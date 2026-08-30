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

`tests/golden/utterances.yaml` holds 80–120 utterances across en/hi/gu, each
with:

```yaml
- text: "volume thoda kam karo"
  lang: hi
  expect_tool: set_volume
  expect_args: {direction: down}
  expect_stage: grammar
  expect_confirm: false   # omit if not risk="confirm"; true requires the gate to fire
```

## Running it

```bash
uv run pytest tests/test_router.py -v
```

(Adjust once the actual runner/CLI exists in Phase 2 — check `scripts/` and
`tests/test_router.py` for the current invocation if this has changed.)

## Interpreting results

CI gate, do not relax these to unblock a merge:
- **≥92% exact tool match** — the router picked the tool the case expects.
- **≥85% args match** — extracted slots match expected args.
- **100% on `expect_confirm: true` cases** — a missed confirmation gate is a
  correctness bug, not a quality metric. Any failure here blocks the merge
  regardless of the aggregate score.

When a case fails, diagnose which cascade stage should have matched
(`.claude/rules/architecture-and-router.md` has the cascade order) and why it
didn't:
- Expected `grammar` but matched `embeddings` or missed entirely → check the
  hassil template in `config/intents/` for a phrasing gap.
- Expected `embeddings` but missed → check the example set has enough coverage
  in that language, and that the similarity threshold (0.75 default) isn't too
  tight for a genuine paraphrase.
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
`.claude/agents/indic-language-specialist.md`).
