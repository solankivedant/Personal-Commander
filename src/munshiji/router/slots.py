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

# Public because router/grammar.py builds its {direction} TextSlotList off
# these same two sets. Grammar and embedding stages must agree on what counts
# as an up/down word — if grammar resolves "tez" to "up" but enrich_slots
# doesn't (or vice versa), the same utterance gets a different `direction`
# depending only on which stage happened to catch it.
UP_WORDS = {
    "up", "louder", "brighter", "increase", "raise", "higher",
    "badha", "badhao", "badhaao", "badhari", "vadhu", "vadhare", "vadhari",
    "vadharo", "tez", "zyada", "oonchi", "motho",
}
DOWN_WORDS = {
    "down", "quieter", "dimmer", "decrease", "lower", "reduce",
    "kam", "km", "dhire", "dhimi", "dhima", "halka", "halki", "halke",
    "ochu", "ochi", "ghata", "ghatao", "ghatado",
}
DIRECTION_WORDS = UP_WORDS | DOWN_WORDS

# on/off vocabulary for wifi_toggle / bluetooth_toggle. Mirrors the {state}
# TextSlotList in router/grammar.py, extended with the verbs that only ever
# show up in free-text paraphrases ("disable the wifi") and never in a
# grammar template. Same contract as UP_WORDS/DOWN_WORDS: both stages must
# agree on what a state word is.
ON_WORDS = {
    "on", "enable", "enabled", "connect", "chalu", "shuru",
}
OFF_WORDS = {
    "off", "disable", "disabled", "disconnect", "band", "bandh",
}

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
    if words & UP_WORDS:
        return "up"
    if words & DOWN_WORDS:
        return "down"
    return None


def extract_state(text: str) -> str | None:
    """Scan raw utterance text for an on/off state keyword.

    Same role as `extract_direction`, for the toggle intents. Returns None
    when the utterance names no state — "get bluetooth going" means "on" but
    contains no state word, and inferring one from nothing would be worse
    than deferring to what the embedding match supplied.
    """
    words = set(re.findall(r"[a-zA-Z]+", text.lower()))
    if words & OFF_WORDS:
        return "off"
    if words & ON_WORDS:
        return "on"
    return None


def extract_app(text: str, known_apps: tuple[str, ...] = DEFAULT_KNOWN_APPS) -> str | None:
    """Find a known application name inside a free-text utterance.

    Deliberately exact (word-boundary) matching, NOT rapidfuzz. Fuzzy
    matching is safe on a grammar-captured `{app}` slot, where the captured
    span is already known to *be* an app name and only its spelling is in
    doubt. Run over every token of a free utterance it is actively harmful:
    at the documented cutoff of 75, rapidfuzz's WRatio scores "out" against
    "outlook" at 90 and "no" against "notepad" at 90, so "get this out of my
    way" would resolve an app the user never named.

    Longest name first, so "visual studio code" wins over "code".
    """
    if not text or not known_apps:
        return None
    lowered = text.lower()
    for app in sorted(known_apps, key=len, reverse=True):
        if re.search(rf"\b{re.escape(app.lower())}\b", lowered):
            return app
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
# Intents carrying an on/off `state` slot.
_STATE_SLOT_INTENTS = {"wifi_toggle", "bluetooth_toggle"}

# Free-text slots on the Phase 3 file intents. Unlike `app`, `state` and
# `direction`, these cannot be re-derived from the utterance by any lookup —
# "which files" and "to where" are open-ended strings, and recovering them
# needs either a grammar template (which captures them from *this* sentence)
# or Phase 4's escalation.
#
# So at the embedding stage they are dropped rather than inherited. The
# alternative is strictly worse: a nearest-example hit for "move my photos to
# Pictures" would arrive carrying the example's own args and move somebody's
# PDFs to Documents instead. Dropping them makes the route arrive with its
# required args missing, which the caller reports as "tell me which files" —
# an honest question rather than a confident wrong action.
_UNDERIVABLE_TEXT_SLOTS = frozenset({"query", "source", "destination", "new_name", "folder"})


def enrich_slots(
    intent: str,
    text: str,
    slots: dict[str, Any],
    known_apps: tuple[str, ...] = DEFAULT_KNOWN_APPS,
    *,
    args_from_example: bool = False,
) -> dict[str, Any]:
    """Post-process a matcher's raw slots for the handful of Phase 2 intents
    that need it: derive `direction` from keywords when it wasn't captured as
    a named slot, parse `level` into an int, and fuzzy-correct `app`.

    `args_from_example` distinguishes the two stages, and the distinction is
    a correctness one, not a tuning knob:

    - **Grammar (False).** Slots were captured from *this* utterance. They
      are authoritative; this function only fills gaps and fixes spelling.
    - **Embeddings (True).** `slots` did not come from this utterance at all
      — they are the stored args of the nearest *example*, which is a
      different sentence that merely means something similar. A nearest-
      neighbour match is evidence about the **intent** and no evidence at
      all about the **arguments**. Inheriting them produces confidently
      wrong actions: with the real multilingual-e5-small, "excel kholo"
      matched the example "chrome kholo" and opened Chrome; "wifi ko off kar
      do" matched "wifi chalu karo" and turned wifi *on*. So in this mode
      every re-derivable slot is re-derived from the utterance, and an `app`
      the utterance does not name is **dropped** rather than inherited —
      acting on no app is recoverable, acting on the wrong one is not.

    A slot that genuinely cannot be re-derived (the "on" in "get bluetooth
    going", the "up" in "the screen is too dark" — meant, but not said)
    falls back to the example's value, which is the best evidence available.

    The exception is `_UNDERIVABLE_TEXT_SLOTS` — the open-ended file slots,
    which are dropped outright in this mode rather than inherited. No lookup
    can recover "which files" from an arbitrary sentence, and a
    plausible-looking wrong value on a file mutation is the most damaging
    thing this function could produce.
    """
    result = dict(slots)

    if intent in _DIRECTION_INTENTS:
        direction = extract_direction(text)
        if direction is not None and (args_from_example or "direction" not in result):
            result["direction"] = direction

    if intent in _STATE_SLOT_INTENTS and args_from_example:
        state = extract_state(text)
        if state is not None:
            result["state"] = state

    if "level" in result and result["level"] is not None:
        parsed = extract_number(str(result["level"]))
        if parsed is not None:
            result["level"] = parsed

    if args_from_example:
        for slot in _UNDERIVABLE_TEXT_SLOTS:
            result.pop(slot, None)

    if intent in _APP_SLOT_INTENTS:
        if args_from_example:
            spoken_app = extract_app(text, known_apps)
            if spoken_app is not None:
                result["app"] = spoken_app
            else:
                result.pop("app", None)
        elif result.get("app"):
            match = resolve_app_name(str(result["app"]), known_apps)
            if match is not None:
                result["app"] = match.name

    return result
