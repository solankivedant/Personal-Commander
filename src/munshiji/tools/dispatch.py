"""Text-in / speech-out command dispatch: route -> registry -> confirm gate
-> execute, with every step published on the event bus.

Extracted from `wake/fsm.py`, which still owns the audio-driven states but
now carries transcripts here instead of implementing the decision itself.
The extraction exists because the voice loop is no longer the only way a
command arrives: the Control Center (`ui/server.py`) sends typed commands
from the local UI, and both paths must make *exactly* the same safety
decisions. Two copies of "does this need confirmation?" is precisely the
drift `.claude/rules/security-and-privacy.md` exists to prevent, so there is
one copy, here.

What is deliberately not here: any way to approve an action. `route()` can
propose a confirm-tier action and `resolve_confirmation()` carries a human
answer to the gate, but the decision itself stays in `security/confirm.py`,
reachable only from human input (a transcript, or what the user typed or
clicked in the local UI) and never from a tool result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from munshiji.bus import EventBus
from munshiji.security.confirm import ConfirmationGate
from munshiji.tools.registry import REGISTRY, ToolRegistry, ToolSpec

if TYPE_CHECKING:
    from munshiji.router.router import Router

Outcome = Literal[
    "executed",
    "confirm_requested",
    "cancelled",
    "refused",
    "needs_more_info",
    "unmatched",
]

# Spoken prompts for the slots a user can actually be asked about. Anything
# not named here falls back to the parameter name, which is at least honest.
SLOT_QUESTIONS: dict[str, str] = {
    "query": "which files you mean",
    "destination": "where to put them",
    "source": "which folder to take them from",
    "new_name": "what to call it",
    "folder": "which folder",
    "app": "which app",
}


@dataclass(frozen=True)
class DispatchResult:
    """What happened, and what to say about it.

    `speech` is the only field the voice loop needs; the rest is what the
    Control Center renders — which stage decided, which tool ran, with what
    arguments — so the UI shows the real decision rather than a description
    of one.
    """

    speech: str
    outcome: Outcome
    tool: str | None = None
    stage: str | None = None
    args: dict[str, Any] = field(default_factory=dict)
    risk: str | None = None
    tier: str | None = None
    score: float | None = None

    @property
    def awaiting_confirmation(self) -> bool:
        return self.outcome == "confirm_requested"


def missing_required_args(spec: ToolSpec, args: dict[str, object]) -> list[str]:
    """Required schema parameters the route didn't supply.

    Guards the seam between a router that produces whatever slots it could
    extract and a tool with a fixed signature. Without it, a partially
    resolved route reaches `spec(**args)` and dies as a TypeError the user
    hears as "something went wrong".
    """
    required = spec.schema.get("required", [])
    if not isinstance(required, list):
        return []
    return [name for name in required if name not in args or args[name] in (None, "")]


def ask_for_missing(spec: ToolSpec, missing: list[str]) -> str:
    wanted = " and ".join(SLOT_QUESTIONS.get(name, name) for name in missing)
    return f"I can do that, but I need you to tell me {wanted}."


class CommandDispatcher:
    """Turns one utterance (spoken or typed) into one action or one question.

    Holds no state of its own — the pending confirmation lives in the gate,
    so the voice loop and the Control Center can share one dispatcher and one
    gate without either being able to answer the other's question by
    accident.
    """

    def __init__(
        self,
        router: Router | None,
        bus: EventBus,
        registry: ToolRegistry = REGISTRY,
        confirm_gate: ConfirmationGate | None = None,
    ) -> None:
        self._router = router
        self._bus = bus
        self._registry = registry
        self._confirm_gate = confirm_gate

    @property
    def registry(self) -> ToolRegistry:
        return self._registry

    @property
    def awaiting_confirmation(self) -> bool:
        return self._confirm_gate is not None and self._confirm_gate.pending is not None

    @property
    def pending_prompt(self) -> str | None:
        pending = self._confirm_gate.pending if self._confirm_gate is not None else None
        return pending.prompt if pending is not None else None

    def handle(self, text: str) -> DispatchResult:
        """Route this utterance, or read it as the answer to the pending one.

        A pending confirmation takes precedence over routing: the utterance
        is an answer, not a new command. Routing it instead would let "yes"
        match some unrelated intent while the proposed action sat unanswered.
        """
        if self.awaiting_confirmation:
            return self.resolve_confirmation(text)
        return self.route(text)

    def route(self, text: str) -> DispatchResult:
        """Run the router cascade, then either execute or ask.

        Anything the registry reports as needing confirmation — and anything
        whose risk it cannot report, i.e. an unregistered tool — goes to the
        gate rather than to the tool. Only an explicit `confirm_required is
        False` executes directly, so "unknown" fails the same way as "yes,
        confirm" (security-and-privacy.md).
        """
        if self._router is None or not text:
            return DispatchResult(speech=text, outcome="unmatched")

        route = self._router.route(text)
        self._bus.publish(
            "router.route",
            {
                "text": text,
                "tool": route.tool,
                "stage": route.stage,
                "args": route.args,
                "score": route.score,
                "confirm_required": route.confirm_required,
            },
        )

        if route.tool is None:
            return DispatchResult(
                speech="I don't know how to do that yet.",
                outcome="unmatched",
                stage=route.stage,
                score=route.score,
            )

        spec = self._registry.get(route.tool)
        if spec is None:
            self._bus.publish(
                "tool.refused",
                {"tool": route.tool, "reason": "not_registered", "stage": route.stage},
            )
            return DispatchResult(
                speech=f"I don't have a way to do that yet ({route.tool}).",
                outcome="refused",
                tool=route.tool,
                stage=route.stage,
                args=dict(route.args),
                score=route.score,
            )

        missing = missing_required_args(spec, route.args)
        if missing:
            # The route identified the intent but not everything the tool
            # needs — typically an embedding match on a file command, whose
            # free-text slots router/slots.py deliberately refuses to inherit
            # from the nearest example. Asking is the only correct move here:
            # calling the tool would raise, and guessing would act on the
            # wrong files.
            self._bus.publish(
                "tool.refused",
                {
                    "tool": spec.name,
                    "reason": "missing_args",
                    "missing": missing,
                    "stage": route.stage,
                },
            )
            return DispatchResult(
                speech=ask_for_missing(spec, missing),
                outcome="needs_more_info",
                tool=spec.name,
                stage=route.stage,
                args=dict(route.args),
                risk=spec.risk,
                tier=spec.tier,
                score=route.score,
            )

        if route.confirm_required is not False:
            return self.request_confirmation(spec, route.args, route.stage, score=route.score)

        return self.execute(spec, route.args, route.stage, score=route.score)

    def request_confirmation(
        self,
        spec: ToolSpec,
        args: dict[str, object],
        stage: str | None,
        score: float | None = None,
    ) -> DispatchResult:
        """Propose a confirm-tier action and hand back the prompt to speak."""
        if self._confirm_gate is None:
            # No gate wired (e.g. a Phase 1 style test rig). Describing the
            # action and stopping is the only safe answer — never execute.
            self._bus.publish(
                "tool.refused",
                {"tool": spec.name, "reason": "no_confirm_gate", "stage": stage},
            )
            return DispatchResult(
                speech=f"That needs confirmation, which isn't set up right now: {spec.name}.",
                outcome="refused",
                tool=spec.name,
                stage=stage,
                args=dict(args),
                risk=spec.risk,
                tier=spec.tier,
                score=score,
            )

        pending = self._confirm_gate.request(spec, dict(args), stage=stage)
        self._bus.publish(
            "confirm.requested",
            {"tool": spec.name, "args": pending.args, "stage": stage, "prompt": pending.prompt},
        )
        return DispatchResult(
            speech=pending.prompt,
            outcome="confirm_requested",
            tool=spec.name,
            stage=stage,
            args=dict(pending.args),
            risk=spec.risk,
            tier=spec.tier,
            score=score,
        )

    def resolve_confirmation(self, text: str) -> DispatchResult:
        """Interpret this utterance as the answer to the pending action.

        `text` must come from a human — an ASR transcript, or what the user
        typed or clicked in the local Control Center. There is deliberately
        no caller-supplied "approved" flag: the words go to the gate and the
        gate decides, so nothing but a person can reach `confirmed`.
        """
        if self._confirm_gate is None:
            return DispatchResult(speech="There was nothing waiting.", outcome="refused")

        result = self._confirm_gate.resolve(text)
        pending = result.pending
        self._bus.publish(
            "confirm.resolved",
            {
                "tool": pending.tool if pending else None,
                "outcome": result.outcome,
                "answer_text": text,
                "stage": pending.stage if pending else None,
            },
        )

        if not result.should_execute or pending is None:
            if result.outcome != "confirmed" and pending is not None:
                self._bus.publish(
                    "tool.refused",
                    {"tool": pending.tool, "reason": result.outcome, "stage": pending.stage},
                )
            # "reasked" leaves the proposal standing, so the caller must keep
            # treating the next utterance as an answer — report it as such.
            outcome: Outcome = "confirm_requested" if result.outcome == "reasked" else "cancelled"
            return DispatchResult(
                speech=result.message,
                outcome=outcome,
                tool=pending.tool if pending else None,
                stage=pending.stage if pending else None,
                args=dict(pending.args) if pending else {},
            )

        spec = self._registry.get(pending.tool)
        if spec is None:
            return DispatchResult(
                speech=f"I don't have a way to do that any more ({pending.tool}).",
                outcome="refused",
                tool=pending.tool,
                stage=pending.stage,
            )
        return self.execute(spec, pending.args, pending.stage)

    def execute(
        self,
        spec: ToolSpec,
        args: dict[str, object],
        stage: str | None,
        score: float | None = None,
    ) -> DispatchResult:
        """Run a tool and publish the result for the audit log."""
        try:
            result = spec(**args)
        except Exception as exc:
            # Tools already catch their own execution errors and return a
            # readable string (engineering-standards.md); this guards only
            # the integration seam — e.g. router-extracted args that don't
            # match the tool's actual parameters.
            result = f"Something went wrong trying to do that: {exc}"
        self._bus.publish(
            "tool.executed",
            {
                "tool": spec.name,
                "args": args,
                "stage": stage,
                "result": result,
                "risk": spec.risk,
                "tier": spec.tier,
            },
        )
        return DispatchResult(
            speech=result,
            outcome="executed",
            tool=spec.name,
            stage=stage,
            args=dict(args),
            risk=spec.risk,
            tier=spec.tier,
            score=score,
        )
