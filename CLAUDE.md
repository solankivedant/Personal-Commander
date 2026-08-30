# Munshiji — Local-First Voice Assistant for Windows

Munshiji (codenamed *Sahayak* in the source report) is a wake-word-activated voice
assistant that runs entirely on a Windows laptop and controls the actual machine —
files, applications, system settings, Office documents, email — with optional
internet connectivity for live data and cloud services. It is voice-first and
speaks Hindi, Gujarati, and English.

The full product/engineering/commercial spec lives in
[`munshiji-full-report.md`](munshiji-full-report.md) (19 sections, ~1400 lines).
This file is the operating summary for Claude Code sessions; **when in doubt about
a design decision, read the relevant section of the full report before guessing.**
Section references (`§N`) below point into it.

## Target hardware baseline

Windows 10/11 laptop, 16 GB RAM, Intel Iris integrated graphics — **no CUDA**.
Every optimization decision in this repo is made for CPU/iGPU inference, not GPU.
See `docs/ARCHITECTURE.md` §9 before adding anything that assumes a discrete GPU.

## The core architectural decision — read this first

**The LLM is not the primary reasoning path.** On this hardware a 7B model takes
8–14s per response — unusable for voice. ~85% of commands are routed through a
deterministic grammar matcher (`router/grammar.py`) and a multilingual embedding
classifier (`router/embeddings.py`), both sub-20ms. Only genuinely compositional
requests escalate to the local 3B LLM (`brain/`) or, opt-in, a cloud API.

This is not a hardware compromise — it is the better architecture for the
differentiating feature too: a multilingual sentence encoder places Hindi and
Gujarati phrasings in the same vector space as English examples, so the
non-LLM path is *more* accurate in Indic languages, not less (§10.2).

**Do not "fix" slow responses by routing more through the LLM.** If something
feels slow, the fix is almost always a new grammar template or embedding example,
not a bigger model. See `router/teach.py` — the assistant is supposed to get
faster with use.

## Repository layout

```
src/munshiji/    Application code — see docs/ARCHITECTURE.md for the layer map (L0-L8)
config/          default.yaml + hassil intent grammars + per-language embedding examples
tests/golden/    utterances.yaml — the golden test set (mandatory, see below)
scripts/         build_index.py, benchmark.py, package.py
installer/       Inno Setup script + assets
docs/            ROADMAP.md, ARCHITECTURE.md, RISK-REGISTER.md, LICENSING-AUDIT.md
.claude/         rules/, agents/, skills/ — see below
```

Every module under `src/munshiji/` currently exists only as a docstring stub
naming its purpose and the roadmap phase it belongs to (see `docs/ROADMAP.md`).
Implement in phase order — don't build Phase 5 tools before Phase 2's router and
tool registry are real and passing the golden set.

## Non-negotiable engineering standards

Full detail in [`.claude/rules/engineering-standards.md`](.claude/rules/engineering-standards.md).
The short version:

- `uv` for dependency management, committed lockfile, Ollama model tags pinned **by
  digest, never `:latest`**.
- `mypy --strict` on `src/`, `ruff` for lint, `pytest` for tests.
- **The golden test set (`tests/golden/utterances.yaml`) is mandatory**, not
  optional coverage. CI fails below 92% exact tool match, 85% args match, and
  **100% on `expect_confirm` cases** — a missed confirmation gate is a
  correctness bug, not a quality metric. Run it after *any* prompt, model, or
  index change (§5.2).
- No behaviour constants in source — config lives in YAML only.
- Every tool catches its own exceptions and returns a readable failure string.
  Never let an exception reach the LLM loop as a raw traceback.

## Non-negotiable security invariants

Full detail in [`.claude/rules/security-and-privacy.md`](.claude/rules/security-and-privacy.md).
This product has shell access and reads content written by strangers (web pages,
email, PDFs) — prompt injection is the primary threat (§8.1), not a theoretical
one. Before touching `tools/`, `net/`, or `security/`:

- Untrusted tool output is always wrapped in `<untrusted_content>` delimiters and
  is content to reason about, **never instructions to obey**.
- Anything that **deletes, sends, spends, or overwrites** is `risk="confirm"` and
  speaks its intent before acting — confirmation always routes to the user by
  voice, never triggered directly by a tool result.
- Every mutating tool registers its inverse in the undo stack *before* executing.
- Network calls go through the shared allowlisted `net/client.py` only. Never add
  a raw `httpx`/`requests` call elsewhere. `local_only` mode must remove every
  `net`-tier tool from the registry.
- The local API (`net/api.py`) binds to the Tailscale interface only — **never
  `0.0.0.0`** — plus a bearer token.
- `blocked`-risk tools (credential access, registry writes, mass deletion) are
  unreachable from the LLM path entirely, not just discouraged by prompt.

## Licensing

Full detail in [`.claude/rules/licensing-and-ip.md`](.claude/rules/licensing-and-ip.md)
and `docs/LICENSING-AUDIT.md`. The load-bearing rule: **do not bundle model
weights in the installer.** Download from the original upstream source at first
run with the licence displayed and accepted (§13.2) — this keeps the project a
pointer, not a redistributor. Verify the exact licence of any model at the exact
size before wiring it in; licences vary by size within the same model family.

## Working in this repo

- `.claude/rules/` — the standards above, in full, auto-loaded context for how to
  build in this codebase.
- `.claude/agents/` — specialized subagents for router work, Windows tool
  building, the Indic language layer, security review, and packaging/release.
  Prefer the matching agent over general-purpose work when a task fits one.
- `.claude/skills/` — `/new-tool` to scaffold a registry-compliant tool,
  `/golden-test` to run and interpret the golden set, `/phase-status` to check
  roadmap progress against `docs/ROADMAP.md`.
- `docs/ROADMAP.md` — Phase 0–9 checklist (§11). Check it before starting new
  work to confirm you're building in the right order and not skipping a gate.
- `docs/RISK-REGISTER.md` — known risks (§18), several **High** likelihood
  (wake-word reliability, antivirus false-positives). Read before dismissing a
  failure mode as unlikely.

## What "done" looks like for a phase

Each roadmap phase in the full report (§11) names a concrete deliverable, not
just a task list — e.g. Phase 1 is "a thing that listens and talks," Phase 2 is
"genuinely useful daily driver, no LLM required." Treat the deliverable as the
acceptance test, and update `docs/ROADMAP.md` when a phase's gate is met.
