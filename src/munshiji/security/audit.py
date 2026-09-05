"""Append-only audit log. Phase 3.

`docs/ARCHITECTURE.md` lists the audit log as a cross-cutting concern beside
the event bus and config, and `.claude/rules/architecture-and-router.md`
requires those to be *subscribers* rather than callers wired into internals.
So this module attaches to `EventBus` topics and writes what it hears; no
layer calls it directly, and nothing here can change what the assistant does.

What it must capture, per `.claude/rules/engineering-standards.md`: **every
action, its arguments, its result, a timestamp, and which router stage decided
it.** That last field is the one that makes the log worth keeping — "why did
it delete that" is answered by knowing whether a grammar template, an
embedding neighbour, or an escalation chose the tool, and a log without it
just says the deletion happened. Treat gaps as bugs.

Deliberately *not* a structlog sink. `logging.level` controls a developer
diagnostic stream that is meant to be tunable and discardable; this is an
evidence trail with a fixed schema that must not thin out because someone
raised the log level to WARNING.

Secrets: this log records tool arguments verbatim, and Phase 5's `net`-tier
tools will take arguments that are not safe to persist. `REDACTED_ARG_KEYS`
is the hook for that and is applied on every write — extend it there rather
than remembering to sanitize at each call site.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from munshiji.bus import EventBus

# Argument names whose values never reach the log. Matched case-insensitively
# against a substring of the key, so "api_key" and "APIKey" both redact.
REDACTED_ARG_KEYS: tuple[str, ...] = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "credential",
    "auth",
)

_REDACTED = "<redacted>"

# Bus topics this log subscribes to. Adding a topic here is how a new event
# becomes auditable — there is no second place to update.
AUDITED_TOPICS: tuple[str, ...] = (
    "router.route",
    "tool.executed",
    "tool.refused",
    "confirm.requested",
    "confirm.resolved",
    "undo.performed",
)


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(marker in lowered for marker in REDACTED_ARG_KEYS):
                out[str(key)] = _REDACTED
            else:
                out[str(key)] = _redact(item)
        return out
    if isinstance(value, (list, tuple)):
        return [_redact(v) for v in value]
    return value


class AuditLog:
    """Append-only JSONL writer with size-based rotation.

    Thread-safe: the FSM thread publishes tool results while a future HTTP API
    (Phase 7) may publish its own, and `EventBus` runs callbacks on the
    publisher's thread.

    Never raises into a publisher. A full disk or a locked file must not take
    the assistant down mid-command — a lost audit line is bad, a crash while
    the user is talking is worse. Write failures are counted and surfaced by
    `write_failures` so the condition is visible rather than silent.
    """

    def __init__(self, path: Path, rotate_mb: int = 50) -> None:
        self._path = path
        self._rotate_bytes = rotate_mb * 1024 * 1024
        self._lock = threading.Lock()
        self.write_failures = 0

    @property
    def path(self) -> Path:
        return self._path

    def record(self, event: str, payload: Any = None, **fields: Any) -> None:
        """Append one entry. `event` is the bus topic or an explicit name."""
        entry: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(),
            "event": event,
        }
        if isinstance(payload, dict):
            entry.update(_redact(payload))
        elif payload is not None:
            entry["payload"] = _redact(payload)
        if fields:
            entry.update(_redact(fields))

        line = json.dumps(entry, ensure_ascii=False, default=str)
        with self._lock:
            try:
                self._rotate_if_needed()
                self._path.parent.mkdir(parents=True, exist_ok=True)
                with self._path.open("a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except OSError:
                self.write_failures += 1

    def _rotate_if_needed(self) -> None:
        try:
            size = self._path.stat().st_size
        except OSError:
            return
        if size < self._rotate_bytes:
            return
        # Single generation. The point of this log is recent forensics ("why
        # did it delete that three days ago"), not indefinite retention, and
        # unbounded generations on a laptop is its own failure mode.
        previous = self._path.with_suffix(self._path.suffix + ".1")
        try:
            previous.unlink(missing_ok=True)
            self._path.rename(previous)
        except OSError:
            self.write_failures += 1

    def attach(self, bus: EventBus) -> None:
        """Subscribe to every topic in AUDITED_TOPICS."""
        for topic in AUDITED_TOPICS:
            bus.subscribe(topic, self._on_event)

    def detach(self, bus: EventBus) -> None:
        for topic in AUDITED_TOPICS:
            bus.unsubscribe(topic, self._on_event)

    def _on_event(self, topic: str, payload: Any) -> None:
        self.record(topic, payload)

    def read_entries(self) -> Iterator[dict[str, Any]]:
        """Read the log back. Used by tests and, later, the Phase 7 `/audit`
        endpoint. Malformed lines are skipped rather than raising — a
        truncated final line from an interrupted write must not make the
        whole history unreadable."""
        if not self._path.exists():
            return
        with self._path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
