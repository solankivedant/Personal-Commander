---
name: golden-test
description: Run and interpret Munshiji's golden test set (tests/golden/utterances.yaml) — the mandatory regression check for the router. Use after any change to a grammar file, embedding examples, the embedding index, a prompt, or a model, and whenever asked to check routing accuracy or "did this break anything".
---

# Running the golden test set

Source of the standard: `munshiji-full-report.md` §5.2 and §19.2.

## Why this exists

The failure mode this catches is silent regression, not crashes: you tweak a
system prompt or add an embedding example, the model quietly stops selecting
the right tool for some other case, and nothing errors. The golden set is the
only thing that surfaces this, so treat "I didn't have time to run it" as
equivalent to "I didn't test this."

## What it checks

The suite is three files, and they answer three different questions. Running
only the first is how Phase 2 nearly shipped a router that opened Chrome when
told "excel kholo" — see `docs/PHASE-2-RESULTS.md`.

### 1. `tests/golden/utterances.yaml` — cascade mechanics (the CI gate)

91 utterances across en/hi/gu, each with an expected tool, args and stage:

```yaml
- text: "volume thoda kam karo"
  lang: hi
  expect_tool: set_volume
  expect_args: {direction: down}
  expect_stage: grammar
  expect_confirm: false   # omit if not risk="confirm"; true requires the gate to fire
```

**Every embedding-stage case here is a verbatim copy of a line in
`config/examples/*.jsonl`.** That is deliberate and it is what makes this set
runnable in CI with no model download — but it also means a 100% score here
says nothing about semantic recall. The query has an exact match in the index,
so similarity is 1.0 and even the non-semantic `_fake_encoder` scores 100%.
Never cite this number as accuracy; cite it as "the cascade is wired
correctly."

### 2. `tests/golden/paraphrases.yaml` — held-out semantic recall

53 utterances that are **not** in the example set and **not** grammar-
matchable, so only genuine generalization answers them. This is the set that
measures the product's core claim — that one shared example set covers
en/hi/gu because the encoder is multilingual.

Two always-on tests enforce the held-out property itself. If you "fix" a
failing paraphrase by pasting it into `config/examples/`, they fail. Don't
route around them: add a *different* example that generalizes to it.

### 3. `tests/golden/out_of_domain.yaml` — knowing when not to answer

18 utterances with no Phase 2 tool at all (knowledge questions, unbuilt
capabilities, chit-chat). All must fall through to teach mode. This is the
only file that tests refusal, and it is the one that caught the shipped
threshold of 0.75 refusing **nothing** — `multilingual-e5-small` scores
unrelated text at 0.78-0.93, so everything matched something.

## Running it

```bash
# Always-on: fake encoder, no network, no model download. This is CI.
uv run pytest tests/test_router.py -v

# Full: adds the real multilingual-e5-small runs of all three sets.
# ~470MB download on first use, ~35s thereafter.
MUNSHIJI_GOLDEN_REAL_ENCODER=1 uv run pytest tests/test_router.py -s
```

Run the **real-encoder** form after any change to `config/examples/*.jsonl`,
the embedding threshold, or the encoder itself. The fake encoder cannot see
those regressions — it has no semantics, by construction.

## Interpreting results

CI gate on `utterances.yaml`, do not relax these to unblock a merge:
- **>=92% exact tool match** — the router picked the tool the case expects.
- **>=85% args match** — extracted slots match expected args.
- **100% on `expect_confirm: true` cases** — a missed confirmation gate is a
  correctness bug, not a quality metric. Any failure here blocks the merge
  regardless of the aggregate score.

Floors on `paraphrases.yaml` are lower (85% tool, 90% args) because unseen
phrasing is strictly harder — **except the confirm gate, which stays at
100%**. These are regression floors against measured behaviour, not targets:
raise them when the numbers justify it, never lower them to pass.

`out_of_domain.yaml` asserts that the set of leakers is *exactly* the ones
marked `still_matches: true`. A new leaker fails; so does a marked case that
starts being refused, since a stale marker stops guarding anything.

The runner also prints **stage-as-expected**, reported but not gated. A case
sliding grammar → embeddings still routes correctly but costs latency and
signals a template gap; sliding the other way means a template is
over-matching. That report is how `lock_screen` not accepting "lock my laptop"
was found.

When a case fails, diagnose which cascade stage should have matched
(`.claude/rules/architecture-and-router.md` has the cascade order) and why it
didn't:
- Expected `grammar` but matched `embeddings` or missed entirely → check the
  hassil template in `config/intents/` for a phrasing gap.
- Expected `embeddings` but missed → check the example set has enough coverage
  in that language, and that the similarity threshold (0.75 default) isn't too
  tight for a genuine paraphrase.
- Expected `embeddings` but got `teach` → the utterance scored below
  `router.embeddings.threshold`. Check the score the runner prints before
  touching the threshold: it is calibrated against the real encoder's score
  distribution (`docs/PHASE-2-RESULTS.md`), and lowering it to catch one case
  costs out-of-domain refusal across the board.
- Right tool, wrong args, at the embedding stage → the args did not come from
  this utterance. `enrich_slots` re-derives `app`/`state`/`direction` from the
  text (`args_from_example=True`); if a new slot type needs the same
  treatment, add it there rather than trusting the nearest example's value.
- Wrong tool selected at the LLM stage → check tool subsetting (top 8–12 by
  embedding relevance) and the stable-prefix prompt assembly — don't just
  reword the system prompt as a first attempt.

Never "fix" a failing case by routing it to the LLM as a shortcut — that hides
the actual gap instead of closing it, and works against the product's core
premise that router coverage should grow over time (see `router/teach.py`).

## Report format

State plainly: pass rate before/after, which specific cases changed status, and
for hi/gu cases specifically call out the per-language breakdown — an aggregate
pass rate can hide an Indic-language regression (see
`.claude/agents/indic-language-specialist.md`). Hindi was 61.1% when the
aggregate was 75.5%.

Say **which** of the three sets a number came from. "The golden set passes" is
ambiguous between "the cascade is wired correctly" and "the router is
accurate", and those came apart badly once already.
