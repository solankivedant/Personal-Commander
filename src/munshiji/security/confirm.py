"""Spoken confirmation gate for `risk="confirm"` tools. Phase 3.

The rule this implements (`.claude/rules/security-and-privacy.md` §8.2):
anything that **deletes, sends, spends, or overwrites** speaks its intent and
blocks on a spoken yes before executing. The threat it exists for is specific
and foreseeable, not hypothetical — voice transcription errors plus an eager
matcher plus real filesystem access. Phase 2's own held-out measurements make
that concrete: "meri maa ko phone lagao" ("call my mother") routed to
`restart`, and this gate is what stood between that and a reboot.

Three properties are load-bearing, and all three fail *closed*:

1. **Only a human voice can confirm.** `resolve()` takes an ASR transcript and
   nothing else. There is deliberately no API by which a tool result, a router
   score, or a "clearly safe" special case can approve an action — §8.1's
   fourth rule is that a tool result must never directly trigger a confirm-tier
   action, and the way to guarantee that is to give the code no path to do it.
2. **Pending confirmations expire** (`security.confirm_timeout_s`). Without
   this, a "yes" meant for some later question could execute an action
   proposed minutes earlier. An expired gate cancels; it never executes.
3. **Ambiguity is not consent.** Anything not recognizably affirmative is
   re-asked, and after `security.confirm_max_attempts` the action is dropped.
   Silence, noise and a misheard word all land in the same safe place.

Multi-step dry-run plan summarization (the model emits a whole sequence, the
assistant speaks one summary, nothing runs until confirmed) is Phase 4 — it
needs the escalation loop that produces plans. `describe()` here is the
single-call version of that summary and is what Phase 4 should build on.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from munshiji.tools.registry import ToolSpec

Answer = Literal["yes", "no", "unclear"]
Outcome = Literal["confirmed", "cancelled", "expired", "reasked", "none_pending"]

# Affirmative/negative vocabulary across en/hi/gu. Romanized Hindi/Gujarati
# forms sit alongside the English ones because this is exact word matching,
# not embedding similarity — nothing places "haan" near "yes" for free (the
# same reasoning as the {state} slot list in router/grammar.py).
#
# Matched as whole words against the transcript. NEGATIVE is checked first:
# "nahi karo" contains "karo", and reading that as consent would be the worst
# possible failure of this module.
AFFIRMATIVE: frozenset[str] = frozenset(
    {
        # en. Deliberately excludes bare "do" and "please": they carry no
        # affirmative meaning on their own ("please don't") and the phrases
        # that do — "do it", "yes please" — are matched below.
        "yes", "yeah", "yep", "yup", "sure", "ok", "okay", "okey",
        "confirm", "confirmed", "correct", "right", "proceed", "continue",
        # hi
        "haan", "han", "haa", "ha", "ji", "bilkul", "karo", "kardo",
        "thik", "theek", "sahi", "chalo",
        # gu
        "hoye", "barabar", "kari",
    }
)

NEGATIVE: frozenset[str] = frozenset(
    {
        # en
        "no", "nope", "nah", "not", "dont", "don", "stop", "cancel", "abort",
        "wait", "nevermind", "never", "forget", "skip", "leave",
        # hi
        "nahi", "nahin", "nai", "na", "mat", "ruko", "rehne", "chhodo", "chodo",
        # gu
        "nathi", "nakko", "rehva",
    }
)

# Multi-word phrases that must be checked before single tokens, because their
# individual words are ambiguous or affirmative on their own.
NEGATIVE_PHRASES: tuple[str, ...] = (
    "never mind",
    "no thanks",
    "not now",
    "rehne do",
    "chhod do",
    "mat karo",
    "nahi karo",
    "rehva do",
)

AFFIRMATIVE_PHRASES: tuple[str, ...] = (
    "go ahead",
    "do it",
    "yes please",
    "go for it",
    "kar do",
    "kari nakho",
    "ha karo",
)

_WORD_RE = re.compile(r"[a-z]+")


def interpret(transcript: str) -> Answer:
    """Classify an ASR transcript as yes / no / unclear.

    Negatives win every tie. "yes, but no" and "nahi karo" are both `no`;
    treating a transcript containing both as consent would turn a
    transcription slip into an executed deletion.
    """
    lowered = transcript.strip().lower()
    if not lowered:
        return "unclear"

    for phrase in NEGATIVE_PHRASES:
        if phrase in lowered:
            return "no"

    words = set(_WORD_RE.findall(lowered))
    if words & NEGATIVE:
        return "no"

    for phrase in AFFIRMATIVE_PHRASES:
        if phrase in lowered:
            return "yes"
    if words & AFFIRMATIVE:
        return "yes"
    return "unclear"


def describe(spec: ToolSpec, args: dict[str, Any]) -> str:
    """The sentence spoken before acting.

    Names the tool's effect and its actual arguments, because the user is
    confirming *this* action and cannot see the screen. A prompt that only
    says "are you sure?" gives them nothing to catch a misroute with — which
    is the whole point of the gate.
    """
    if spec.preview is not None:
        try:
            summary = spec.preview(**args).strip()
        except Exception:
            # A broken previewer must not stop the gate from asking. Falling
            # back to the generic wording is worse UX; silently executing
            # would be a security failure, so this path degrades, never skips.
            summary = ""
        if summary:
            return f"{summary.rstrip('.')}. Should I go ahead?"

    if args:
        rendered = ", ".join(f"{k}={v!r}" for k, v in sorted(args.items()))
        return f"{spec.description.rstrip('.')} ({rendered}). Should I go ahead?"
    return f"{spec.description.rstrip('.')} Should I go ahead?"


@dataclass
class PendingConfirmation:
    """One action waiting on a spoken yes."""

    tool: str
    args: dict[str, Any]
    prompt: str
    stage: str | None = None
    attempts: int = 0
    requested_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class ConfirmationResult:
    outcome: Outcome
    message: str
    pending: PendingConfirmation | None = None

    @property
    def should_execute(self) -> bool:
        return self.outcome == "confirmed"


class ConfirmationGate:
    """Holds at most one pending confirmation.

    One, not a queue: a second proposal while one is outstanding replaces it,
    because a user answering "yes" must never be ambiguous about *what* they
    just approved. The replaced action is dropped, not deferred.
    """

    def __init__(self, timeout_s: int = 45, max_attempts: int = 2) -> None:
        self._timeout = timedelta(seconds=timeout_s)
        self._max_attempts = max_attempts
        self._pending: PendingConfirmation | None = None
        self._lock = threading.Lock()

    def configure(self, *, timeout_s: int | None = None, max_attempts: int | None = None) -> None:
        """Sync from `config.security` at bootstrap (see __main__.py)."""
        with self._lock:
            if timeout_s is not None:
                self._timeout = timedelta(seconds=timeout_s)
            if max_attempts is not None:
                self._max_attempts = max_attempts

    @property
    def pending(self) -> PendingConfirmation | None:
        with self._lock:
            return self._pending

    def request(
        self,
        spec: ToolSpec,
        args: dict[str, Any],
        stage: str | None = None,
        now: datetime | None = None,
    ) -> PendingConfirmation:
        """Propose an action and return the confirmation to speak."""
        pending = PendingConfirmation(
            tool=spec.name,
            args=dict(args),
            prompt=describe(spec, args),
            stage=stage,
            requested_at=now or datetime.now(UTC),
        )
        with self._lock:
            self._pending = pending
        return pending

    def cancel(self, reason: str = "Cancelled.") -> ConfirmationResult:
        with self._lock:
            pending = self._pending
            self._pending = None
        if pending is None:
            return ConfirmationResult("none_pending", "There was nothing waiting.")
        return ConfirmationResult("cancelled", reason, pending)

    def resolve(self, transcript: str, now: datetime | None = None) -> ConfirmationResult:
        """Interpret a spoken answer against the pending action.

        The only route to `outcome == "confirmed"`, and it is reachable only
        from an ASR transcript.
        """
        now = now or datetime.now(UTC)
        with self._lock:
            pending = self._pending
            if pending is None:
                return ConfirmationResult("none_pending", "There was nothing waiting.")

            if now - pending.requested_at > self._timeout:
                self._pending = None
                return ConfirmationResult(
                    "expired",
                    f"That confirmation expired, so I didn't {pending.tool.replace('_', ' ')}. "
                    "Ask again if you still want it.",
                    pending,
                )

            answer = interpret(transcript)
            if answer == "yes":
                self._pending = None
                return ConfirmationResult("confirmed", "Okay.", pending)
            if answer == "no":
                self._pending = None
                return ConfirmationResult("cancelled", "Okay, I won't.", pending)

            pending.attempts += 1
            if pending.attempts >= self._max_attempts:
                self._pending = None
                return ConfirmationResult(
                    "cancelled",
                    "I didn't catch a yes, so I've left it alone.",
                    pending,
                )
            return ConfirmationResult(
                "reasked",
                f"Sorry, I need a yes or no. {pending.prompt}",
                pending,
            )
