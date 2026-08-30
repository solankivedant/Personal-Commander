---
name: phase-status
description: Report current build progress against Munshiji's Phase 0-9 roadmap (docs/ROADMAP.md, sourced from munshiji-full-report.md §11). Use when asked "what phase are we on", "what's left before Phase N", "is Phase X done", or before starting new work to confirm it belongs in the current phase.
---

# Checking phase status

`docs/ROADMAP.md` holds the Phase 0–9 checklist derived from
`munshiji-full-report.md` §11. Each phase has a stated deliverable, not just a
task list — treat the deliverable as the acceptance test for "done."

## How to check status

1. Read `docs/ROADMAP.md`.
2. For the phase in question, check which checklist items correspond to real,
   working code vs. stub modules (everything under `src/munshiji/` starts as a
   docstring-only stub — grep for `NotImplementedError`, `TODO`, or simply
   check whether the module has grown past its stub docstring).
3. Cross-check against `tests/golden/utterances.yaml` and whether
   `tests/test_router.py` / `tests/test_tools.py` / `tests/test_latency.py`
   have real assertions yet — a phase claiming completion without golden-set
   coverage for its new tools/intents is not actually done per
   `.claude/rules/engineering-standards.md`.
4. State the phase's deliverable from the roadmap verbatim and say plainly
   whether it currently holds.

## Reporting format

- Current phase, and one line on why it's current (previous phase's deliverable
  met, or explicitly still in progress).
- What's done vs. outstanding within it, as a short checklist.
- Anything found built *ahead* of the current phase (e.g. LLM escalation code
  before Phase 2's router is solid) — flag it, since the roadmap's phase order
  exists to keep "no LLM required" true through Phase 3.
- Whether `docs/ROADMAP.md` itself needs updating to reflect reality (check
  boxes, don't just report verbally and leave the file stale).

## Gate reminders worth surfacing

- **Phase 0 gate**: if ASR > 600ms or the 3B model < 10 tok/s on the actual
  target machine, model choices should be revisited before Phase 1 starts —
  don't let this slide silently.
- **Phase 2 deliverable**: "genuinely useful daily driver, no LLM required" —
  if Phase 2 work depends on `brain/` being functional, something is out of
  order.
- **Phase 3 deliverable**: "safe to point at real files" — this requires the
  undo stack and confirm gating to be real, not stubbed, before file tools are
  considered done.
