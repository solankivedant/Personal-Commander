"""Stage 1: hassil grammar-template matcher. <10ms, deterministic, zero RAM.

Loads the hassil intent YAML files under ``config/intents/`` (per
``config.router.grammar.dirs``), builds a single hassil ``Intents`` object,
and matches an utterance to ``(intent_name, slots)``. First match wins — this
module has no notion of "second best," that ambiguity is Stage 2's job.

Wildcard captures (``{app}``, ``{query}``, ...) are detected automatically by
scanning every loaded sentence template for ``{name}`` references, so adding a
new ``{foo}`` capture to a YAML file does not require touching this module.
A small set of "special" slots are *constrained* instead of being treated as
free-text wildcards, so a grammar-stage match carries a resolved value rather
than raw matched text — and, just as importantly, so a template holding one
cannot swallow an utterance it has no business matching:

- ``{state}`` (on/off intents) -> ``TextSlotList``, resolving to ``"on"``/``"off"``.
- ``{direction}`` (up/down intents) -> ``TextSlotList``, resolving to
  ``"up"``/``"down"`` off the same vocabulary ``router/slots.py`` uses.
- ``{level}`` (volume/brightness percentages) -> ``RangeSlotList`` over
  ``config.router.grammar.level_range``.

The ``{level}`` constraint is load-bearing, not cosmetic. As an untyped
wildcard it matched *any* text, so ``"volume {level}"`` claimed
``"volume kitna hai"`` ("what's the volume") at Stage 1 with
``level="kitna hai"`` — intercepting a question that ``get_volume``'s
embedding examples already covered, and passing junk to a tool that wants an
int. hassil resolves a ``RangeSlotList`` from digits *and* number words, so
"set volume to fifty percent" still matches at Stage 1; only non-numeric text
now falls through to Stage 2, which is the whole point.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import hassil
import yaml
from hassil import Intents, RangeSlotList, SlotList, TextSlotList, WildcardSlotList

from munshiji.router.slots import DOWN_WORDS, UP_WORDS

# Repo root: src/munshiji/router/grammar.py -> parents[3] is the repo root
# (mirrors the parents[2] pattern used in munshiji/config.py, one level
# deeper here because this module lives one package down from config.py).
REPO_ROOT = Path(__file__).resolve().parents[3]

_WILDCARD_RE = re.compile(r"\{(\w+)\}")

# Slot names that resolve to a canonical value instead of raw captured text.
# "toggle" backs on/off style intents (wifi_toggle, bluetooth_toggle); the
# Hindi/Gujarati romanized forms are included directly here because grammar
# matching is exact-string, not embedding-based — unlike the embedding
# example sets, there is no encoder placing "chalu" near "on" for free.
# The slot is named "state" (not "toggle") in sentence templates so the
# captured slot key lines up directly with wifi_toggle/bluetooth_toggle's
# `state` parameter — no renaming step needed between grammar and the tool.
_STATE_VALUES: list[tuple[str, str]] = [
    ("on", "on"),
    ("off", "off"),
    ("chalu", "on"),
    ("band", "off"),
]

# Default {level} range. Overridden from `config.router.grammar.level_range`
# at bootstrap — this pair only exists so a bare GrammarRouter(...) in a test
# or a REPL doesn't need the whole config object to construct.
DEFAULT_LEVEL_RANGE: tuple[int, int] = (0, 100)


def _direction_values() -> list[tuple[str, str]]:
    """{direction} vocabulary, read straight off router/slots.py's word sets
    rather than duplicated here — the two must agree, since `enrich_slots`
    re-derives direction from raw text for the embedding stage and a word
    known to one layer but not the other is exactly the kind of silent
    inconsistency the golden set struggles to surface."""
    return [(word, "up") for word in sorted(UP_WORDS)] + [
        (word, "down") for word in sorted(DOWN_WORDS)
    ]


def _build_special_slot_lists(level_range: tuple[int, int]) -> dict[str, SlotList]:
    low, high = level_range
    return {
        "state": TextSlotList.from_tuples(_STATE_VALUES, name="state"),
        "direction": TextSlotList.from_tuples(_direction_values(), name="direction"),
        "level": RangeSlotList(name="level", start=low, stop=high),
    }


@dataclass(frozen=True)
class GrammarMatch:
    """Result of a successful Stage 1 match."""

    intent: str
    slots: dict[str, Any] = field(default_factory=dict)
    matched_text: str = ""


class GrammarRouter:
    """Loads hassil grammar templates and matches utterances against them."""

    def __init__(
        self,
        dirs: list[Path],
        language: str = "en",
        level_range: tuple[int, int] = DEFAULT_LEVEL_RANGE,
    ) -> None:
        self._language = language
        self._level_range = level_range
        merged_intents: dict[str, Any] = {}
        wildcard_names: set[str] = set()

        for directory in dirs:
            for yaml_path in sorted(directory.glob("*.yaml")):
                with yaml_path.open("r", encoding="utf-8") as f:
                    doc = yaml.safe_load(f) or {}
                intents = doc.get("intents", {})
                for intent_name, intent_body in intents.items():
                    if intent_name in merged_intents:
                        raise ValueError(
                            f"Duplicate intent {intent_name!r} while loading "
                            f"{yaml_path} — intent names must be unique across "
                            "all grammar files."
                        )
                    merged_intents[intent_name] = intent_body
                    for data_block in intent_body.get("data", []):
                        for sentence in data_block.get("sentences", []):
                            wildcard_names.update(_WILDCARD_RE.findall(sentence))

        self._intents: Intents | None
        if merged_intents:
            self._intents = Intents.from_dict(
                {"language": language, "intents": merged_intents}
            )
        else:
            self._intents = None

        special = _build_special_slot_lists(level_range)
        slot_lists: dict[str, SlotList] = {}
        for name in wildcard_names:
            slot_lists[name] = special.get(name, WildcardSlotList(name=name))
        self._slot_lists = slot_lists

    @classmethod
    def from_config_dirs(
        cls,
        dirs: list[str],
        root: Path = REPO_ROOT,
        level_range: tuple[int, int] = DEFAULT_LEVEL_RANGE,
    ) -> GrammarRouter:
        """Build a GrammarRouter from the string paths in
        ``config.router.grammar.dirs`` (relative to the repo root)."""
        return cls([root / d for d in dirs], level_range=level_range)

    def match(self, text: str) -> GrammarMatch | None:
        if self._intents is None:
            return None
        result = hassil.recognize(text, self._intents, slot_lists=self._slot_lists)
        if result is None:
            return None
        slots: dict[str, Any] = {}
        for name, entity in result.entities.items():
            # TextSlotList entries ({state}, {direction}) resolve .value to
            # the canonical output ("on"/"down"/...); a RangeSlotList ({level})
            # resolves to a number; plain wildcards have value == text. So
            # this is safe for all three cases.
            slots[name] = entity.value if entity.value is not None else entity.text
        return GrammarMatch(intent=result.intent.name, slots=slots, matched_text=text)
