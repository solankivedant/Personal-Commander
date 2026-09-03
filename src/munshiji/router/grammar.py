"""Stage 1: hassil grammar-template matcher. <10ms, deterministic, zero RAM.

Loads the hassil intent YAML files under ``config/intents/`` (per
``config.router.grammar.dirs``), builds a single hassil ``Intents`` object,
and matches an utterance to ``(intent_name, slots)``. First match wins — this
module has no notion of "second best," that ambiguity is Stage 2's job.

Wildcard captures (``{app}``, ``{level}``, ``{query}``, ...) are detected
automatically by scanning every loaded sentence template for ``{name}``
references, so adding a new ``{foo}`` capture to a YAML file does not require
touching this module. A small set of "special" slots (currently just
``{state}`` for on/off style intents) resolve to a canonical value via a
hassil ``TextSlotList`` instead of being treated as free-text wildcards, so
grammar-stage matches for e.g. ``wifi_toggle`` already carry
``{"state": "on"}`` rather than raw matched text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import hassil
import yaml
from hassil import Intents, SlotList, TextSlotList, WildcardSlotList

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


def _build_special_slot_lists() -> dict[str, SlotList]:
    return {
        "state": TextSlotList.from_tuples(_STATE_VALUES, name="state"),
    }


@dataclass(frozen=True)
class GrammarMatch:
    """Result of a successful Stage 1 match."""

    intent: str
    slots: dict[str, Any] = field(default_factory=dict)
    matched_text: str = ""


class GrammarRouter:
    """Loads hassil grammar templates and matches utterances against them."""

    def __init__(self, dirs: list[Path], language: str = "en") -> None:
        self._language = language
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

        special = _build_special_slot_lists()
        slot_lists: dict[str, SlotList] = {}
        for name in wildcard_names:
            slot_lists[name] = special.get(name, WildcardSlotList(name=name))
        self._slot_lists = slot_lists

    @classmethod
    def from_config_dirs(cls, dirs: list[str], root: Path = REPO_ROOT) -> GrammarRouter:
        """Build a GrammarRouter from the string paths in
        ``config.router.grammar.dirs`` (relative to the repo root)."""
        return cls([root / d for d in dirs])

    def match(self, text: str) -> GrammarMatch | None:
        if self._intents is None:
            return None
        result = hassil.recognize(text, self._intents, slot_lists=self._slot_lists)
        if result is None:
            return None
        slots: dict[str, Any] = {}
        for name, entity in result.entities.items():
            # TextSlotList entries (e.g. "toggle") resolve .value to the
            # canonical output ("on"/"off"); plain wildcards have
            # value == text, so this is safe for both cases.
            slots[name] = entity.value if entity.value is not None else entity.text
        return GrammarMatch(intent=result.intent.name, slots=slots, matched_text=text)
