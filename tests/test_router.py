"""Router cascade tests: grammar/embeddings stage selection, confirm
resolution, and the golden-set runner against tests/golden/utterances.yaml.

No network access is available in CI/sandbox for the real ~470MB
multilingual-e5-small weights, so every test here (including the golden-set
run) uses `_fake_encoder`, a small deterministic hashing "embedding" built
from word and character-trigram overlap. It is good enough to validate
cascade *mechanics* (ordering, thresholding, confirm resolution, slot
enrichment) — it is not a claim about real semantic recall, which is
Sentence-Transformers' job in production (see router/embeddings.py's
SentenceTransformerEncoder).
"""

from __future__ import annotations

import os
import re
import zlib
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pytest
import yaml

from munshiji.config import EmbeddingsConfig, GrammarConfig, RouterConfig, SlotsConfig
from munshiji.router.embeddings import (
    DEFAULT_MODEL_NAME,
    EmbeddingIndex,
    Encoder,
    ExampleEntry,
    SentenceTransformerEncoder,
    load_examples,
)
from munshiji.router.grammar import GrammarRouter
from munshiji.router.router import Router
from munshiji.router.slots import (
    enrich_slots,
    extract_app,
    extract_direction,
    extract_number,
    extract_state,
    resolve_app_name,
)
from munshiji.tools.registry import ToolRegistry, ToolSpec

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_INTENTS_DIR = REPO_ROOT / "config" / "intents"
CONFIG_EXAMPLES_DIR = REPO_ROOT / "config" / "examples"
GOLDEN_PATH = REPO_ROOT / "tests" / "golden" / "utterances.yaml"
PARAPHRASE_PATH = REPO_ROOT / "tests" / "golden" / "paraphrases.yaml"
OUT_OF_DOMAIN_PATH = REPO_ROOT / "tests" / "golden" / "out_of_domain.yaml"

# Opt-in switch for the real-weights golden run (see
# test_golden_set_phase2_gates_real_encoder). Off by default so a clean
# CI runner never blocks on a ~470MB model download.
REAL_ENCODER_ENV = "MUNSHIJI_GOLDEN_REAL_ENCODER"

_FAKE_DIM = 512


def _fake_encoder(texts: list[str]) -> npt.NDArray[np.float32]:
    """Deterministic bag-of-words + char-trigram hashing "embedding". Uses
    zlib.crc32 rather than Python's built-in hash() because str hashing is
    randomized per-process (PYTHONHASHSEED) — this must be stable across
    runs and across the two calls (index build, then query) in the same
    test."""
    vectors = np.zeros((len(texts), _FAKE_DIM), dtype=np.float32)
    for row, text in enumerate(texts):
        tokens = re.findall(r"\w+", text.lower())
        for tok in tokens:
            vectors[row, zlib.crc32(f"w:{tok}".encode()) % _FAKE_DIM] += 1.0
            for n in (2, 3):
                for i in range(max(len(tok) - n + 1, 0)):
                    gram = tok[i : i + n]
                    vectors[row, zlib.crc32(f"n:{gram}".encode()) % _FAKE_DIM] += 0.3
    return vectors


# ---------------------------------------------------------------------------
# Stage 1: grammar
# ---------------------------------------------------------------------------


def test_grammar_matches_existing_intent() -> None:
    router = GrammarRouter.from_config_dirs(["config/intents"], root=REPO_ROOT)
    match = router.match("open chrome")
    assert match is not None
    assert match.intent == "open_app"
    assert match.slots == {"app": "chrome"}


def test_grammar_matches_new_intent_with_state_slot() -> None:
    router = GrammarRouter.from_config_dirs(["config/intents"], root=REPO_ROOT)
    match = router.match("wifi off")
    assert match is not None
    assert match.intent == "wifi_toggle"
    assert match.slots == {"state": "off"}


def test_grammar_level_slot_rejects_non_numeric_text() -> None:
    """The regression guard for the Phase 2 `{level}` wildcard bug.

    "volume kitna hai" is Hindi for "what's the volume" — a get_volume
    question. While `{level}` was an untyped WildcardSlotList, "volume
    {level}" matched it at Stage 1 and handed set_volume level="kitna hai",
    so the utterance never reached the embedding examples that answer it.
    """
    router = GrammarRouter.from_config_dirs(["config/intents"], root=REPO_ROOT)
    assert router.match("volume kitna hai") is None
    assert router.match("volume ketlu che") is None
    assert router.match("brightness kitni hai") is None


def test_grammar_level_slot_accepts_digits_and_number_words() -> None:
    """Constraining {level} to a range must not cost real level-setting its
    grammar-stage match — hassil's RangeSlotList resolves number words too."""
    router = GrammarRouter.from_config_dirs(["config/intents"], root=REPO_ROOT)
    digits = router.match("set volume to 50 percent")
    words = router.match("set volume to fifty percent")
    assert digits is not None and digits.intent == "set_volume"
    assert words is not None and words.intent == "set_volume"
    assert int(digits.slots["level"]) == 50
    assert int(words.slots["level"]) == 50


def test_grammar_level_slot_rejects_out_of_range() -> None:
    router = GrammarRouter.from_config_dirs(["config/intents"], root=REPO_ROOT)
    assert router.match("set volume to 150") is None


def test_grammar_level_range_is_configurable() -> None:
    """level_range comes from config.router.grammar.level_range, not a
    constant in source (engineering-standards.md: no behaviour constants)."""
    narrow = GrammarRouter.from_config_dirs(
        ["config/intents"], root=REPO_ROOT, level_range=(0, 10)
    )
    assert narrow.match("volume 5") is not None
    assert narrow.match("volume 50") is None


def test_grammar_direction_slot_resolves_up_down() -> None:
    """Direction phrasings used to "work" only as junk {level} captures
    (set_volume received level="up"); they now carry a resolved direction."""
    router = GrammarRouter.from_config_dirs(["config/intents"], root=REPO_ROOT)
    up = router.match("volume up")
    down = router.match("turn the brightness down")
    assert up is not None and up.intent == "set_volume"
    assert up.slots == {"direction": "up"}
    assert down is not None and down.intent == "set_brightness"
    assert down.slots == {"direction": "down"}


def test_grammar_direction_vocabulary_matches_slots_module() -> None:
    """grammar.py builds {direction} from router/slots.py's word sets, so a
    word added to one is understood by the other. Guards the drift this
    shared-vocabulary arrangement exists to prevent."""
    router = GrammarRouter.from_config_dirs(["config/intents"], root=REPO_ROOT)
    for word in ("tez", "kam"):
        match = router.match(f"volume {word}")
        assert match is not None, word
        assert match.slots["direction"] == extract_direction(word)


def test_grammar_returns_none_on_no_match() -> None:
    router = GrammarRouter.from_config_dirs(["config/intents"], root=REPO_ROOT)
    assert router.match("please compose a haiku about mangoes") is None


def test_grammar_toggle_state_shares_hi_gu_vocabulary() -> None:
    """'chalu'/'band' resolve to on/off directly via the grammar-level
    TextSlotList — a deliberately shared vocabulary across hi/gu, matching
    the architecture rule that system-command words should be shared."""
    router = GrammarRouter.from_config_dirs(["config/intents"], root=REPO_ROOT)
    on_match = router.match("bluetooth chalu")
    off_match = router.match("wifi band")
    assert on_match is not None and on_match.slots == {"state": "on"}
    assert off_match is not None and off_match.slots == {"state": "off"}


# ---------------------------------------------------------------------------
# Stage 2: embeddings
# ---------------------------------------------------------------------------


def _tiny_index() -> EmbeddingIndex:
    entries = [
        ExampleEntry(
            text="turn the volume down",
            intent="set_volume",
            args={"direction": "down"},
            lang="en",
        ),
        ExampleEntry(
            text="make it a bit louder", intent="set_volume", args={"direction": "up"}, lang="en"
        ),
        ExampleEntry(text="lock my laptop please", intent="lock_screen", args={}, lang="en"),
    ]
    index = EmbeddingIndex(_fake_encoder)
    index.build_from_examples(entries)
    return index


def test_embeddings_matches_near_identical_paraphrase() -> None:
    index = _tiny_index()
    match = index.match("make it a bit louder", threshold=0.75)
    assert match is not None
    assert match.intent == "set_volume"
    assert match.args == {"direction": "up"}
    assert match.score > 0.99  # identical text to a corpus entry


def test_embeddings_misses_below_threshold() -> None:
    index = _tiny_index()
    match = index.match("please compose a haiku about mangoes", threshold=0.75)
    assert match is None


def test_embeddings_empty_index_never_matches() -> None:
    index = EmbeddingIndex(_fake_encoder)
    assert index.match("open chrome", threshold=0.75) is None


def test_embedding_index_save_load_round_trip(tmp_path: Path) -> None:
    """Exercises scripts/build_index.py's exact save format, including
    non-ASCII (Gujarati script) example text, which is what makes this a
    meaningful round-trip test rather than a trivial one."""
    index = _tiny_index()
    gu_entry = ExampleEntry(
        text="મારી બેટરી કેટલી છે", intent="battery_status", args={}, lang="gu"
    )
    index.build_from_examples([*index.entries, gu_entry])
    out = tmp_path / "index.npz"
    index.save(out)

    loaded = EmbeddingIndex.load(out, _fake_encoder)
    assert len(loaded.entries) == len(index.entries)
    match = loaded.match("મારી બેટરી કેટલી છે", threshold=0.75)
    assert match is not None
    assert match.intent == "battery_status"


def test_load_examples_reads_jsonl(tmp_path: Path) -> None:
    p = tmp_path / "en.jsonl"
    p.write_text('{"text": "open chrome", "intent": "open_app", "args": {"app": "chrome"}}\n')
    entries = load_examples([p])
    assert len(entries) == 1
    assert entries[0].intent == "open_app"
    assert entries[0].lang == "en"


# ---------------------------------------------------------------------------
# Slot extraction
# ---------------------------------------------------------------------------


def test_extract_number_digits_and_words() -> None:
    assert extract_number("50") == 50
    assert extract_number("50%") == 50
    assert extract_number("fifty") == 50
    assert extract_number("fifty five") == 55
    assert extract_number("no numbers here") is None


def test_extract_direction() -> None:
    assert extract_direction("make it louder") == "up"
    assert extract_direction("turn the volume down") == "down"
    assert extract_direction("nothing relevant") is None


def test_resolve_app_name_recovers_asr_typo() -> None:
    match = resolve_app_name("chrom")
    assert match is not None
    assert match.name == "chrome"


def test_resolve_app_name_no_match_returns_none() -> None:
    # Cross-script input (Devanagari "Chrome") is a documented limitation —
    # rapidfuzz edit-distance doesn't bridge scripts without transliteration.
    assert resolve_app_name("क्रोम") is None


def test_enrich_slots_fills_missing_direction_without_overwriting() -> None:
    filled = enrich_slots("set_volume", "make it louder", {})
    assert filled["direction"] == "up"

    kept = enrich_slots("set_volume", "make it louder", {"direction": "down"})
    assert kept["direction"] == "down"  # never overwrites a resolved slot


def test_enrich_slots_parses_level_and_fuzzes_app() -> None:
    filled = enrich_slots("set_volume", "volume 50", {"level": "50"})
    assert filled["level"] == 50

    filled_app = enrich_slots("open_app", "open chrom", {"app": "chrom"})
    assert filled_app["app"] == "chrome"


def test_extract_app_finds_named_app() -> None:
    assert extract_app("excel kholo") == "excel"
    assert extract_app("put spotify in the background") == "spotify"


def test_extract_app_prefers_longest_name() -> None:
    assert extract_app("open visual studio code") == "visual studio code"


def test_extract_app_is_exact_not_fuzzy() -> None:
    """The reason extract_app does not use rapidfuzz.

    At the documented cutoff of 75, WRatio scores "out" against "outlook" at
    90 and "no" against "notepad" at 90. Running that over every token of a
    free utterance would resolve apps nobody named — and at the embedding
    stage the app arg is taken from the utterance, so a false positive here
    is a wrong window acted on, not a cosmetic slip.
    """
    assert extract_app("get this out of my way") is None
    assert extract_app("no sound at all please") is None
    assert extract_app("minimize that window please") is None


def test_extract_state_reads_on_off_vocabulary() -> None:
    assert extract_state("wifi ko off kar do") == "off"
    assert extract_state("bluetooth on kar do") == "on"
    assert extract_state("disable the wifi") == "off"
    # No state word: None, so the caller can fall back to the example's arg
    # rather than inventing one.
    assert extract_state("get bluetooth going") is None


def test_enrich_slots_embedding_stage_rederives_app_from_utterance() -> None:
    """An embedding match is evidence about the intent, not the arguments.

    With the real encoder, "excel kholo" is nearest to the example "chrome
    kholo" (args {"app": "chrome"}). Inheriting that opens Chrome when the
    user said Excel.
    """
    args = enrich_slots("open_app", "excel kholo", {"app": "chrome"}, args_from_example=True)
    assert args["app"] == "excel"


def test_enrich_slots_embedding_stage_drops_unnamed_app() -> None:
    """If the utterance names no app at all, the nearest example's app is
    dropped, not inherited — acting on no app is recoverable, acting on the
    wrong one is not."""
    args = enrich_slots(
        "minimize_app", "get this out of my way", {"app": "spotify"}, args_from_example=True
    )
    assert "app" not in args


def test_enrich_slots_embedding_stage_rederives_state() -> None:
    """"wifi ko off kar do" matched the example "wifi chalu karo"
    (state=on) and turned wifi on."""
    args = enrich_slots(
        "wifi_toggle", "wifi ko off kar do", {"state": "on"}, args_from_example=True
    )
    assert args["state"] == "off"


def test_enrich_slots_embedding_stage_rederives_direction() -> None:
    args = enrich_slots(
        "set_volume", "awaaz dhimi karo", {"direction": "up"}, args_from_example=True
    )
    assert args["direction"] == "down"


def test_enrich_slots_embedding_stage_keeps_unsayable_arg() -> None:
    """Some args are meant but not said — "the screen is too dark" means
    brightness up, with no direction word in it. There is nothing to
    re-derive, so the example's value is the best evidence available."""
    args = enrich_slots(
        "set_brightness", "the screen is too dark", {"direction": "up"}, args_from_example=True
    )
    assert args["direction"] == "up"


def test_enrich_slots_grammar_stage_trusts_captured_slots() -> None:
    """Mirror image: grammar slots were captured from this utterance, so they
    are authoritative and only get spelling correction."""
    args = enrich_slots("open_app", "open chrom", {"app": "chrom"}, args_from_example=False)
    assert args["app"] == "chrome"


# ---------------------------------------------------------------------------
# Cascade ordering + confirm resolution
# ---------------------------------------------------------------------------


# Mirrors config/default.yaml's router.embeddings.threshold. Kept in step
# with it deliberately: a test suite grading the cascade at a threshold the
# product doesn't ship would measure the wrong router.
DEFAULT_THRESHOLD = 0.88


def _router_config(threshold: float = DEFAULT_THRESHOLD) -> RouterConfig:
    return RouterConfig(
        grammar=GrammarConfig(enabled=True, dirs=["config/intents"]),
        embeddings=EmbeddingsConfig(
            enabled=True, model="fake", threshold=threshold, examples="config/examples"
        ),
        slots=SlotsConfig(fuzzy_app_cutoff=75),
        teach_mode=True,
    )


def _fresh_registry() -> ToolRegistry:
    def _fn(**kwargs: Any) -> str:
        return "ok"

    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="open_app",
            func=_fn,
            tier="local",
            risk="safe",
            tags=(),
            undo=None,
            description="open_app",
            schema={"type": "object", "properties": {}, "required": []},
        )
    )
    registry.register(
        ToolSpec(
            name="shutdown",
            func=_fn,
            tier="local",
            risk="confirm",
            tags=(),
            undo="cancel_shutdown",
            description="shutdown",
            schema={"type": "object", "properties": {}, "required": []},
        )
    )
    return registry


def test_grammar_beats_embeddings_when_both_would_match() -> None:
    """"open chrome" matches grammar directly; an embeddings index seeded
    with the exact same text (which would also match, trivially, at
    similarity 1.0) must never be consulted — first match wins."""
    grammar = GrammarRouter.from_config_dirs(["config/intents"], root=REPO_ROOT)
    embeddings = EmbeddingIndex(_fake_encoder)
    embeddings.build_from_examples(
        [ExampleEntry(text="open chrome", intent="close_app", args={"app": "chrome"}, lang="en")]
    )
    router = Router(grammar, embeddings, _router_config(), registry=_fresh_registry())
    result = router.route("open chrome")
    assert result.stage == "grammar"
    # not close_app, which the (deliberately rigged) embeddings index would give
    assert result.tool == "open_app"


def test_embeddings_used_when_grammar_misses() -> None:
    grammar = GrammarRouter.from_config_dirs(["config/intents"], root=REPO_ROOT)
    embeddings = EmbeddingIndex(_fake_encoder)
    embeddings.build_from_examples(
        [
            ExampleEntry(
                text="fire up firefox", intent="open_app", args={"app": "firefox"}, lang="en"
            )
        ]
    )
    router = Router(grammar, embeddings, _router_config(), registry=_fresh_registry())
    result = router.route("fire up firefox")
    assert result.stage == "embeddings"
    assert result.tool == "open_app"
    assert result.args == {"app": "firefox"}


def test_embedding_stage_does_not_inherit_example_args() -> None:
    """End-to-end version of the enrich_slots tests: the Router must pass
    args_from_example=True for embedding matches. Rigged so the only
    neighbour is an example for a *different* app."""
    grammar = GrammarRouter.from_config_dirs(["config/intents"], root=REPO_ROOT)
    embeddings = EmbeddingIndex(_fake_encoder)
    embeddings.build_from_examples(
        [ExampleEntry(text="chrome kholo", intent="open_app", args={"app": "chrome"}, lang="gu")]
    )
    # Low threshold: _fake_encoder is lexical, and "excel kholo" vs "chrome
    # kholo" shares only one word. The point here is the arg handling once a
    # match is made, not what the fake encoder scores.
    router = Router(grammar, embeddings, _router_config(threshold=0.3), registry=_fresh_registry())
    result = router.route("excel kholo")
    assert result.stage == "embeddings"
    assert result.tool == "open_app"
    assert result.args["app"] == "excel"


def test_falls_through_to_teach_when_nothing_matches() -> None:
    grammar = GrammarRouter.from_config_dirs(["config/intents"], root=REPO_ROOT)
    embeddings = EmbeddingIndex(_fake_encoder)
    router = Router(grammar, embeddings, _router_config(), registry=_fresh_registry())
    result = router.route("please compose a haiku about mangoes")
    assert result.stage == "teach"
    assert result.tool is None
    assert result.confirm_required is None


def test_confirm_required_true_for_confirm_risk_tool() -> None:
    grammar = GrammarRouter.from_config_dirs(["config/intents"], root=REPO_ROOT)
    embeddings = EmbeddingIndex(_fake_encoder)
    router = Router(grammar, embeddings, _router_config(), registry=_fresh_registry())
    result = router.route("shut down the computer")
    assert result.tool == "shutdown"
    assert result.confirm_required is True


def test_confirm_required_false_for_safe_tool() -> None:
    grammar = GrammarRouter.from_config_dirs(["config/intents"], root=REPO_ROOT)
    embeddings = EmbeddingIndex(_fake_encoder)
    router = Router(grammar, embeddings, _router_config(), registry=_fresh_registry())
    result = router.route("open chrome")
    assert result.tool == "open_app"
    assert result.confirm_required is False


def test_confirm_required_is_unknown_not_false_for_unregistered_tool() -> None:
    """The fail-safe case: delete_files matches grammar (files.yaml's
    template exists) but isn't registered in this registry (Phase 3 tool).
    confirm_required must be None, never silently False."""
    grammar = GrammarRouter.from_config_dirs(["config/intents"], root=REPO_ROOT)
    embeddings = EmbeddingIndex(_fake_encoder)
    router = Router(grammar, embeddings, _router_config(), registry=_fresh_registry())
    result = router.route("delete old logs")
    assert result.tool == "delete_files"
    assert result.confirm_required is None


# ---------------------------------------------------------------------------
# Golden-set runner
# ---------------------------------------------------------------------------


def _load_golden_cases() -> list[dict[str, Any]]:
    with GOLDEN_PATH.open("r", encoding="utf-8") as f:
        cases: list[dict[str, Any]] = yaml.safe_load(f)
        return cases


def _golden_registry(_cases: list[dict[str, Any]] | None = None) -> ToolRegistry:
    """The **real** tool registry, not a stand-in.

    Phase 2 graded the golden set against a fake registry that re-declared
    which tools were `risk="confirm"` — a hand-maintained duplicate of the
    thing under test. It passed at 100% while Phase 3's file tools, all three
    of which delete or overwrite, would have been graded as safe.

    Importing the tool modules registers them as a side effect, so the confirm
    gate is now checked against the risk tier each tool actually declares. A
    tool whose `risk=` is wrong fails the golden set, which is the whole point
    of a 100% confirm gate.
    """
    from munshiji.tools import apps, files, system  # noqa: F401  (registration side effects)
    from munshiji.tools.registry import REGISTRY

    return REGISTRY


def test_every_golden_tool_is_registered() -> None:
    """No golden case may name a tool that doesn't exist.

    Without this, a typo in `expect_tool` reads as a routing failure, and a
    deleted tool silently stops being covered. Only `expect_stage: llm` cases
    are exempt — they are xfailed by design until Phase 4.
    """
    registry = _golden_registry()
    missing = sorted(
        {
            case["expect_tool"]
            for case in _load_golden_cases()
            if case.get("expect_stage") != "llm" and registry.get(case["expect_tool"]) is None
        }
    )
    assert not missing, f"golden set names unregistered tools: {missing}"


def test_confirm_risk_matches_golden_expectations() -> None:
    """`expect_confirm` in the golden set and `risk=` in the registry must
    agree — in both directions.

    A case that expects confirmation on a tool the registry calls safe is a
    missed gate. The reverse (a confirm-tier tool with no `expect_confirm`
    case saying so) is how a gate quietly stops being exercised.
    """
    registry = _golden_registry()
    cases = [c for c in _load_golden_cases() if c.get("expect_stage") != "llm"]

    wrong: list[str] = []
    for case in cases:
        spec = registry.get(case["expect_tool"])
        if spec is None:
            continue
        expects = bool(case.get("expect_confirm"))
        is_confirm = spec.risk == "confirm"
        if expects != is_confirm:
            wrong.append(
                f"{case['text']!r}: expect_confirm={expects} but "
                f"{spec.name}.risk={spec.risk!r}"
            )
    assert not wrong, "golden set and registry disagree on confirmation:\n" + "\n".join(wrong)


def test_every_confirm_tool_has_a_golden_case() -> None:
    """Every `risk="confirm"` tool is exercised by at least one
    `expect_confirm` case. Adding a destructive tool without one should fail
    here rather than ship untested."""
    registry = _golden_registry()
    covered = {
        c["expect_tool"]
        for c in _load_golden_cases()
        if c.get("expect_confirm") and c.get("expect_stage") != "llm"
    }
    confirm_tools = {t.name for t in registry.all() if t.risk == "confirm"}
    assert not (confirm_tools - covered), (
        "confirm-risk tools with no expect_confirm golden case: "
        f"{sorted(confirm_tools - covered)}"
    )


def _build_phase2_router(cases: list[dict[str, Any]], encoder: Encoder) -> Router:
    grammar = GrammarRouter.from_config_dirs(["config/intents"], root=REPO_ROOT)
    embeddings = EmbeddingIndex(encoder)
    embeddings.build_from_dirs([CONFIG_EXAMPLES_DIR])
    return Router(grammar, embeddings, _router_config(), registry=_golden_registry(cases))


def _grade_golden_set(encoder: Encoder, label: str) -> dict[str, float]:
    """Run the full golden set through the Phase 2 cascade, grade only
    expect_stage in {grammar, embeddings} (Phase 2's actual cascade), print a
    report, and assert the three CI gates.

    Parameterized by encoder so the same grading logic serves both the
    always-on fake-encoder run and the opt-in real-model run — the two must
    never drift, since a gate that passes under one grader but not the other
    is worthless. expect_stage: llm cases are explicitly reported as skipped
    rather than silently dropped; see utterances.yaml's header comment.
    """
    cases = _load_golden_cases()
    router = _build_phase2_router(cases, encoder)

    scored: list[dict[str, Any]] = []
    skipped_llm: list[dict[str, Any]] = []

    for case in cases:
        if case.get("expect_stage") == "llm":
            skipped_llm.append(case)
            continue
        result = router.route(case["text"], lang=case.get("lang", "en"))
        tool_ok = result.tool == case["expect_tool"]
        expect_args = case.get("expect_args")
        args_ok = True
        if expect_args is not None:
            args_ok = all(result.args.get(k) == v for k, v in expect_args.items())
        expect_confirm = case.get("expect_confirm", False)
        confirm_ok = (result.confirm_required is True) if expect_confirm else True
        expect_stage = case.get("expect_stage")
        stage_ok = expect_stage is None or result.stage == expect_stage
        scored.append(
            {
                **case,
                "actual_tool": result.tool,
                "actual_stage": result.stage,
                "actual_args": result.args,
                "actual_confirm": result.confirm_required,
                "tool_ok": tool_ok,
                "args_ok": args_ok,
                "confirm_ok": confirm_ok,
                "stage_ok": stage_ok,
            }
        )

    total = len(scored)
    tool_matches = sum(c["tool_ok"] for c in scored)
    args_matches = sum(c["args_ok"] for c in scored)
    stage_matches = sum(c["stage_ok"] for c in scored)
    confirm_cases = [c for c in scored if c.get("expect_confirm")]
    confirm_matches = sum(c["confirm_ok"] for c in confirm_cases)

    tool_rate = tool_matches / total if total else 1.0
    args_rate = args_matches / total if total else 1.0
    stage_rate = stage_matches / total if total else 1.0
    confirm_rate = confirm_matches / len(confirm_cases) if confirm_cases else 1.0

    by_lang: dict[str, list[dict[str, Any]]] = {}
    for c in scored:
        by_lang.setdefault(c.get("lang", "en"), []).append(c)

    print(f"\n--- Phase 2 golden-set results [{label}] ---")
    print(f"Scored cases (grammar/embeddings only): {total}")
    print(f"Skipped (expect_stage=llm, Phase 4 not built): {len(skipped_llm)}")
    print(f"Exact tool match: {tool_matches}/{total} = {tool_rate:.1%} (gate >=92%)")
    print(f"Args match:       {args_matches}/{total} = {args_rate:.1%} (gate >=85%)")
    print(
        f"Confirm gate:     {confirm_matches}/{len(confirm_cases)} = {confirm_rate:.1%} "
        "(gate =100%)"
    )
    # Reported, not gated: which cascade stage answered. A case sliding from
    # grammar to embeddings still routes correctly but costs latency and
    # signals a template gap; a case sliding the other way means a template is
    # over-matching — exactly the {level}-wildcard bug this set now guards.
    print(f"Stage as expected: {stage_matches}/{total} = {stage_rate:.1%} (reported, not gated)")
    for lang, lang_cases in sorted(by_lang.items()):
        n = len(lang_cases)
        t = sum(c["tool_ok"] for c in lang_cases)
        a = sum(c["args_ok"] for c in lang_cases)
        print(f"  [{lang}] n={n} tool={t}/{n}={t/n:.1%} args={a}/{n}={a/n:.1%}")

    failures = [c for c in scored if not (c["tool_ok"] and c["args_ok"] and c["confirm_ok"])]
    stage_only = [c for c in scored if c["tool_ok"] and c["args_ok"] and not c["stage_ok"]]
    if failures:
        print("Failing cases:")
        for c in failures:
            print(
                f"  [{c.get('lang')}] {c['text']!r}: expected "
                f"tool={c['expect_tool']} stage={c.get('expect_stage')} "
                f"args={c.get('expect_args')} confirm={c.get('expect_confirm', False)} "
                f"-> got tool={c['actual_tool']} stage={c['actual_stage']} "
                f"args={c['actual_args']} confirm={c['actual_confirm']}"
            )
    if stage_only:
        print("Right answer, unexpected stage (not a gate failure):")
        for c in stage_only:
            print(
                f"  [{c.get('lang')}] {c['text']!r}: expected stage="
                f"{c.get('expect_stage')} -> got {c['actual_stage']}"
            )

    assert confirm_rate == 1.0, "expect_confirm cases are a hard 100% gate — see failures above"
    assert tool_rate >= 0.92, f"exact tool match {tool_rate:.1%} below 92% gate"
    assert args_rate >= 0.85, f"args match {args_rate:.1%} below 85% gate"
    return {
        "tool": tool_rate,
        "args": args_rate,
        "confirm": confirm_rate,
        "stage": stage_rate,
        "total": float(total),
    }


def test_golden_set_phase2_gates() -> None:
    """The always-on run: fake encoder, no network, no model download. Grades
    cascade *mechanics* (ordering, thresholding, confirm resolution, slot
    enrichment), which is what CI can check on any runner."""
    _grade_golden_set(_fake_encoder, "fake encoder")


@pytest.mark.skipif(
    os.environ.get(REAL_ENCODER_ENV) != "1",
    reason=(
        f"set {REAL_ENCODER_ENV}=1 to grade the golden set against the real "
        f"{DEFAULT_MODEL_NAME} weights (~470MB download on first run)"
    ),
)
def test_golden_set_phase2_gates_real_encoder() -> None:
    """The opt-in run: real multilingual-e5-small weights.

    The fake encoder above validates mechanics but says nothing about genuine
    semantic-paraphrase recall — in particular the product's core claim that
    one shared example set covers en/hi/gu because the encoder is
    multilingual. Only this test can substantiate that, so it applies the same
    gates to the same cases with the real model swapped in.

    Kept opt-in rather than always-on because it needs a ~470MB download a
    clean CI runner (or an offline dev box) may not have; a skip is honest,
    a silently fake-graded "100%" is not. Run it after any change to
    config/examples/*.jsonl or the embedding threshold, and record the numbers
    in docs/PHASE-2-RESULTS.md.
    """
    _grade_golden_set(SentenceTransformerEncoder(), "real multilingual-e5-small")


# ---------------------------------------------------------------------------
# Held-out paraphrase set — the semantic half of the suite
# ---------------------------------------------------------------------------


def _load_paraphrase_cases() -> list[dict[str, Any]]:
    with PARAPHRASE_PATH.open("r", encoding="utf-8") as f:
        cases: list[dict[str, Any]] = yaml.safe_load(f)
        return cases


def _example_texts() -> set[str]:
    return {e.text.strip().lower() for e in load_examples(CONFIG_EXAMPLES_DIR.glob("*.jsonl"))}


def test_paraphrase_set_is_actually_held_out() -> None:
    """The paraphrase set is only meaningful if none of it is in the index.

    Runs with no encoder and no network, so it guards the property on every
    CI run — including the runs that skip the real-model test below. Without
    it, the natural way to "fix" a failing paraphrase is to paste it into
    config/examples/*.jsonl, which silently converts the semantic test back
    into the verbatim-lookup test it was written to replace.
    """
    examples = _example_texts()
    leaked = [c["text"] for c in _load_paraphrase_cases() if c["text"].strip().lower() in examples]
    assert not leaked, (
        "these held-out paraphrases were added to config/examples/*.jsonl, which "
        f"destroys their value as a generalization test: {leaked}"
    )


def test_paraphrase_set_is_not_grammar_matchable() -> None:
    """Likewise, a paraphrase that a grammar template can match never reaches
    Stage 2, so it measures nothing about the encoder."""
    grammar = GrammarRouter.from_config_dirs(["config/intents"], root=REPO_ROOT)
    matched = [c["text"] for c in _load_paraphrase_cases() if grammar.match(c["text"]) is not None]
    assert not matched, (
        "these held-out paraphrases are matched at Stage 1, so they never exercise "
        f"the embedding stage they were written for: {matched}"
    )


@pytest.mark.skipif(
    os.environ.get(REAL_ENCODER_ENV) != "1",
    reason=(
        f"set {REAL_ENCODER_ENV}=1 to grade held-out paraphrases against the real "
        f"{DEFAULT_MODEL_NAME} weights (~470MB download on first run)"
    ),
)
def test_paraphrase_set_real_encoder() -> None:
    """Held-out paraphrase recall with the real encoder.

    Deliberately NOT run against `_fake_encoder`: that encoder is word- and
    trigram-overlap by construction, so it has no semantics to generalize
    with and grading it here would produce a meaningless number.

    Thresholds are lower than utterances.yaml's CI gates because this is a
    strictly harder set — every case is unseen phrasing — except the confirm
    gate, which stays at 100%. A `confirm` tool that a paraphrase routes to
    some `safe` tool instead is a missed confirmation gate, and
    .claude/rules/security-and-privacy.md does not soften that for hard
    inputs. These are regression floors against measured behaviour (see
    docs/PHASE-2-RESULTS.md), not aspirations — raise them when the numbers
    justify it, never lower them to unblock a merge.
    """
    cases = _load_paraphrase_cases()
    golden = _load_golden_cases()
    router = _build_phase2_router(golden, SentenceTransformerEncoder())

    scored: list[dict[str, Any]] = []
    for case in cases:
        result = router.route(case["text"], lang=case.get("lang", "en"))
        expect_args = case.get("expect_args")
        scored.append(
            {
                **case,
                "actual_tool": result.tool,
                "actual_args": result.args,
                "actual_stage": result.stage,
                "actual_score": result.score,
                "tool_ok": result.tool == case["expect_tool"],
                "args_ok": (
                    True
                    if expect_args is None
                    else all(result.args.get(k) == v for k, v in expect_args.items())
                ),
                "confirm_ok": (
                    (result.confirm_required is True) if case.get("expect_confirm") else True
                ),
            }
        )

    total = len(scored)
    tool_matches = sum(c["tool_ok"] for c in scored)
    args_matches = sum(c["args_ok"] for c in scored)
    confirm_cases = [c for c in scored if c.get("expect_confirm")]
    confirm_matches = sum(c["confirm_ok"] for c in confirm_cases)

    tool_rate = tool_matches / total
    args_rate = args_matches / total
    confirm_rate = confirm_matches / len(confirm_cases) if confirm_cases else 1.0

    by_lang: dict[str, list[dict[str, Any]]] = {}
    for c in scored:
        by_lang.setdefault(c.get("lang", "en"), []).append(c)

    print("\n--- Held-out paraphrase results [real multilingual-e5-small] ---")
    print(f"Cases: {total} (none present in config/examples/*.jsonl)")
    print(f"Exact tool match: {tool_matches}/{total} = {tool_rate:.1%} (floor >=85%)")
    print(f"Args match:       {args_matches}/{total} = {args_rate:.1%} (floor >=90%)")
    print(
        f"Confirm gate:     {confirm_matches}/{len(confirm_cases)} = {confirm_rate:.1%} "
        "(gate =100%)"
    )
    for lang, lang_cases in sorted(by_lang.items()):
        n = len(lang_cases)
        t = sum(c["tool_ok"] for c in lang_cases)
        print(f"  [{lang}] n={n} tool={t}/{n}={t/n:.1%}")

    failures = [c for c in scored if not (c["tool_ok"] and c["args_ok"] and c["confirm_ok"])]
    if failures:
        print("Failing cases:")
        for c in failures:
            print(
                f"  [{c.get('lang')}] {c['text']!r}: expected tool={c['expect_tool']} "
                f"args={c.get('expect_args')} -> got tool={c['actual_tool']} "
                f"args={c['actual_args']} score={c['actual_score']}"
            )

    assert confirm_rate == 1.0, "expect_confirm is a hard 100% gate — see failures above"
    assert tool_rate >= 0.85, f"held-out tool match {tool_rate:.1%} below 85% floor"
    assert args_rate >= 0.90, f"held-out args match {args_rate:.1%} below 90% floor"


# ---------------------------------------------------------------------------
# Out-of-domain set — does the router know when to say nothing?
# ---------------------------------------------------------------------------


def _load_out_of_domain_cases() -> list[dict[str, Any]]:
    with OUT_OF_DOMAIN_PATH.open("r", encoding="utf-8") as f:
        cases: list[dict[str, Any]] = yaml.safe_load(f)
        return cases


@pytest.mark.skipif(
    os.environ.get(REAL_ENCODER_ENV) != "1",
    reason=(
        f"set {REAL_ENCODER_ENV}=1 to check out-of-domain refusal against the real "
        f"{DEFAULT_MODEL_NAME} weights (~470MB download on first run)"
    ),
)
def test_out_of_domain_utterances_reach_teach_mode() -> None:
    """The complement of every other test here: not "is the answer right?"
    but "does it know it has no answer?".

    This is a property of the *threshold* against the real encoder's score
    distribution, which is why it cannot be graded with `_fake_encoder`. At
    the router's previously shipped threshold of 0.75 it failed completely —
    0/18 refused, because multilingual-e5-small scores unrelated text at
    0.78-0.93 rather than near zero.

    Cases marked `still_matches: true` are known, recorded leakers (all
    knowledge questions, which Phase 4's knowledge route should claim before
    Stage 2 sees them). They are asserted to be *exactly* the set that leaks:
    a new leaker fails the test, and so does a marked one that starts being
    refused, since a stale marker hides a real regression later.
    """
    cases = _load_out_of_domain_cases()
    router = _build_phase2_router(_load_golden_cases(), SentenceTransformerEncoder())

    refused: list[dict[str, Any]] = []
    matched: list[dict[str, Any]] = []
    for case in cases:
        result = router.route(case["text"], lang=case.get("lang", "en"))
        (refused if result.stage == "teach" else matched).append(
            {**case, "tool": result.tool, "stage": result.stage, "score": result.score}
        )

    total = len(cases)
    rate = len(refused) / total
    print("\n--- Out-of-domain refusal [real multilingual-e5-small] ---")
    print(f"Threshold: {DEFAULT_THRESHOLD}")
    print(f"Correctly fell through to teach mode: {len(refused)}/{total} = {rate:.1%}")
    if matched:
        print("Leaked into a tool call:")
        for c in matched:
            expected = " (known, marked still_matches)" if c.get("still_matches") else " (NEW)"
            print(f"  {c['score']:.3f} [{c.get('lang')}] {c['text']!r} -> {c['tool']}{expected}")

    unexpected = [c["text"] for c in matched if not c.get("still_matches")]
    assert not unexpected, (
        "these out-of-domain utterances resolved to a Phase 2 tool instead of "
        f"falling through to teach mode: {unexpected}"
    )

    stale = [c["text"] for c in refused if c.get("still_matches")]
    assert not stale, (
        "these are marked `still_matches: true` but are now correctly refused — "
        f"drop the marker so it keeps guarding: {stale}"
    )


@pytest.mark.parametrize(
    "case",
    [c for c in _load_golden_cases() if c.get("expect_stage") == "llm"],
    ids=lambda c: c["text"],
)
def test_golden_set_llm_cases_xfail_phase4_not_built(case: dict[str, Any]) -> None:
    """Documents (rather than silently drops) the files.yaml cases that
    require Stage 3 (LLM escalation, brain/), which is Phase 4 and does not
    exist in this codebase yet. Marked xfail, not deleted or force-passed —
    see .claude/skills/golden-test/SKILL.md: never route a failing case to
    the LLM as a shortcut, and never quietly stop testing it either."""
    pytest.xfail(f"Stage 3 (LLM, Phase 4) not implemented yet: {case['text']!r}")
