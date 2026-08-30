# Security Policy

Munshiji has shell access, a filesystem, and reasons over content authored by
strangers (web pages, email, PDFs) via a local LLM. Prompt injection, tool
misuse, and credential handling are treated as primary threats — see
`munshiji-full-report.md` §8 and `.claude/rules/security-and-privacy.md` for
the full threat model.

## Reporting a vulnerability

**Do not open a public GitHub issue for a security vulnerability.**

Email: vedantsolanki20102005@gmail.com with a description, reproduction steps,
and impact assessment. Please allow a reasonable window to investigate and
patch before public disclosure.

## In scope

- Prompt-injection paths that bypass the untrusted-content boundary or trigger
  a `confirm`/`blocked`-tier action without user confirmation
- Network calls that bypass the domain allowlist
- Credential exposure (plaintext secrets, logs, audit trail)
- Local API (`net/api.py`) exposure beyond the Tailscale interface
- Licence-verification bypass is **not** a priority report — see
  `munshiji-full-report.md` §15.6: offline licence checks are known-defeatable
  by design and optimized for honest-buyer convenience, not anti-piracy.

## Known accepted risks

Tracked in `docs/RISK-REGISTER.md`, including wake-word reliability,
antivirus false positives, and COM automation fragility across Office updates.
These are tracked risks, not undisclosed vulnerabilities.
