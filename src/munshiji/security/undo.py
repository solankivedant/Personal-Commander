"""Inverse-operation undo stack, registered before execution. Phase 3 owns the
full audit-log-integrated undo UX (multi-step undo, "undo that" voice command,
undo across file operations); Phase 2's system/app tools push real inverses
onto this stack now so the mechanism is load-bearing from day one rather than
stubbed out and retrofitted later.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

_DEFAULT_MAX_DEPTH = 20  # mirrors config/default.yaml's security.undo_depth;
# see UndoStack.configure() to sync the live singleton with the loaded config.


@dataclass
class UndoRecord:
    tool_name: str
    description: str
    inverse: Callable[[], str]
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


class UndoStack:
    """Bounded LIFO stack of inverse operations. Thread-safe: tool execution
    happens on the FSM thread, but a future HTTP API (Phase 7) or a
    concurrent voice command could call into this too.
    """

    def __init__(self, max_depth: int = _DEFAULT_MAX_DEPTH) -> None:
        self._records: list[UndoRecord] = []
        self._max_depth = max_depth
        self._lock = threading.Lock()

    def configure(self, max_depth: int) -> None:
        with self._lock:
            self._max_depth = max_depth
            del self._records[: max(0, len(self._records) - max_depth)]

    def push(self, tool_name: str, description: str, inverse: Callable[[], str]) -> None:
        """Record an inverse for `tool_name`. Call this *before* performing
        the mutation, per security-and-privacy.md — if the mutation then
        fails, the tool should catch its own exception and the pushed record
        simply never gets used, which is harmless.
        """
        with self._lock:
            self._records.append(UndoRecord(tool_name, description, inverse))
            overflow = len(self._records) - self._max_depth
            if overflow > 0:
                del self._records[:overflow]

    def can_undo(self) -> bool:
        with self._lock:
            return bool(self._records)

    def peek_description(self) -> str | None:
        with self._lock:
            return self._records[-1].description if self._records else None

    def undo_last(self) -> str:
        with self._lock:
            if not self._records:
                return "Nothing to undo."
            record = self._records.pop()
        try:
            return record.inverse()
        except Exception as exc:  # tool inverses must never raise into the caller
            return f"Could not undo {record.tool_name!r}: {exc}"

    def clear(self) -> None:
        """Test-only: reset between test modules."""
        with self._lock:
            self._records.clear()


UNDO_STACK = UndoStack()
