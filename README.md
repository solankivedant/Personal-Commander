# Munshiji

A wake-word-activated voice assistant that runs entirely on a Windows laptop
and controls the actual machine — files, applications, system settings, Office
documents, email — with optional internet connectivity for live data and cloud
services. Local-first, and natively speaks Hindi, Gujarati, and English.

> Audio never leaves the device. The LLM is not the primary reasoning path —
> most commands are handled by a deterministic grammar matcher and a
> multilingual embedding classifier in under a second, with a small local LLM
> escalated to only for genuinely compositional requests.

The full product/engineering/commercial specification lives in
[`munshiji-full-report.md`](munshiji-full-report.md). This README is the
practical entry point; that report is the source of truth for *why*.

## Status

Pre-Phase 0. See [`docs/ROADMAP.md`](docs/ROADMAP.md) for the build plan and
current progress, and [`docs/RISK-REGISTER.md`](docs/RISK-REGISTER.md) for
known risks.

## Target hardware

Windows 10/11, 16 GB RAM, Intel Iris integrated graphics (no CUDA). See
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for why every design decision
here is made for CPU/iGPU inference.

## Repository layout

```
src/munshiji/    Application code — layers L0-L8, see docs/ARCHITECTURE.md
config/          Default config, hassil intent grammars, embedding examples
tests/golden/    The golden test set — mandatory router regression check
scripts/         build_index.py, benchmark.py, package.py
installer/       Inno Setup script + assets
docs/            Roadmap, architecture, risk register, licensing audit
.claude/         Claude Code rules, agents, and skills for working in this repo
```

## Getting started (once Phase 0/1 land)

```bash
uv sync
uv run pytest tests/ -v          # includes the golden test set
uv run python -m munshiji
```

## Working with Claude Code in this repo

This repo ships a full `.claude/` setup:

- **`.claude/rules/`** — engineering standards, security invariants,
  architecture/router rules, and licensing constraints. Auto-loaded context for
  any AI-assisted work here.
- **`.claude/agents/`** — `router-engineer`, `windows-tool-builder`,
  `indic-language-specialist`, `security-auditor`, `packaging-release-engineer`.
- **`.claude/skills/`** — `/new-tool` to scaffold a registry-compliant tool,
  `/golden-test` to run and interpret the golden test set, `/phase-status` to
  check roadmap progress.

See [`CLAUDE.md`](CLAUDE.md) for the full operating summary.

## Security

This product has shell and filesystem access and reasons over content authored
by strangers (web pages, email, PDFs) — prompt injection is treated as the
primary threat, not boilerplate. See
[`.claude/rules/security-and-privacy.md`](.claude/rules/security-and-privacy.md)
and `munshiji-full-report.md` §8 before adding any tool or network call.
Report suspected vulnerabilities per `SECURITY.md` (once published) rather
than filing a public issue.

## Licensing

Not finalized — see [`docs/LICENSING-AUDIT.md`](docs/LICENSING-AUDIT.md) for
the component licence audit and open decisions, and
[`LICENSE`](LICENSE) for the current placeholder. Not legal advice.

## Contributing

Solo/early-stage project — see `docs/ROADMAP.md` before proposing work, and
build in phase order. Golden-test coverage is required for any router/tool
change (`.claude/rules/engineering-standards.md`).
