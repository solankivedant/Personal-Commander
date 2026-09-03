"""Cascade orchestration: grammar -> embeddings -> LLM -> teach mode, first
match wins. The core IP (L3).

Stage 3 (LLM escalation) is Phase 4 and does not exist in this codebase yet
— per .claude/rules/architecture-and-router.md, this module falls straight
through past it rather than adding a shortcut or a stub that pretends to
decide anything. Stage 4 (teach mode) is *signalled* here (stage="teach")
but the actual "ask the user, then append the example" flow lives in
router/teach.py and the voice loop that will call it — this module's job
ends at "nothing else matched, hand it to teach mode."

Confirm resolution is intentionally fail-safe: if a route resolves to a tool
name that isn't in the registry yet (e.g. files.py's Phase-3 tools),
`confirm_required` is `None` ("unknown"), never `False`. A caller must treat
`None` as "do not skip confirmation," the same as `True` — silently
defaulting an unregistered tool to "safe" would be exactly the missed-
confirmation-gate bug security-and-privacy.md calls a correctness bug.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from munshiji.config import RouterConfig
from munshiji.router.embeddings import EmbeddingIndex
from munshiji.router.grammar import GrammarRouter
from munshiji.router.slots import DEFAULT_KNOWN_APPS, enrich_slots
from munshiji.tools.registry import REGISTRY, ToolRegistry

Stage = Literal["grammar", "embeddings", "teach"]


@dataclass(frozen=True)
class RouteResult:
    """What the cascade decided, and what a caller needs to know before
    acting on it."""

    tool: str | None
    args: dict[str, Any]
    stage: Stage | None
    # True/False = registry has an answer. None = tool isn't registered yet
    # (or nothing matched) — treat as "confirmation required" defensively.
    confirm_required: bool | None
    matched_text: str = ""
    score: float | None = None
    lang: str | None = None


class Router:
    """First-match-wins cascade over Stage 1 (grammar) and Stage 2
    (embeddings), with graceful fallthrough to teach mode."""

    def __init__(
        self,
        grammar: GrammarRouter,
        embeddings: EmbeddingIndex,
        config: RouterConfig,
        registry: ToolRegistry = REGISTRY,
        known_apps: tuple[str, ...] = DEFAULT_KNOWN_APPS,
    ) -> None:
        self._grammar = grammar
        self._embeddings = embeddings
        self._config = config
        self._registry = registry
        self._known_apps = known_apps

    def route(self, text: str, lang: str = "en") -> RouteResult:
        if self._config.grammar.enabled:
            grammar_match = self._grammar.match(text)
            if grammar_match is not None:
                args = enrich_slots(
                    grammar_match.intent, text, grammar_match.slots, self._known_apps
                )
                return self._finalize(grammar_match.intent, args, "grammar", text, lang=lang)

        if self._config.embeddings.enabled:
            embedding_match = self._embeddings.match(text, self._config.embeddings.threshold)
            if embedding_match is not None:
                args = enrich_slots(
                    embedding_match.intent, text, embedding_match.args, self._known_apps
                )
                return self._finalize(
                    embedding_match.intent,
                    args,
                    "embeddings",
                    text,
                    score=embedding_match.score,
                    lang=lang,
                )

        # Stage 3 (LLM, brain/) — Phase 4, does not exist. Fall through.

        if self._config.teach_mode:
            return RouteResult(
                tool=None,
                args={},
                stage="teach",
                confirm_required=None,
                matched_text=text,
                lang=lang,
            )

        return RouteResult(
            tool=None, args={}, stage=None, confirm_required=None, matched_text=text, lang=lang
        )

    def _finalize(
        self,
        tool_name: str,
        args: dict[str, Any],
        stage: Stage,
        text: str,
        score: float | None = None,
        lang: str | None = None,
    ) -> RouteResult:
        spec = self._registry.get(tool_name)
        confirm_required: bool | None
        if spec is None:
            confirm_required = None
        else:
            confirm_required = spec.risk == "confirm"
        return RouteResult(
            tool=tool_name,
            args=args,
            stage=stage,
            confirm_required=confirm_required,
            matched_text=text,
            score=score,
            lang=lang,
        )
