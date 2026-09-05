"""Confirmation gate, audit log, and the FSM's CONFIRMING turn. Phase 3.

These cover the machinery that makes `risk="confirm"` mean something. The
gate's failure modes are all one-directional — every ambiguity must land on
"don't do it" — so most of what's asserted here is that unusual input does
*not* execute anything.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from munshiji.bus import EventBus
from munshiji.security.audit import AuditLog
from munshiji.security.confirm import ConfirmationGate, describe, interpret
from munshiji.tools.registry import ToolRegistry, ToolSpec

# ---------------------------------------------------------------------------
# Yes / no interpretation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    ["yes", "yeah", "sure", "ok", "go ahead", "do it", "haan", "ji haan", "kar do", "barabar"],
)
def test_affirmative_answers(text: str) -> None:
    assert interpret(text) == "yes"


@pytest.mark.parametrize(
    "text",
    ["no", "nope", "cancel", "stop", "never mind", "nahi", "mat karo", "rehne do", "nathi", "na"],
)
def test_negative_answers(text: str) -> None:
    assert interpret(text) == "no"


@pytest.mark.parametrize("text", ["", "   ", "umm", "the weather is nice", "what time is it"])
def test_unrecognized_answers_are_unclear_not_yes(text: str) -> None:
    """Silence, noise and unrelated speech must never read as consent."""
    assert interpret(text) == "unclear"


def test_negatives_beat_affirmatives_in_the_same_utterance() -> None:
    """"nahi karo" contains "karo". Reading a transcript that holds both as
    consent is the worst failure this module could have, so negatives win."""
    assert interpret("nahi karo") == "no"
    assert interpret("yes but no") == "no"
    assert interpret("please don't") == "no"


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------


def _spec(name: str = "delete_files", preview: Any = None) -> ToolSpec:
    return ToolSpec(
        name=name,
        func=lambda **kwargs: "done",
        tier="local",
        risk="confirm",
        tags=("files",),
        undo="_undo",
        description="Move files to the Recycle Bin",
        schema={"type": "object", "properties": {}, "required": []},
        preview=preview,
    )


def test_gate_executes_only_on_a_spoken_yes() -> None:
    gate = ConfirmationGate()
    gate.request(_spec(), {"query": "old logs"})
    result = gate.resolve("haan")
    assert result.should_execute
    assert result.pending is not None and result.pending.args == {"query": "old logs"}


def test_gate_cancels_on_no_and_clears_pending() -> None:
    gate = ConfirmationGate()
    gate.request(_spec(), {"query": "old logs"})
    result = gate.resolve("nahi")
    assert not result.should_execute
    assert result.outcome == "cancelled"
    assert gate.pending is None


def test_gate_reasks_once_then_fails_closed() -> None:
    gate = ConfirmationGate(max_attempts=2)
    gate.request(_spec(), {})
    first = gate.resolve("umm")
    assert first.outcome == "reasked"
    assert gate.pending is not None, "still waiting after one unclear answer"

    second = gate.resolve("mmm what")
    assert second.outcome == "cancelled"
    assert not second.should_execute
    assert gate.pending is None


def test_pending_confirmation_expires() -> None:
    """A "yes" answering some later question must not fire an action proposed
    minutes earlier."""
    gate = ConfirmationGate(timeout_s=30)
    start = datetime.now(UTC)
    gate.request(_spec(), {}, now=start)
    result = gate.resolve("yes", now=start + timedelta(seconds=31))
    assert result.outcome == "expired"
    assert not result.should_execute
    assert gate.pending is None


def test_expiry_is_checked_before_the_answer() -> None:
    """Even an unambiguous yes cannot revive an expired proposal."""
    gate = ConfirmationGate(timeout_s=1)
    start = datetime.now(UTC)
    gate.request(_spec(), {}, now=start)
    assert not gate.resolve("yes", now=start + timedelta(minutes=5)).should_execute


def test_resolving_with_nothing_pending_executes_nothing() -> None:
    gate = ConfirmationGate()
    result = gate.resolve("yes")
    assert result.outcome == "none_pending"
    assert not result.should_execute


def test_second_request_replaces_the_first() -> None:
    """Only one action may be outstanding — "yes" must never be ambiguous
    about what it approves."""
    gate = ConfirmationGate()
    gate.request(_spec("move_files"), {})
    gate.request(_spec("delete_files"), {})
    result = gate.resolve("yes")
    assert result.pending is not None and result.pending.tool == "delete_files"


def test_prompt_uses_the_tool_preview_when_present() -> None:
    """§8.2 wants "I'll move 14 PDFs from Desktop to Documents. Proceed?" —
    a summary of the real effect, not a restatement of the arguments."""
    spec = _spec(preview=lambda **kw: "Move 14 PDFs from Desktop to Documents")
    prompt = describe(spec, {"query": "all pdfs"})
    assert "14 PDFs" in prompt and prompt.endswith("Should I go ahead?")


def test_broken_preview_still_produces_a_prompt() -> None:
    """A previewer that raises must degrade to the generic wording — never
    skip asking."""

    def boom(**kwargs: Any) -> str:
        raise RuntimeError("nope")

    prompt = describe(_spec(preview=boom), {"query": "x"})
    assert "Should I go ahead?" in prompt


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------


def test_audit_records_action_args_result_and_stage(tmp_path: Path) -> None:
    """engineering-standards.md: every action, its arguments, its result, a
    timestamp, and which router stage decided it."""
    log = AuditLog(tmp_path / "audit.jsonl")
    log.record(
        "tool.executed",
        {"tool": "delete_files", "args": {"query": "old logs"}, "result": "ok", "stage": "grammar"},
    )
    entries = list(log.read_entries())
    assert len(entries) == 1
    entry = entries[0]
    assert entry["tool"] == "delete_files"
    assert entry["args"] == {"query": "old logs"}
    assert entry["result"] == "ok"
    assert entry["stage"] == "grammar"
    assert entry["ts"]


def test_audit_subscribes_to_the_bus_rather_than_being_called(tmp_path: Path) -> None:
    """The audit log is a cross-cutting subscriber, not a collaborator wired
    into the FSM (docs/ARCHITECTURE.md)."""
    bus = EventBus()
    log = AuditLog(tmp_path / "audit.jsonl")
    log.attach(bus)

    bus.publish("router.route", {"tool": "mute", "stage": "grammar"})
    bus.publish("tool.executed", {"tool": "mute", "result": "Audio muted.", "stage": "grammar"})
    bus.publish("fsm.transition", {"old": "idle", "new": "listening"})  # not audited

    events = [e["event"] for e in log.read_entries()]
    assert events == ["router.route", "tool.executed"]


def test_audit_redacts_secret_shaped_arguments(tmp_path: Path) -> None:
    log = AuditLog(tmp_path / "audit.jsonl")
    log.record("tool.executed", {"tool": "x", "args": {"password": "hunter2", "path": "a.txt"}})
    entry = next(iter(log.read_entries()))
    assert entry["args"]["password"] == "<redacted>"
    assert entry["args"]["path"] == "a.txt"


def test_audit_never_raises_into_the_publisher(tmp_path: Path) -> None:
    """A full disk must not take the assistant down mid-command."""
    log = AuditLog(tmp_path / "nope" / "audit.jsonl")

    def explode(*args: Any, **kwargs: Any) -> Any:
        raise OSError("disk full")

    log._path.parent.mkdir(parents=True, exist_ok=True)
    original = Path.open
    try:
        Path.open = explode  # type: ignore[method-assign]
        log.record("tool.executed", {"tool": "x"})
    finally:
        Path.open = original  # type: ignore[method-assign]
    assert log.write_failures == 1


def test_audit_rotates_when_oversized(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path, rotate_mb=0)  # every write rotates
    log.record("tool.executed", {"tool": "first"})
    log.record("tool.executed", {"tool": "second"})
    assert path.with_suffix(".jsonl.1").exists()
    assert [e["tool"] for e in log.read_entries()] == ["second"]


def test_audit_skips_malformed_lines_rather_than_failing(tmp_path: Path) -> None:
    """A truncated final line from an interrupted write must not make the
    whole history unreadable."""
    path = tmp_path / "audit.jsonl"
    path.write_text(
        json.dumps({"event": "tool.executed", "tool": "a"}) + "\n{broken\n",
        encoding="utf-8",
    )
    assert [e["tool"] for e in AuditLog(path).read_entries()] == ["a"]


# ---------------------------------------------------------------------------
# FSM: the CONFIRMING turn
# ---------------------------------------------------------------------------


class _Route:
    def __init__(self, tool: str | None, args: dict[str, Any], confirm: bool | None) -> None:
        self.tool = tool
        self.args = args
        self.confirm_required = confirm
        self.stage = "grammar"
        self.score = None


class _FakeRouter:
    def __init__(self, route: _Route) -> None:
        self._route = route

    def route(self, text: str, lang: str = "en") -> _Route:
        return self._route


def _fsm_with(route: _Route, gate: ConfirmationGate | None, executed: list[str]) -> Any:
    """A VoiceFSM with only the pieces _route/_resolve_confirmation touch.

    Constructing a real one needs audio, ASR and TTS; this exercises the
    routing/confirmation logic directly, which is what these tests are about.
    """
    from munshiji.wake.fsm import VoiceFSM

    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="delete_files",
            func=lambda **kwargs: executed.append("ran") or "Moved 2 files to the Recycle Bin.",
            tier="local",
            risk="confirm",
            tags=("files",),
            undo="_undo",
            description="Move files to the Recycle Bin",
            schema={"type": "object", "properties": {"query": {"type": "string"}},
                    "required": ["query"]},
        )
    )
    fsm = VoiceFSM.__new__(VoiceFSM)
    fsm._router = _FakeRouter(route)  # type: ignore[attr-defined]
    fsm._registry = registry  # type: ignore[attr-defined]
    fsm._confirm_gate = gate  # type: ignore[attr-defined]
    fsm._bus = EventBus()  # type: ignore[attr-defined]
    return fsm


def test_confirm_tier_route_asks_instead_of_executing() -> None:
    executed: list[str] = []
    gate = ConfirmationGate()
    fsm = _fsm_with(_Route("delete_files", {"query": "old logs"}, True), gate, executed)

    spoken = fsm._route("delete old logs")
    assert "Should I go ahead?" in spoken
    assert executed == [], "nothing may run before a spoken yes"
    assert gate.pending is not None


def test_yes_on_the_next_turn_executes() -> None:
    executed: list[str] = []
    gate = ConfirmationGate()
    fsm = _fsm_with(_Route("delete_files", {"query": "old logs"}, True), gate, executed)

    fsm._route("delete old logs")
    result = fsm._resolve_confirmation("haan")
    assert executed == ["ran"]
    assert "Recycle Bin" in result


def test_no_on_the_next_turn_executes_nothing() -> None:
    executed: list[str] = []
    gate = ConfirmationGate()
    fsm = _fsm_with(_Route("delete_files", {"query": "old logs"}, True), gate, executed)

    fsm._route("delete old logs")
    fsm._resolve_confirmation("nahi")
    assert executed == []


def test_without_a_gate_confirm_tools_are_refused_not_run() -> None:
    """The gate adds the ability to say yes, never the ability to skip being
    asked. With no gate wired, a confirm-tier route must still not execute."""
    executed: list[str] = []
    fsm = _fsm_with(_Route("delete_files", {"query": "old logs"}, True), None, executed)
    assert "needs confirmation" in fsm._route("delete old logs")
    assert executed == []


def test_unknown_risk_is_treated_as_needing_confirmation() -> None:
    """confirm_required=None means the registry had no answer. It must fail
    the same way as True, never as False."""
    executed: list[str] = []
    gate = ConfirmationGate()
    fsm = _fsm_with(_Route("delete_files", {"query": "old logs"}, None), gate, executed)
    fsm._route("delete old logs")
    assert executed == []
    assert gate.pending is not None


def test_missing_required_args_asks_rather_than_calling_the_tool() -> None:
    """An embedding-stage file match arrives with its free-text slots dropped
    (router/slots.py). Calling the tool would raise; guessing would act on the
    wrong files. Asking is the only correct move."""
    executed: list[str] = []
    gate = ConfirmationGate()
    fsm = _fsm_with(_Route("delete_files", {}, True), gate, executed)

    spoken = fsm._route("purani files hata do")
    assert "which files you mean" in spoken
    assert executed == []
    assert gate.pending is None, "nothing should be proposed when we can't say what it does"


def test_confirmation_flow_is_fully_audited(tmp_path: Path) -> None:
    """The log must explain "why did it delete that" afterwards: the route,
    the question, the answer, and the result."""
    executed: list[str] = []
    gate = ConfirmationGate()
    fsm = _fsm_with(_Route("delete_files", {"query": "old logs"}, True), gate, executed)
    log = AuditLog(tmp_path / "audit.jsonl")
    log.attach(fsm._bus)

    fsm._route("delete old logs")
    fsm._resolve_confirmation("haan")

    events = [e["event"] for e in log.read_entries()]
    assert events == ["router.route", "confirm.requested", "confirm.resolved", "tool.executed"]

    entries = {e["event"]: e for e in log.read_entries()}
    assert entries["confirm.resolved"]["outcome"] == "confirmed"
    assert entries["confirm.resolved"]["answer_text"] == "haan"
    assert entries["tool.executed"]["stage"] == "grammar"
    assert entries["tool.executed"]["args"] == {"query": "old logs"}


def test_refusal_is_audited_too(tmp_path: Path) -> None:
    executed: list[str] = []
    gate = ConfirmationGate()
    fsm = _fsm_with(_Route("delete_files", {"query": "old logs"}, True), gate, executed)
    log = AuditLog(tmp_path / "audit.jsonl")
    log.attach(fsm._bus)

    fsm._route("delete old logs")
    fsm._resolve_confirmation("nahi")

    entries = {e["event"]: e for e in log.read_entries()}
    assert entries["confirm.resolved"]["outcome"] == "cancelled"
    assert entries["tool.refused"]["reason"] == "cancelled"
