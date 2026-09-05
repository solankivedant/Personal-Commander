"""Control Center (ui/server.py) — the loopback surface the desktop UI drives
the real engine through.

The tests that matter here are the ones a browser can't be trusted to keep
honest: that it refuses to bind anywhere but loopback, that an unauthorized
or cross-origin caller gets nothing, and above all that a confirm-tier tool
still cannot run without a human answering the gate. A transport that could
skip that gate would be a hole straight through
`.claude/rules/security-and-privacy.md` §8.2.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from munshiji.bus import EventBus
from munshiji.config import ControlCenterConfig
from munshiji.security.confirm import ConfirmationGate
from munshiji.tools.dispatch import CommandDispatcher
from munshiji.tools.registry import ToolRegistry, ToolSpec
from munshiji.ui.server import ControlCenterServer, _check_loopback_host


class _Route:
    def __init__(self, tool: str | None, args: dict[str, Any], confirm: bool | None) -> None:
        self.tool = tool
        self.args = args
        self.confirm_required = confirm
        self.stage = "grammar"
        self.score = None


class _FakeRouter:
    """Routes by keyword so one server fixture can serve both a safe and a
    confirm-tier command without pulling in the embedding model."""

    def route(self, text: str, lang: str = "en") -> _Route:
        if "delete" in text:
            return _Route("delete_files", {"query": "logs"}, True)
        if "battery" in text:
            return _Route("battery_status", {}, False)
        return _Route(None, {}, None)


def _registry(executed: list[str]) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="battery_status",
            func=lambda: "Battery is at 88%.",
            tier="local",
            risk="safe",
            tags=("system",),
            undo=None,
            description="Report the battery level",
            schema={"type": "object", "properties": {}, "required": []},
        )
    )

    def _delete(query: str) -> str:
        executed.append(query)
        return "Moved 2 files to the Recycle Bin."

    registry.register(
        ToolSpec(
            name="delete_files",
            func=_delete,
            tier="local",
            risk="confirm",
            tags=("files",),
            undo="_undo",
            description="Move files to the Recycle Bin",
            schema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        )
    )
    return registry


@pytest.fixture
def ui_dir(tmp_path: Path) -> Path:
    (tmp_path / "index.html").write_text(
        "<html><body>token=__MUNSHIJI_SESSION_TOKEN__</body></html>", encoding="utf-8"
    )
    (tmp_path / "extra.css").write_text("body{}", encoding="utf-8")
    return tmp_path


@pytest.fixture
def server(ui_dir: Path) -> Any:
    executed: list[str] = []
    dispatcher = CommandDispatcher(
        router=_FakeRouter(),  # type: ignore[arg-type]
        bus=EventBus(),
        registry=_registry(executed),
        confirm_gate=ConfirmationGate(),
    )
    # port 0: the OS picks a free one, so a developer already running the
    # real Control Center on 5180 doesn't fail the suite.
    server = ControlCenterServer(
        dispatcher=dispatcher,
        bus=EventBus(),
        config=ControlCenterConfig(port=0, max_commands_per_minute=1000),
        ui_dir=ui_dir,
        voice_enabled=False,
    )
    server.start()
    server.executed = executed  # type: ignore[attr-defined]
    try:
        yield server
    finally:
        server.stop()


def _request(
    server: Any,
    path: str,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    token: str | None = "",
    origin: str | None = None,
    host: str | None = None,
) -> tuple[int, dict[str, Any] | str]:
    url = f"http://127.0.0.1:{server.port}{path}"
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    presented = server.token if token == "" else token
    if presented is not None:
        request.add_header("Authorization", f"Bearer {presented}")
    if origin is not None:
        request.add_header("Origin", origin)
    if host is not None:
        request.add_header("Host", host)
    try:
        with urllib.request.urlopen(request) as response:
            raw = response.read().decode()
            code = response.status
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        code = exc.code
    try:
        return code, json.loads(raw)
    except ValueError:
        return code, raw


# --- binding ---------------------------------------------------------------


def test_refuses_to_bind_anywhere_but_loopback() -> None:
    assert _check_loopback_host("127.0.0.1") == "127.0.0.1"
    assert _check_loopback_host("localhost") == "localhost"
    for host in ("0.0.0.0", "192.168.1.10", "not-an-address"):
        with pytest.raises(ValueError):
            _check_loopback_host(host)


# --- authorization ---------------------------------------------------------


def test_health_needs_no_token_and_leaks_nothing(server: Any) -> None:
    code, payload = _request(server, "/health", token=None)
    assert code == 200
    assert isinstance(payload, dict)
    assert payload["ok"] is True
    assert "token" not in json.dumps(payload)


def test_command_without_token_is_rejected(server: Any) -> None:
    code, _ = _request(server, "/command", "POST", {"text": "battery"}, token=None)
    assert code == 401


def test_command_with_wrong_token_is_rejected(server: Any) -> None:
    code, _ = _request(server, "/command", "POST", {"text": "battery"}, token="nope")
    assert code == 401


def test_cross_origin_request_is_rejected_even_with_the_token(server: Any) -> None:
    code, _ = _request(
        server, "/command", "POST", {"text": "battery"}, origin="https://evil.example"
    )
    assert code == 403


def test_non_loopback_host_header_is_rejected(server: Any) -> None:
    """The DNS-rebinding guard: a name that resolves to 127.0.0.1 still
    presents its own Host header."""
    code, _ = _request(server, "/health", token=None, host="rebind.example.com")
    assert code == 403


def test_served_page_carries_this_runs_token(server: Any) -> None:
    code, body = _request(server, "/", token=None)
    assert code == 200
    assert isinstance(body, str)
    assert server.token in body
    assert "__MUNSHIJI_SESSION_TOKEN__" not in body


def test_static_traversal_is_refused(server: Any) -> None:
    code, _ = _request(server, "/../../config/default.yaml", token=None)
    assert code in (400, 403, 404)


# --- commands --------------------------------------------------------------


def test_safe_command_actually_runs_and_returns_the_tool_output(server: Any) -> None:
    code, payload = _request(server, "/command", "POST", {"text": "battery"})
    assert code == 200
    assert isinstance(payload, dict)
    assert payload["outcome"] == "executed"
    assert payload["speech"] == "Battery is at 88%."
    assert payload["tool"] == "battery_status"
    assert payload["stage"] == "grammar"


def test_unmatched_command_says_so_rather_than_guessing(server: Any) -> None:
    code, payload = _request(server, "/command", "POST", {"text": "call my mother"})
    assert code == 200
    assert isinstance(payload, dict)
    assert payload["outcome"] == "unmatched"


def test_empty_command_is_rejected(server: Any) -> None:
    code, _ = _request(server, "/command", "POST", {"text": "   "})
    assert code == 400


# --- the confirmation gate, over HTTP --------------------------------------


def test_confirm_tier_command_asks_and_does_not_execute(server: Any) -> None:
    code, payload = _request(server, "/command", "POST", {"text": "delete old logs"})
    assert code == 200
    assert isinstance(payload, dict)
    assert payload["outcome"] == "confirm_requested"
    assert payload["awaiting_confirmation"] is True
    assert server.executed == []


def test_a_yes_over_http_executes_exactly_once(server: Any) -> None:
    _request(server, "/command", "POST", {"text": "delete old logs"})
    code, payload = _request(server, "/confirm", "POST", {"answer": "yes"})
    assert code == 200
    assert isinstance(payload, dict)
    assert payload["outcome"] == "executed"
    assert server.executed == ["logs"]
    # The gate is empty again, so a replayed yes cannot re-run it.
    code, _ = _request(server, "/confirm", "POST", {"answer": "yes"})
    assert code == 409
    assert server.executed == ["logs"]


def test_a_no_over_http_cancels(server: Any) -> None:
    _request(server, "/command", "POST", {"text": "delete old logs"})
    code, payload = _request(server, "/confirm", "POST", {"answer": "nahi"})
    assert code == 200
    assert isinstance(payload, dict)
    assert payload["outcome"] == "cancelled"
    assert server.executed == []


def test_an_unclear_answer_is_reasked_not_taken_as_consent(server: Any) -> None:
    _request(server, "/command", "POST", {"text": "delete old logs"})
    code, payload = _request(server, "/confirm", "POST", {"answer": "hmm maybe"})
    assert code == 200
    assert isinstance(payload, dict)
    assert payload["outcome"] == "confirm_requested"
    assert server.executed == []


def test_confirm_with_nothing_pending_is_a_conflict(server: Any) -> None:
    code, _ = _request(server, "/confirm", "POST", {"answer": "yes"})
    assert code == 409
    assert server.executed == []


def test_there_is_no_approved_flag_to_bypass_the_gate(server: Any) -> None:
    """The only field /confirm reads is the human's own words. A caller that
    tries to assert approval directly gets a 400, not an execution."""
    _request(server, "/command", "POST", {"text": "delete old logs"})
    code, _ = _request(server, "/confirm", "POST", {"approved": True, "confirmed": True})
    assert code == 400
    assert server.executed == []


# --- catalog and rate limiting ---------------------------------------------


def test_catalog_reports_the_real_registry(server: Any) -> None:
    code, payload = _request(server, "/catalog")
    assert code == 200
    assert isinstance(payload, dict)
    names = {tool["name"] for tool in payload["tools"]}
    assert names == {"battery_status", "delete_files"}
    risks = {tool["name"]: tool["risk"] for tool in payload["tools"]}
    assert risks["delete_files"] == "confirm"


def test_commands_are_rate_limited(ui_dir: Path) -> None:
    dispatcher = CommandDispatcher(
        router=_FakeRouter(),  # type: ignore[arg-type]
        bus=EventBus(),
        registry=_registry([]),
        confirm_gate=ConfirmationGate(),
    )
    server = ControlCenterServer(
        dispatcher=dispatcher,
        bus=EventBus(),
        config=ControlCenterConfig(port=0, max_commands_per_minute=2),
        ui_dir=ui_dir,
        voice_enabled=False,
    )
    server.start()
    try:
        codes = [
            _request(server, "/command", "POST", {"text": "battery"})[0] for _ in range(3)
        ]
    finally:
        server.stop()
    assert codes == [200, 200, 429]
