# Licensing Audit

Source: `munshiji-full-report.md` §13. **Not legal advice** — this tracks what
has and hasn't been verified; it does not replace reading actual licence text
or consulting a lawyer before commercial launch. See
`.claude/rules/licensing-and-ip.md` for the rules that follow from this table.

## Component licences (§13.1) — verified as of report date (2026-08-29)

| Component | Licence | Commercial redistribution |
|---|---|---|
| openWakeWord | Apache 2.0 | ✓ attribution |
| faster-whisper / CTranslate2 | MIT | ✓ |
| Whisper weights (OpenAI) | MIT | ✓ |
| Silero VAD | MIT | ✓ |
| hassil | Apache 2.0 | ✓ |
| multilingual-e5-small | MIT | ✓ |
| Kokoro-82M | Apache 2.0 | ✓ |
| ChromaDB | Apache 2.0 | ✓ |
| Ollama | MIT | ✓ |
| Goose (if forking) | Apache 2.0 | ✓ |
| Open Interpreter | Apache 2.0 | ✓ |
| pywin32 | PSF | ✓ |
| PySide6 | **LGPL v3** | ✓ **only if dynamically linked** — see `.claude/rules/licensing-and-ip.md` |
| Everything (voidtools) | Freeware | ⚠️ verify bundling terms before shipping |

**Re-verify all of the above at implementation time** — this table reflects
the report's August 2026 sourcing (§19.5), not a live check.

## Model weight licences — the trap (§13.2)

Licences vary **by size within the same model family**. Never assume a
family's licence carries across sizes or versions.

| Model family | Status at report time | Action required |
|---|---|---|
| Qwen2.5 (small sizes) | Largely Apache 2.0 | Verify exact size on the model card before shipping |
| Qwen2.5-72B | Tongyi Qianwen licence, 100M-MAU threshold, separate application to Alibaba Cloud | Do not ship without separate agreement |
| Qwen2.5-VL variants | May differ from text counterparts | Check per-variant |
| Llama | Community Licence, commercial use permitted below 700M MAU | Weights gated behind acceptance |
| Gemma 3 | Custom Google Terms of Use, not OSI-approved, remote-restriction rights reserved | Verify before shipping |
| Gemma 4 | Apache 2.0 | — |

**Practical policy for v1 (recommended in the report, not yet a final
decision)**: ship Apache-2.0-licensed weights only, and do not bundle weights
in the installer — download from the upstream source at first run with the
licence displayed and accepted. This keeps the project a pointer, not a
redistributor.

If a model is called via a hosted API instead of shipped as weights, the
provider's API terms govern instead, and redistribution/MAU triggers become
the provider's burden, not ours.

## Open decisions — not yet finalized

- [ ] **Our own licence**: proprietary EULA (closed, perpetual per major
      version) vs. open-core (router/tools/voice-loop AGPL-3.0, Indic
      layer/GUI/Office integration proprietary) — see §13.4. Open-core
      supports the "audit the privacy claim yourself" pitch but is a real
      business decision, not a default to assume in code or user-facing copy.
- [ ] **PySide6 vs. Tauri** for the tray UI — affects the LGPL dynamic-linking
      requirement. If PySide6 is used, `--onedir` with Qt as separate DLLs is
      required, not `--onefile` or static linking.
- [ ] **Trademark**: "Munshiji" (and the report's placeholder "Sahayak") are
      common Hindi words — run an Indian trademark registry search before
      committing to final branding. File in Class 9 (software) and Class 42
      (SaaS) if proceeding.
- [ ] Confirm exact model + size for the shipped Qwen2.5 build and record its
      verified licence here before Phase 4/8.

## Attribution requirements

Ship `THIRD_PARTY_NOTICES.txt`, generated in CI via `pip-licenses`, reachable
from the About dialog. Apache 2.0 requires preserving copyright and NOTICE
files when vendoring — don't strip them on dependency updates.

## Update policy

Whenever a new dependency or model is added anywhere in `src/munshiji/`, add a
row here (or update the model table) with its verified licence and the date
verified. If it isn't recorded here, treat it as unverified regardless of what
a code comment claims.
