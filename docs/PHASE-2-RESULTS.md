# Phase 2 results — router accuracy with the real encoder

Closes the three caveats left open at the end of `docs/ROADMAP.md`'s Phase 2
section. Measured on the target laptop (Dell Inspiron 14 7430, i7-1355U, Iris
Xe, 16GB) against the real `intfloat/multilingual-e5-small` weights, not the
deterministic fake encoder CI runs against.

Reproduce everything below with:

```bash
MUNSHIJI_GOLDEN_REAL_ENCODER=1 uv run pytest tests/test_router.py -s
```

---

## Summary

| Suite | What it measures | Result |
|---|---|---|
| `tests/golden/utterances.yaml` | cascade mechanics | 100% tool / 100% args / 100% confirm (87 cases) |
| `tests/golden/paraphrases.yaml` | held-out semantic recall | **92.5% tool / 100% args / 100% confirm** (53 cases) |
| `tests/golden/out_of_domain.yaml` | refusal — knowing when not to answer | **77.8% refused** (18 cases) |

The middle and bottom rows are new. They exist because the top row, on its
own, was not measuring what it was being cited for.

---

## 1. The original golden set could not measure semantic accuracy

Phase 2 shipped with the caveat that "the real `multilingual-e5-small`
accuracy is not yet verified" and that the 100% figure came from a fake
encoder. Re-running the same set with the real weights returns 100% again —
but that number means nothing, and the reason is structural:

**All 62 embedding-stage cases in `utterances.yaml` were verbatim copies of
lines in `config/examples/*.jsonl`.** The query has an exact match in the
index, so cosine similarity is 1.0 and *any* encoder scores 100% — including
`_fake_encoder`, which is word- and character-trigram overlap with no
semantics at all. The set is a good test of cascade mechanics (stage
ordering, thresholding, confirm resolution, slot enrichment) and a null test
of recall.

So `tests/golden/paraphrases.yaml` was added: 53 utterances across en/hi/gu,
none present in the example set and none matchable by any grammar template,
so they can only be answered by Stage 2 actually generalizing. Two always-on
tests (`test_paraphrase_set_is_actually_held_out`,
`test_paraphrase_set_is_not_grammar_matchable`) enforce both properties, so a
future "fix" that pastes a failing paraphrase into the example set fails
loudly instead of quietly recreating the original problem.

### First measurement, and what it exposed

| | tool | args | confirm | en | hi | gu |
|---|---|---|---|---|---|---|
| Initial | 75.5% | 73.6% | **66.7%** | 77.8% | 61.1% | 88.2% |
| After fixes below | **92.5%** | **100%** | **100%** | 83.3% | 94.4% | 100% |

---

## 2. Correctness bug: the embedding stage inherited its arguments

The largest single defect, and invisible to a verbatim golden set.

`EmbeddingMatch` carries the *stored args of the nearest example*. Those args
describe a different sentence that merely means something similar, and
`enrich_slots` passed them straight through. Observed with real weights:

| utterance | nearest example | acted on |
|---|---|---|
| `excel kholo` | `chrome kholo` | opened **Chrome** |
| `outlook par jao` | `word par switch karo` | focused **Word** |
| `wifi ko off kar do` | `wifi chalu karo` | turned wifi **on** |
| `bluetooth on kar do` | `bluetooth band kar do` | turned bluetooth **off** |

A nearest-neighbour hit is evidence about the **intent** and no evidence at
all about the **arguments**. `enrich_slots` now takes `args_from_example`,
which `router.py` sets for embedding matches only, and in that mode every
re-derivable slot is re-derived from the utterance:

- `app` — via a new `extract_app`, and **dropped** rather than inherited when
  the utterance names no app. Acting on no app is recoverable; acting on the
  wrong one is not.
- `state` — via a new `extract_state` (on/off, including `chalu`/`band`).
- `direction` — via the existing `extract_direction`, now overriding rather
  than only filling a gap.

A slot that genuinely cannot be re-derived (the "on" in "get bluetooth going",
the "up" in "the screen is too dark" — meant, but not said) still falls back to
the example's value, which is the best evidence available.

`extract_app` matches on exact word boundaries, **not** rapidfuzz, and that is
deliberate: at the documented cutoff of 75, `WRatio` scores `"out"` against
`"outlook"` at 90 and `"no"` against `"notepad"` at 90, so fuzzy-matching every
token of a free utterance resolves apps nobody named. Fuzzy matching stays
where it is safe — correcting the spelling of a slot the grammar already
captured *as* an app name.

Effect: args 73.6% → 84.9%.

## 3. Coverage: the example set was too thin, especially Hindi

Per `CLAUDE.md` — "the fix is almost always a new grammar template or
embedding example, not a bigger model" — the example set grew from 136 to 294
entries, targeting the observed confusions: `open_app` knew only four apps and
four verbs; `band karo` was pulling `close_app` into `shutdown`; `chalu karo`
was pulling `restart` into `wifi_toggle`; `mute` was losing to `set_volume
down`. The `UP_WORDS`/`DOWN_WORDS` vocabularies also gained the common Indic
intensity words they were missing (`zyada`, `halka`, `ochi`, `dhimi`,
`vadhare`).

Effect: tool 75.5% → 92.5%, hi 61.1% → 94.4%, args → 100%.

**A negative result worth recording:** top-k voting over the index was tried
first as a cheaper fix and is *worse* than single nearest-neighbour at every
k and weighting tested (73.6% → 64–68% on held-out; 100% → 85–98% on the
golden set). With only a handful of examples per intent and unequal counts
between them, voting is dominated by whichever intent has more examples. The
cascade keeps `argmax`. Do not re-try this without first balancing the example
counts per intent.

## 4. Threshold: 0.75 meant the router never refused anything

The most serious finding, and the one no accuracy metric would ever surface —
because it is about the cases where the router should produce *no* answer.

`multilingual-e5-small` is contrastively trained and its cosine range is
compressed. Unrelated text does not score near zero against this index; it
scores **0.78–0.93**. At the shipped threshold of `0.75`, out of 18 utterances
with no Phase 2 tool at all — knowledge questions, reminders, chit-chat —
**zero** fell through to teach mode. Every one resolved to a tool with apparent
confidence:

```
compose a haiku about mangoes   -> minimize_app
meri maa ko phone lagao         -> restart        (call my mother)
aaj mausam kaisa hai            -> set_volume     (how's the weather today)
```

Only the confirmation gate stood between "call my mother" and a reboot — which
is a good demonstration of why `security-and-privacy.md` requires that gate,
and a bad thing to be relying on.

Sweep against the real score distribution (in-domain = the 53 held-out
paraphrases, which must match; out-of-domain = the 18 above, which must not):

| threshold | in-domain answered correctly | out-of-domain refused |
|---|---|---|
| 0.75 (shipped) | 92.5% | **0.0%** |
| 0.80 | 92.5% | 11.1% |
| 0.85 | 92.5% | 55.6% |
| **0.88** | **92.5%** | **77.8%** |
| 0.90 | 83.0% | 88.9% |
| 0.92 | 71.7% | 94.4% |

`router.embeddings.threshold` is now **0.88**. In-domain accuracy is
completely unaffected up to that point — the lowest in-domain score is 0.884 —
so the whole gain is free.

The four residual leakers are all knowledge questions ("is tomorrow a
holiday", "how's the weather"). They are recorded in `out_of_domain.yaml` with
`still_matches: true` rather than hidden, and the test asserts they are
*exactly* the set that leaks: a new leaker fails, and so does a marked one
that starts being refused. Phase 4's knowledge-question route is what should
claim them before Stage 2 ever sees them.

**This threshold is a property of the encoder, not a universal constant.**
Re-run the sweep if the encoder changes.

---

## 5. Grammar: `{level}` and `{direction}` are now constrained slots

The second caveat in the roadmap. `{level}` was an untyped `WildcardSlotList`,
so `"volume {level}"` matched *any* text — `"volume kitna hai"` ("what's the
volume") was claimed by `set_volume` at Stage 1 with `level="kitna hai"`,
never reaching the `get_volume` examples that answer it.

`{level}` is now a hassil `RangeSlotList` bounded by
`config.router.grammar.level_range` (`[0, 100]`, in YAML, not source). hassil
resolves it from digits *and* number words, so "set volume to fifty percent"
keeps its Stage 1 match; only non-numeric text falls through. Direction
phrasings ("volume up"), which previously matched only as junk `{level}`
captures, got their own `{direction}` `TextSlotList` built from
`router/slots.py`'s word sets, so grammar and embeddings cannot drift apart on
what an up/down word is.

The first half of that caveat — `focus_app`'s `"go to {app}"` colliding with
`sleep`'s `"go to sleep"` — was already resolved during Phase 2 integration
(the bare "go to" alternative was dropped); the roadmap note was stale.

Also fixed, surfaced by new stage reporting in the golden runner: `lock_screen`
did not accept `"lock my laptop"` (only `"lock the ..."`), so it was silently
falling to Stage 2 — right answer, wasted latency. The runner now reports
per-case cascade stage, which is how a template over- or under-matching shows
up at all.

---

## Still open after this

- **Cross-script ASR recovery** (roadmap caveat 3) — unchanged and still
  Phase 6. `rapidfuzz` recovers Latin-script mangling ("Chrom" → "chrome") but
  not Devanagari ("क्रोम"); that needs transliteration before fuzzy matching.
- **The held-out set has now been used once for tuning.** Two rounds of example
  additions were driven by its failures, so it is no longer a perfectly
  unbiased estimate. Treat 92.5% as an optimistic bound and refresh the file
  with genuinely unseen paraphrases before the next tuning round.
- **Remaining held-out failures** are fine-grained sense distinctions rather
  than gross errors: `focus_app` vs `open_app` on movement verbs ("jump over
  to outlook"), and `mute` vs `set_volume down`. Both route to a plausible
  neighbouring tool with a safe risk tier.
- **18 out-of-domain cases is a small sample.** The refusal rate is directional,
  not precise. Grow the file as real misses show up.
