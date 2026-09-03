"""Slot extraction/enrichment shared by the grammar and embedding stages.

Scope note (Phase 2): only what the 20 Phase-2 intents actually need —
numbers (volume/brightness levels), up/down and on/off directions, and
fuzzy app-name correction via rapidfuzz for ASR mis-transcriptions like
"Chrom" -> "chrome". Full spaCy NER for dates/times is deferred to Phase 3's
file tools ("move files from last week") — nothing in the Phase 2 intent set
needs it, so spaCy is deliberately not added as a dependency yet. Add it
when files.py's real date-range slots land, not before.

Known limitation: rapidfuzz operates on plain string edit-distance, so it
recovers Latin-script ASR errors ("Chrom") but not cross-script ones
(Devanagari "क्रोम" for "Chrome") — that needs a transliteration step, which
is Indic-language-specialist territory, not this module. Flagging rather
than silently pretending it's covered.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from rapidfuzz import fuzz, process

# architecture-and-router.md specifies "rapidfuzz (cutoff ~75)" directly —
# this isn't an invented magic number, it's the documented spec value, and it
# mirrors config/default.yaml's `router.slots.fuzzy_app_cutoff`. Call
# configure() at bootstrap to sync it from the loaded config.
FUZZY_APP_CUTOFF = 75


def configure(*, fuzzy_app_cutoff: int | None = None) -> None:
    """Sync this module's tunables from `config.router.slots` at bootstrap."""
    global FUZZY_APP_CUTOFF
    if fuzzy_app_cutoff is not None:
        FUZZY_APP_CUTOFF = fuzzy_app_cutoff

# Placeholder known-app list used until Phase 3's tools/apps.py exposes a
# real installed-application index. Callers (router.py, tests) should pass
# `known_apps=` once that index exists instead of relying on this default.
DEFAULT_KNOWN_APPS: tuple[str, ...] = (
    "chrome",
    "firefox",
    "edge",
    "spotify",
    "notepad",
    "word",
    "excel",
    "powerpoint",
    "outlook",
    "whatsapp",
    "visual studio code",
    "code",
    "terminal",
    "calculator",
    "paint",
    "explorer",
    "teams",
    "zoom",
    "vlc",
    "slack",
)

_UP_WORDS = {
    "up", "louder", "brighter", "increase",
    "badha", "badhao", "badhaao", "vadhu", "vadharo", "tez",
}
_DOWN_WORDS = {
    "down", "quieter", "dimmer", "decrease",
    "kam", "km", "dhire", "ochu", "ghatado", "halke",
}
_DIRECTION_WORDS = _UP_WORDS | _DOWN_WORDS

_NUMBER_WORDS: dict[str, int] = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
}

_DIGIT_RE = re.compile(r"\d+")


@dataclass(frozen=True)
class AppMatch:
    """Result of fuzzy-matching a raw captured app name against a known list."""

    name: str
    score: float
    raw: str


def extract_number(text: str) -> int | None:
    """Parse a volume/brightness level out of raw captured text.

    Handles plain digits ("50", "50%") and a small set of common English
    number words ("fifty"). Compound words like "fifty five" sum the parts.
    Devanagari/Gujarati numeral words are not covered yet — the golden set
    keeps hi/gu volume/brightness cases qualitative (direction-based, e.g.
    "kam karo") rather than numeric, so this doesn't block Phase 2.
    """
    if text is None:
        return None
    digits = _DIGIT_RE.search(text)
    if digits:
        return int(digits.group())

    words = re.findall(r"[a-zA-Z]+", text.lower())
    total = 0
    found = False
    for word in words:
        if word in _NUMBER_WORDS:
            total += _NUMBER_WORDS[word]
            found = True
    return total if found else None


def extract_direction(text: str) -> str | None:
    """Scan raw utterance text for an up/down direction keyword.

    Used as a fallback when a grammar template captures a bare alternative
    (e.g. "(louder|quieter)") as plain text rather than a named slot, or when
    an embedding paraphrase match needs its direction re-derived from the
    actual utterance rather than trusted blindly from the nearest example.
    """
    words = set(re.findall(r"[a-zA-Z]+", text.lower()))
    if words & _UP_WORDS:
        return "up"
    if words & _DOWN_WORDS:
        return "down"
    return None


def resolve_app_name(
    raw: str, known_apps: tuple[str, ...] = DEFAULT_KNOWN_APPS
) -> AppMatch | None:
    """Fuzzy-match a raw captured app name against a list of known apps.

    Returns None if nothing clears FUZZY_APP_CUTOFF — callers should fall
    back to the raw text in that case (best-effort) rather than fail
    outright, since the real app registry (Phase 3) may know a name this
    placeholder list doesn't.
    """
    if not raw or not known_apps:
        return None
    result = process.extractOne(
        raw, known_apps, scorer=fuzz.WRatio, score_cutoff=FUZZY_APP_CUTOFF
    )
    if result is None:
        return None
    match_name, score, _index = result
    return AppMatch(name=match_name, score=score, raw=raw)


# Intents whose grammar/embedding slots may need direction re-derived from
# raw text rather than (or in addition to) whatever the matcher captured.
_DIRECTION_INTENTS = {"set_volume", "set_brightness"}
# Intents that carry a free-text `app` slot worth fuzzy-correcting.
_APP_SLOT_INTENTS = {"open_app", "close_app", "focus_app", "minimize_app", "maximize_app"}


def enrich_slots(
    intent: str,
    text: str,
    slots: dict[str, Any],
    known_apps: tuple[str, ...] = DEFAULT_KNOWN_APPS,
) -> dict[str, Any]:
    """Post-process a matcher's raw slots for the handful of Phase 2 intents
    that need it: derive `direction` from keywords when it wasn't captured
    as a named slot, parse `level` into an int, and fuzzy-correct `app`.
    Never overwrites a slot value a matcher already resolved with higher
    confidence (e.g. a `{state}` TextSlotList hit) — this only fills gaps.
    """
    result = dict(slots)

    if intent in _DIRECTION_INTENTS and "direction" not in result:
        direction = extract_direction(text)
        if direction is not None:
            result["direction"] = direction

    if "level" in result and result["level"] is not None:
        parsed = extract_number(str(result["level"]))
        if parsed is not None:
            result["level"] = parsed

    if intent in _APP_SLOT_INTENTS and "app" in result and result["app"]:
        match = resolve_app_name(str(result["app"]), known_apps)
        if match is not None:
            result["app"] = match.name

    return result
