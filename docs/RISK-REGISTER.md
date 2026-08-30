# Risk Register

Source: `munshiji-full-report.md` §18. Review before dismissing a failure mode
as unlikely — several of these are rated **High** likelihood, not edge cases.

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| 1 | Wake word unreliable in Indian home/office noise | High | High | Always ship push-to-talk; tune on real user audio in free-tier phase |
| 2 | Gujarati ASR accuracy insufficient | Medium | High | AI4Bharat models; collect corrections via teach mode; ship Hindi first if needed |
| 3 | 3B model too weak for Tier 4 tasks | Medium | Medium | Router covers 85%; offer cloud escalation |
| 4 | Prompt injection causes real damage | Low | **Severe** | Data boundary, allowlist, confirm gate, undo stack |
| 5 | Model licence blocks redistribution | Medium | High | Ship no weights; download upstream at first run |
| 6 | SmartScreen kills install conversion | High | High | EV certificate from day one |
| 7 | Antivirus false-positive (PyInstaller + input synthesis is a classic AV trigger) | **High** | High | Sign everything; submit to AV vendors pre-launch; document exclusion steps |
| 8 | COM automation breaks on Office update | Medium | Medium | Version detection, graceful degradation, fallback to openpyxl |
| 9 | Market too small (Windows + 16GB + wants voice + Indic) | Medium | High | Validate with free tier before Pro investment |
| 10 | Big-tech competitor ships equivalent | Low | High | Local file/shell access is structurally hard for them; Indic is a durable niche |
| 11 | Support burden exceeds revenue | High | Medium | Excellent docs, in-app diagnostics, community forum before email support |
| 12 | Solo maintainer burnout | **High** | High | Ship narrow, say no, automate the golden test set |

## Risk #7 deserves emphasis

A PyInstaller-packaged Python app that synthesizes keystrokes, takes
screenshots, and runs shell commands looks exactly like malware to heuristic
antivirus engines. This *will* happen. Sign everything, submit binaries to
major AV vendors for whitelisting before launch, and prepare a support article
in advance. Several indie Windows apps have been effectively killed by this —
see `.claude/agents/packaging-release-engineer.md`.

## Risk #4 deserves emphasis

Severity is rated Severe despite Low likelihood specifically because the
product combines LLM reasoning over untrusted content with real shell/file
access — see `.claude/rules/security-and-privacy.md` and the
`security-auditor` agent, which exists specifically to keep this risk's
likelihood low as the tool surface grows.
