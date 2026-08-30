# Licensing & IP rules

Source: `munshiji-full-report.md` §13. **This file and the report section it
summarizes are not legal advice.** Read the actual licence text before shipping
anything commercially, and consult a lawyer before commercial launch. This file
exists so day-to-day coding decisions don't accidentally create a compliance
problem — not as a substitute for real review.

## The core rule: don't bundle model weights

Ship no model weights in the installer. Download from the original upstream
source at first run, display the licence, require acceptance. This keeps the
project a *pointer* rather than a *redistributor* and materially simplifies
compliance (§13.2). Do not change this to "bundle for offline convenience"
without a licensing review — it changes the legal posture of the whole product.

## Model licences vary by size within the same family

This is the trap that catches people. Before wiring in *any* model or changing
a model's size/variant:

- Check the specific model card for the exact model **and size** being shipped.
  Qwen2.5's smaller sizes are largely Apache 2.0; the 72B is under a different
  licence with a MAU threshold. Some Qwen2.5-VL variants differ from their text
  counterparts.
- Llama: Community Licence, commercial use permitted below 700M MAU, weights
  gated behind acceptance.
- Gemma 3: custom Google Terms of Use, not OSI-approved; Gemma 4 moved to
  Apache 2.0 — don't assume the family's licence carries across versions.
- If calling a model through a hosted API instead of shipping weights, the
  provider's API terms govern instead — redistribution/MAU triggers become the
  provider's burden, not ours.
- Record every model's verified licence in `docs/LICENSING-AUDIT.md` when you
  add or change one. If it isn't recorded there, treat it as unverified.

## PySide6 / LGPL

If the tray UI uses PySide6: LGPL v3 permits commercial closed-source use
**only with dynamic linking** and the ability for users to replace the library.
PyInstaller `--onedir` with Qt as separate DLLs satisfies this; static bundling
does not — never switch the build to `--onefile` or static-link Qt without
re-checking this. Tauri (MIT/Apache) is the escape hatch if this becomes
uncomfortable.

## Attribution

Ship `THIRD_PARTY_NOTICES.txt`, generated in CI with `pip-licenses`, reachable
from the About dialog. Apache 2.0 requires preserving copyright and NOTICE
files — don't strip them when vendoring or updating a dependency.

## Trademark / naming

"Munshiji" and "Sahayak" are both common Hindi words and may be difficult to
register cleanly — run an Indian trademark registry search before committing to
final branding. Never use "Hey Siri," "OK Google," or a confusingly similar
wake-word phrase or marketing comparison that implies endorsement. Nominative
comparison in a feature table is fine; imitation is not.

## Our own licence

Recommended default per the report: proprietary EULA, closed source, perpetual
licence for the shipped major version — or open-core (router/tools/voice-loop
under AGPL-3.0, Indic layer + GUI + Office/COM integration proprietary), which
supports the "audit the privacy claim yourself" pitch. **This is a business
decision, not yet finalized in this repo** — see `docs/LICENSING-AUDIT.md` for
status. Don't assume one over the other in code comments or user-facing text
until it's decided.

## Component licence table

See `docs/LICENSING-AUDIT.md` for the full audited component table (§13.1). Keep
it updated whenever a new dependency is added.
