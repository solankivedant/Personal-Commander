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

import re
import zlib
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pytest
import yaml

from munshiji.config import EmbeddingsConfig, GrammarConfig, RouterConfig, SlotsConfig
from munshiji.router.embeddings import EmbeddingIndex, ExampleEntry, load_examples
from munshiji.router.grammar import GrammarRouter
from munshiji.router.router import Router
from munshiji.router.slots import enrich_slots, extract_direction, extract_number, resolve_app_name
from munshiji.tools.registry import ToolRegistry, ToolSpec

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_INTENTS_DIR = REPO_ROOT / "config" / "intents"
CONFIG_EXAMPLES_DIR = REPO_ROOT / "config" / "examples"
GOLDEN_PATH = REPO_ROOT / "tests" / "golden" / "utterances.yaml"

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


# ---------------------------------------------------------------------------
# Cascade ordering + confirm resolution
# ---------------------------------------------------------------------------


def _router_config(threshold: float = 0.75) -> RouterConfig:
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


def _phase2_fake_registry(cases: list[dict[str, Any]]) -> ToolRegistry:
    """Fake registry standing in for the real tools/system.py + tools/apps.py
    (owned by a parallel workstream, not imported here). Risk is set exactly
    per the spec this task was given: shutdown/restart are risk=confirm,
    every other Phase 2 tool is safe. Phase 3's file tools are deliberately
    left unregistered — that gap is what test_confirm_required_is_unknown_*
    above exercises directly, and is why files.yaml cases route to
    confirm_required=None rather than a real answer."""

    def _fn(**kwargs: Any) -> str:
        return "ok"

    confirm_tools = {"shutdown", "restart"}
    registry = ToolRegistry()
    seen: set[str] = set()
    for case in cases:
        name = case["expect_tool"]
        if case.get("expect_stage") == "llm" or name in seen:
            continue
        seen.add(name)
        registry.register(
            ToolSpec(
                name=name,
                func=_fn,
                tier="local",
                risk="confirm" if name in confirm_tools else "safe",
                tags=(),
                undo=None,
                description=name,
                schema={"type": "object", "properties": {}, "required": []},
            )
        )
    return registry


def _build_phase2_router(cases: list[dict[str, Any]]) -> Router:
    grammar = GrammarRouter.from_config_dirs(["config/intents"], root=REPO_ROOT)
    embeddings = EmbeddingIndex(_fake_encoder)
    embeddings.build_from_dirs([CONFIG_EXAMPLES_DIR])
    return Router(grammar, embeddings, _router_config(), registry=_phase2_fake_registry(cases))


def test_golden_set_phase2_gates() -> None:
    """Runs the full golden set, grades only expect_stage in {grammar,
    embeddings} (Phase 2's actual cascade), and explicitly reports
    expect_stage: llm cases as skipped rather than silently dropping them —
    see the module docstring and utterances.yaml's header comment."""
    cases = _load_golden_cases()
    router = _build_phase2_router(cases)

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
            }
        )

    total = len(scored)
    tool_matches = sum(c["tool_ok"] for c in scored)
    args_matches = sum(c["args_ok"] for c in scored)
    confirm_cases = [c for c in scored if c.get("expect_confirm")]
    confirm_matches = sum(c["confirm_ok"] for c in confirm_cases)

    tool_rate = tool_matches / total if total else 1.0
    args_rate = args_matches / total if total else 1.0
    confirm_rate = confirm_matches / len(confirm_cases) if confirm_cases else 1.0

    by_lang: dict[str, list[dict[str, Any]]] = {}
    for c in scored:
        by_lang.setdefault(c.get("lang", "en"), []).append(c)

    print("\n--- Phase 2 golden-set results ---")
    print(f"Scored cases (grammar/embeddings only): {total}")
    print(f"Skipped (expect_stage=llm, Phase 4 not built): {len(skipped_llm)}")
    print(f"Exact tool match: {tool_matches}/{total} = {tool_rate:.1%} (gate >=92%)")
    print(f"Args match:       {args_matches}/{total} = {args_rate:.1%} (gate >=85%)")
    print(
        f"Confirm gate:     {confirm_matches}/{len(confirm_cases)} = {confirm_rate:.1%} "
        "(gate =100%)"
    )
    for lang, lang_cases in sorted(by_lang.items()):
        n = len(lang_cases)
        t = sum(c["tool_ok"] for c in lang_cases)
        a = sum(c["args_ok"] for c in lang_cases)
        print(f"  [{lang}] n={n} tool={t}/{n}={t/n:.1%} args={a}/{n}={a/n:.1%}")

    failures = [c for c in scored if not (c["tool_ok"] and c["args_ok"] and c["confirm_ok"])]
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

    assert confirm_rate == 1.0, "expect_confirm cases are a hard 100% gate — see failures above"
    assert tool_rate >= 0.92, f"exact tool match {tool_rate:.1%} below 92% gate"
    assert args_rate >= 0.85, f"args match {args_rate:.1%} below 85% gate"


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
