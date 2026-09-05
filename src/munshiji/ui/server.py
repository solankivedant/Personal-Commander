"""Control Center backend: a loopback-only HTTP server that lets the local
desktop UI drive the *real* engine — router, tool registry, confirmation
gate, audit log — instead of replaying canned answers.

Why this exists, and what it deliberately is not:

* `desktop-preview/` shipped a static mockup whose buttons played recorded
  strings. This module is what turns those buttons into real commands: the
  page posts an utterance, `tools/dispatch.py` routes it through the same
  cascade a spoken command takes, and the reply is whatever the tool
  actually returned on this machine.
* It is **not** `net/api.py` (Phase 7). That one is the remote surface —
  bound to the Tailscale interface, reachable from a phone. This one binds
  to loopback and refuses to bind anywhere else (`_check_loopback_host`), so
  it is not a network service at all; nothing it serves leaves the machine.
  Keeping them separate is deliberate: the remote API's threat model (a
  device on a shared tailnet) is not this one's.

Security posture, per `.claude/rules/security-and-privacy.md`:

* **Loopback only.** `0.0.0.0` and any non-loopback host raise at
  construction rather than silently exposing a machine-control API.
* **Bearer token**, minted per run and injected into the page this server
  serves. A page the user opens from anywhere else has no token and can do
  nothing but `/health`.
* **Host and Origin checks** on every request, which is what stops a remote
  page in the user's browser from reaching 127.0.0.1 by DNS rebinding or
  plain cross-origin POST.
* **No confirmation bypass.** `/confirm` carries the words the human typed
  or clicked to `ConfirmationGate.resolve()`; there is no "approved: true"
  parameter, so this transport cannot approve anything a person did not.
* **Rate limited** on the two mutating endpoints, and every request logged.
"""

from __future__ import annotations

import ipaddress
import json
import queue
import secrets
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import structlog

from munshiji.bus import EventBus
from munshiji.config import ControlCenterConfig
from munshiji.tools.dispatch import CommandDispatcher

logger = structlog.get_logger(__name__)

# Bus topics the UI mirrors. Subscribing to a fixed list (rather than
# everything) keeps a voice turn and a typed turn rendering identically
# without the page having to know about internal events.
STREAMED_TOPICS: tuple[str, ...] = (
    "fsm.transition",
    "asr.transcript",
    "router.route",
    "tool.executed",
    "tool.refused",
    "confirm.requested",
    "confirm.resolved",
)

# Origins a legitimately-served page can present. Everything loopback is
# derived from the bind address at runtime; the tauri ones are the origins
# the desktop preview shell uses when it hosts the page itself.
_STATIC_ALLOWED_ORIGINS: frozenset[str] = frozenset(
    {"tauri://localhost", "http://tauri.localhost", "https://tauri.localhost", "null"}
)

_MAX_BODY_BYTES = 64 * 1024
_TOKEN_PLACEHOLDER = "__MUNSHIJI_SESSION_TOKEN__"

_CONTENT_TYPES: dict[str, str] = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}


def _check_loopback_host(host: str) -> str:
    """Refuse to bind anywhere a second machine could reach.

    security-and-privacy.md forbids binding the API to `0.0.0.0`; for this
    server the rule is stricter still, because it is a machine-control
    surface with no reason to be reachable off-box. Failing loudly at
    construction is the point — a misconfigured host must not start.
    """
    if host in ("localhost", "::1"):
        return host
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise ValueError(
            f"ui.control_center.host must be a loopback address, got {host!r}"
        ) from exc
    if not address.is_loopback:
        raise ValueError(
            f"ui.control_center.host must be a loopback address, got {host!r} — "
            "the Control Center is local-only by design (see ui/server.py)."
        )
    return host


class _RateLimiter:
    """Fixed-window request cap for the mutating endpoints."""

    def __init__(self, max_per_minute: int) -> None:
        self._max = max_per_minute
        self._hits: deque[float] = deque()
        self._lock = threading.Lock()

    def allow(self, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        with self._lock:
            while self._hits and now - self._hits[0] > 60.0:
                self._hits.popleft()
            if len(self._hits) >= self._max:
                return False
            self._hits.append(now)
            return True


class _EventStream:
    """Fan-out of bus events to connected Server-Sent Events clients.

    Bounded per-client queues: a stalled browser tab drops its own events
    rather than blocking the publisher's thread, which is the FSM's audio
    thread (see bus.py — subscribers run synchronously on it).
    """

    def __init__(self, bus: EventBus, queue_size: int, max_clients: int) -> None:
        self._queue_size = queue_size
        self._max_clients = max_clients
        self._clients: list[queue.Queue[str | None]] = []
        self._lock = threading.Lock()
        for topic in STREAMED_TOPICS:
            bus.subscribe(topic, self._on_event)

    def _on_event(self, topic: str, payload: Any) -> None:
        try:
            line = json.dumps({"topic": topic, "payload": payload}, default=str)
        except (TypeError, ValueError):
            return
        with self._lock:
            clients = list(self._clients)
        for client in clients:
            try:
                client.put_nowait(line)
            except queue.Full:
                pass

    def register(self) -> queue.Queue[str | None] | None:
        with self._lock:
            if len(self._clients) >= self._max_clients:
                return None
            client: queue.Queue[str | None] = queue.Queue(maxsize=self._queue_size)
            self._clients.append(client)
            return client

    def unregister(self, client: queue.Queue[str | None]) -> None:
        with self._lock:
            if client in self._clients:
                self._clients.remove(client)

    def close(self) -> None:
        with self._lock:
            clients = list(self._clients)
            self._clients.clear()
        for client in clients:
            try:
                client.put_nowait(None)
            except queue.Full:
                pass


class ControlCenterServer:
    """Serves the Control Center page and the small API behind it."""

    def __init__(
        self,
        dispatcher: CommandDispatcher,
        bus: EventBus,
        config: ControlCenterConfig,
        ui_dir: Path,
        voice_enabled: bool,
        token: str | None = None,
    ) -> None:
        self._host = _check_loopback_host(config.host)
        self._port = config.port
        self._dispatcher = dispatcher
        self._ui_dir = ui_dir.resolve()
        self._voice_enabled = voice_enabled
        self.token = token or secrets.token_urlsafe(32)
        self._limiter = _RateLimiter(config.max_commands_per_minute)
        self._events = _EventStream(bus, config.event_queue_size, config.max_event_clients)
        self._httpd = ThreadingHTTPServer((self._host, self._port), self._make_handler())
        self._httpd.daemon_threads = True
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return self._httpd.server_address[1]

    @property
    def url(self) -> str:
        return f"http://{self._host}:{self.port}/?token={self.token}"

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, name="control-center", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._events.close()
        self._httpd.shutdown()
        self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    # --- request handling -------------------------------------------------

    def _allowed_origins(self) -> frozenset[str]:
        hosts = {self._host, "localhost", "127.0.0.1"}
        origins = {
            f"{scheme}://{host}:{self.port}" for scheme in ("http", "https") for host in hosts
        }
        return frozenset(origins) | _STATIC_ALLOWED_ORIGINS

    def _origin_ok(self, origin: str | None) -> bool:
        """A missing Origin is allowed (curl, EventSource on some engines);
        a present one must be a page we could have served. Browsers always
        send it on cross-origin POSTs, which is the case that matters."""
        return origin is None or origin in self._allowed_origins()

    def _host_header_ok(self, host_header: str | None) -> bool:
        """Reject a Host that isn't loopback — the DNS-rebinding guard."""
        if host_header is None:
            return False
        name = host_header.rsplit(":", 1)[0].strip("[]").lower()
        if name in ("localhost", "::1"):
            return True
        try:
            return ipaddress.ip_address(name).is_loopback
        except ValueError:
            return False

    def _catalog(self) -> list[dict[str, Any]]:
        """The real registry, as the UI's Commands tab renders it.

        `blocked`-risk tools are listed but flagged: the page showing that
        they exist and are unreachable is the honest thing, and matches the
        registry's own split (`iter_llm_visible()`).
        """
        return [
            {
                "name": spec.name,
                "description": spec.description,
                "tier": spec.tier,
                "risk": spec.risk,
                "tags": list(spec.tags),
                "undo": spec.undo,
                "args": list(spec.schema.get("properties", {}).keys()),
                "required": list(spec.schema.get("required", [])),
            }
            for spec in sorted(self._dispatcher.registry.all(), key=lambda s: s.name)
        ]

    def _result_json(self, result: Any) -> dict[str, Any]:
        return {
            "speech": result.speech,
            "outcome": result.outcome,
            "tool": result.tool,
            "stage": result.stage,
            "args": result.args,
            "risk": result.risk,
            "tier": result.tier,
            "score": result.score,
            "awaiting_confirmation": self._dispatcher.awaiting_confirmation,
        }

    def _read_index(self) -> bytes:
        """Serve the page with this run's token baked in.

        The token never travels as a URL the user has to copy: the page the
        server hands out already knows it, and a page from anywhere else
        does not.
        """
        html = (self._ui_dir / "index.html").read_text(encoding="utf-8")
        return html.replace(_TOKEN_PLACEHOLDER, self.token).encode("utf-8")

    def _static_path(self, url_path: str) -> Path | None:
        candidate = (self._ui_dir / url_path.lstrip("/")).resolve()
        # resolve() first, then containment — a textual prefix check passes
        # both `..` and a symlink (same rule as tools/files.py).
        if candidate != self._ui_dir and self._ui_dir not in candidate.parents:
            return None
        if candidate.is_dir():
            candidate = candidate / "index.html"
        return candidate if candidate.is_file() else None

    def _make_handler(self) -> type[BaseHTTPRequestHandler]:
        server = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            server_version = "MunshijiControlCenter/1.0"

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                logger.info(
                    "control_center_request",
                    client=self.client_address[0],
                    msg=format % args,
                )

            # -- helpers --
            def _send(self, code: int, body: bytes, content_type: str) -> None:
                self.send_response(code)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)

            def _send_json(self, code: int, payload: dict[str, Any]) -> None:
                self._send(
                    code,
                    json.dumps(payload, default=str).encode("utf-8"),
                    "application/json; charset=utf-8",
                )

            def _guard(self) -> bool:
                """Common checks for every request. Returns False if answered."""
                if not server._host_header_ok(self.headers.get("Host")):
                    self._send_json(403, {"error": "non-loopback Host header"})
                    return False
                if not server._origin_ok(self.headers.get("Origin")):
                    self._send_json(403, {"error": "origin not allowed"})
                    return False
                return True

            def _authorized(self, query: dict[str, list[str]]) -> bool:
                header = self.headers.get("Authorization", "")
                presented = ""
                if header.startswith("Bearer "):
                    presented = header[len("Bearer ") :]
                elif "token" in query:
                    # EventSource cannot set headers, so /events carries the
                    # token in the query string. Same secret, same origin
                    # checks; it only ever appears in a loopback URL.
                    presented = query["token"][0]
                return secrets.compare_digest(presented, server.token)

            def _body(self) -> dict[str, Any] | None:
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    return None
                if length <= 0 or length > _MAX_BODY_BYTES:
                    return None
                try:
                    return dict(json.loads(self.rfile.read(length).decode("utf-8")))
                except (ValueError, UnicodeDecodeError):
                    return None

            # -- routes --
            def do_GET(self) -> None:  # noqa: N802
                if not self._guard():
                    return
                parsed = urlparse(self.path)
                query = parse_qs(parsed.query)
                path = parsed.path

                if path == "/health":
                    # Token-free on purpose: it is how a page that has no
                    # token discovers the engine is up, and it reveals
                    # nothing but that.
                    self._send_json(
                        200,
                        {
                            "ok": True,
                            "voice": server._voice_enabled,
                            "tools": len(server._dispatcher.registry.all()),
                        },
                    )
                    return

                if path in ("/", "/index.html"):
                    try:
                        self._send(200, server._read_index(), "text/html; charset=utf-8")
                    except OSError:
                        self._send_json(500, {"error": "UI files not found"})
                    return

                if path == "/state":
                    if not self._authorized(query):
                        self._send_json(401, {"error": "bad or missing token"})
                        return
                    self._send_json(
                        200,
                        {
                            "voice": server._voice_enabled,
                            "awaiting_confirmation": server._dispatcher.awaiting_confirmation,
                            "pending_prompt": server._dispatcher.pending_prompt,
                        },
                    )
                    return

                if path == "/catalog":
                    if not self._authorized(query):
                        self._send_json(401, {"error": "bad or missing token"})
                        return
                    self._send_json(200, {"tools": server._catalog()})
                    return

                if path == "/events":
                    if not self._authorized(query):
                        self._send_json(401, {"error": "bad or missing token"})
                        return
                    self._stream_events()
                    return

                static = server._static_path(path)
                if static is None:
                    self._send_json(404, {"error": "not found"})
                    return
                self._send(
                    200,
                    static.read_bytes(),
                    _CONTENT_TYPES.get(static.suffix, "application/octet-stream"),
                )

            def do_POST(self) -> None:  # noqa: N802
                if not self._guard():
                    return
                parsed = urlparse(self.path)
                if parsed.path not in ("/command", "/confirm"):
                    self._send_json(404, {"error": "not found"})
                    return
                if not self._authorized(parse_qs(parsed.query)):
                    self._send_json(401, {"error": "bad or missing token"})
                    return
                if not server._limiter.allow():
                    self._send_json(429, {"error": "too many commands, slow down"})
                    return

                body = self._body()
                if body is None:
                    self._send_json(400, {"error": "expected a small JSON body"})
                    return

                if parsed.path == "/command":
                    text = str(body.get("text", "")).strip()
                    if not text:
                        self._send_json(400, {"error": "text is required"})
                        return
                    # handle(), not route(): if something is already waiting
                    # on a yes/no, this utterance is the answer to it.
                    result = server._dispatcher.handle(text)
                else:
                    answer = str(body.get("answer", "")).strip()
                    if not answer:
                        self._send_json(400, {"error": "answer is required"})
                        return
                    if not server._dispatcher.awaiting_confirmation:
                        self._send_json(409, {"error": "nothing is waiting for an answer"})
                        return
                    # The user's own words go to the gate — the gate decides.
                    result = server._dispatcher.resolve_confirmation(answer)

                self._send_json(200, server._result_json(result))

            def _stream_events(self) -> None:
                client = server._events.register()
                if client is None:
                    self._send_json(503, {"error": "too many event listeners"})
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Connection", "close")
                self.end_headers()
                try:
                    while True:
                        try:
                            line = client.get(timeout=15.0)
                        except queue.Empty:
                            # Keep-alive comment: without it a dropped client
                            # is only noticed when an event happens to fire.
                            self.wfile.write(b": keepalive\n\n")
                            self.wfile.flush()
                            continue
                        if line is None:
                            return
                        self.wfile.write(f"data: {line}\n\n".encode())
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    return
                finally:
                    server._events.unregister(client)

        return Handler
