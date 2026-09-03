# Build Roadmap

Source: `munshiji-full-report.md` §11. Total estimated effort: **~560 hours**
(forking Goose instead of building the orchestrator from scratch removes
roughly 100–150h from Phases 4–5).

Check this file before starting new work — build in phase order. A phase's
**Deliverable** is its acceptance test, not just its checklist.

Status legend: `[ ]` not started · `[~]` in progress · `[x]` done

---

## Phase 0 — Spike (1 week, ~20h)

Prove the hardware works before committing to it. **Run on: Dell Inspiron 14
7430 2-in-1, i7-1355U, Iris Xe, 16GB — confirmed to match the report's target
baseline.** Full results: [`docs/PHASE-0-RESULTS.md`](PHASE-0-RESULTS.md).

- [x] Benchmark Whisper `small` int8 on the actual target laptop — **CPU
      backend fails the gate (~2.9s)**; OpenVINO on the Iris Xe GPU gets to
      ~850ms (close, not yet passing — INT8 quantization is the next lever)
- [x] Benchmark Qwen2.5-3B tok/s via Ollama on the actual target laptop —
      **11.3 tok/s median, gate passed**
- [x] Check RAM channel configuration — soldered LPDDR5x @ 6400 MT/s, already
      optimal on this machine; the report's dual-channel-upgrade advice
      doesn't apply here
- [ ] Test openWakeWord false-accept rate in a real room — needs a live mic
      session, deferred to Phase 1 once `wake/detector.py` exists. Note:
      `wake/detector.py` now exists but loads a stock pretrained model
      (`hey_jarvis`) as a placeholder, not a trained "hey munshiji" model —
      see the Phase 1 note below before running this test.

**Gate:** if ASR > 600ms or 3B < 10 tok/s, revise model choices before Phase 1.
**Status: partially open.** LLM path cleared. ASR needs one more iteration
(INT8-quantized Whisper `small` on the Iris Xe GPU, ~30-60 min estimated) —
see `docs/PHASE-0-RESULTS.md` for the concrete next step before treating
`small` as final. Recommend starting Phase 1's non-ASR work now (ring buffer,
wake FSM, TTS) in parallel rather than blocking everything on this.

## Phase 1 — Voice loop (2 weeks, ~50h)

- [x] L0 ring buffer + Silero VAD (`audio/`)
- [x] L1 wake word + FSM + push-to-talk (`wake/`)
- [x] L2 Whisper integration (`asr/whisper.py`) — CTranslate2 CPU backend;
      `asr/openvino.py` stays the Phase 6 stub, see docs/PHASE-0-RESULTS.md
- [x] L8 Kokoro streaming TTS (`tts/kokoro.py`) — requires manually
      downloading Kokoro's weights into `data/models/kokoro/` before first
      run (no bundled/hardcoded-URL auto-download, see the class docstring
      and `.claude/rules/licensing-and-ip.md`)
- [ ] Echo-back test: say something, hear it repeated — code is in place
      (transcript passes straight through to TTS in Phase 1, no router yet).
      Ran `python -m munshiji` live on the target laptop (real mic + real
      speakers): it now starts cleanly and stays up under continuous real
      audio — found and fixed a real crash in doing so (see note below). What
      remains needs an actual human voice and ears (an AI agent has neither):
      say something, confirm it's heard correctly and repeated back at a
      tolerable latency.
- [x] Minimal floating status overlay (`ui/overlay.py`) — a Whisper-Flow/
      Gemini-style pill docked to the bottom of the screen showing
      listen/think/speak state and the last transcript. **Pulled forward from
      Phase 8 by explicit user decision** (user asked for a dashboard +
      floating control UI; Phase 2/3 — the router and tools a real dashboard
      would control — don't exist yet, so scope was cut to a pure status
      subscriber on the event bus, no controls). The full tray icon, control
      dashboard, and onboarding wizard remain Phase 8.

**Note (found on the first live run, now fixed):** `audio/vad.py`'s `SileroVad`
crashed a few seconds into real audio — the installed `silero-vad` model only
accepts fixed 512-sample windows at 16kHz (256 at 8kHz) and raises on
anything else, but `AudioCapture` hands it 1280-sample (80ms) frames sized
for openWakeWord, not Silero. This is exactly the class of bug the "not
verifiable from this dev environment" caveat existed to catch — it only
surfaced by actually running the process with a live mic, not from unit
tests or a read-through. Fixed by sub-chunking each incoming frame into
model-sized windows internally, carrying the remainder to the next call, with
regression coverage in `tests/test_vad.py` (a fake model pinned to reject any
window size other than 512/256, so a regression back to "just pass the frame
through" fails fast without needing real hardware). Verified stable for 20+
seconds of continuous live capture afterward with no crash.

**Note:** no trained "hey munshiji" openWakeWord model exists yet — training
one needs synthetic-TTS data and a training run, tracked as a follow-up, not
done as part of this phase. `wake/detector.py` defaults to the stock
`hey_jarvis` pretrained model (`config/default.yaml`'s `wake.detector_model_id`) as a
placeholder; push-to-talk (`ctrl+alt+space`) is the reliable entry point in
the meantime, per the report's own guidance that wake words fail in noise.

**Deliverable:** a thing that listens and talks. Code-complete and confirmed
running stably on the target laptop with real audio hardware; the one
remaining gate is a human actually speaking to it and confirming the
round-trip sounds and feels right — not something verifiable without a
person present.

## Phase 2 — Router + Tier 0/1 tools (3 weeks, ~70h)

- [x] `@tool` registry with tier/risk/tags (`tools/registry.py`) — schema
      generated from type hints + docstring; `blocked`-risk tools are
      structurally excluded from `ToolRegistry.iter_llm_visible()`, not just
      discouraged by prompt
- [x] hassil grammars for ~25 intents (`config/intents/`) — 24 intents across
      `system.yaml` (14), `apps.yaml` (6), `files.yaml` (4, Phase 3 tools,
      grammar staged ahead of the tools existing)
- [x] Embedding index + teach mode (`router/embeddings.py`, `router/teach.py`)
      — `multilingual-e5-small` via an injectable encoder; teach mode's
      append-example/rebuild-index primitives are implemented and tested,
      but the interactive "ask the user what this should do" voice dialogue
      is deferred — the FSM has no multi-turn dialogue state yet (see note
      below)
- [x] 20 system and app tools (`tools/system.py`, `tools/apps.py`) — 19
      tools, all with real undo paths except the handful with no sensible
      inverse (lock_screen, sleep, read-only getters)
- [x] Golden test set v1 (`tests/golden/utterances.yaml`) — 86 entries across
      en/hi/gu; Phase-2-scoped (grammar + embeddings) pass rate 100%
      exact-tool, 100% args, 100% confirm (`shutdown`/`restart`) against the
      fake test encoder — **the real `multilingual-e5-small` accuracy is not
      yet verified**, see note below
- [x] Router wired into the voice loop (`wake/fsm.py`'s ROUTING/ACTING
      states, assembled in `__main__.py`) — this was implicit in the
      deliverable but not its own checklist line; a transcript now actually
      resolves to a tool call and executes, rather than echoing

**Deliverable: genuinely useful daily driver, no LLM required — met**, with
three caveats to close out before calling Phase 2 fully hardened:

1. **Real-encoder verification pending.** The golden set's embeddings-stage
   cases were graded against a deterministic fake encoder (no network access
   in the dev sandbox for the ~470MB `multilingual-e5-small` pull) — it
   validates cascade mechanics (ordering, thresholding, confirm resolution)
   correctly, but genuine semantic-paraphrase accuracy needs re-running with
   the real model once it's downloaded. Do this before trusting the 100%
   figure above as a real accuracy number.
2. **Two known grammar issues in `config/intents/`**, not yet fixed:
   `apps.yaml`'s `focus_app` ("go to {app}") and `system.yaml`'s `sleep`
   ("go to sleep") collide on the literal phrase "go to sleep" — whichever
   file's intents dict merges first wins arbitrarily. And `system.yaml`'s
   `set_volume` `{level}` wildcard is untyped, so it can greedily capture
   non-numeric text (diagnosed during golden-set construction) instead of
   falling through to `get_volume`'s embedding examples. Needs a numeric
   slot constraint (hassil `RangeSlotList`) or reordering, not a prompt-level
   workaround.
3. **Cross-script ASR recovery is unhandled.** `rapidfuzz` fixes Latin-script
   mangling ("Chrom" → "Chrome") but not Devanagari ("क्रोम") — that needs a
   transliteration step before fuzzy-matching, tracked as Indic-language-
   specialist work, likely Phase 6.

Also out of scope for this phase, deliberately: `router/slots.py` doesn't use
spaCy (nothing in the Phase 2 intent set needs date/time NER — add it when
Phase 3's file tools do), and voice-driven teach mode's "ask the user" loop
(vs. the already-working programmatic `teach()`/`rebuild_index_after_teach()`
primitives) waits on real multi-turn dialogue state, which is closer to
Phase 4/7 territory than a router concern.

## Phase 3 — Files + confirmation + undo (2 weeks, ~50h)

- [ ] Everything CLI integration (`tools/files.py`)
- [ ] File tools with confirm gating
- [ ] Undo stack (`security/undo.py`)
- [ ] Audit log

**Deliverable:** safe to point at real files.

## Phase 4 — LLM escalation (2 weeks, ~50h)

- [ ] Ollama orchestrator, bounded loop (`brain/ollama.py`, `brain/loop.py`)
- [ ] Stable-prefix prompt assembly (`brain/prompt.py`)
- [ ] Tool subsetting by embedding
- [ ] Dry-run plan summarization

**Deliverable:** handles compositional requests.

## Phase 5 — Office + network (3 weeks, ~70h)

- [ ] COM tools: Outlook, Excel, Word (`tools/office.py`)
- [ ] Allowlisted HTTP client (`net/client.py`)
- [ ] Weather, search, finance (`tools/web.py`)
- [ ] MCP client bridge (`tools/mcp_bridge.py`)
- [ ] Google via app password (`tools/google.py`)

**Deliverable:** does real work.

## Phase 6 — Indic (3 weeks, ~70h)

- [ ] IndicWhisper integration (`asr/`)
- [ ] Multilingual embedding index, hi/gu example sets (`config/examples/`)
- [ ] IndicTTS (`tts/indic.py`)
- [ ] Language auto-routing

**Deliverable:** the differentiator.

## Phase 7 — Memory + RAG (2 weeks, ~45h)

- [ ] SQLite facts, working state (`memory/facts.py`, `memory/working.py`)
- [ ] Chroma document index (`memory/documents.py`)
- [ ] Screen understanding (moondream)
- [ ] Local FastAPI server (`net/api.py`)

## Phase 8 — Packaging + licensing (3 weeks, ~70h)

- [ ] Tray UI, control dashboard, onboarding wizard (`ui/`) — note: a minimal
      status-only overlay (`ui/overlay.py`) already exists, pulled forward
      into Phase 1; this phase still owns the tray icon, the real control
      dashboard wired to the router/tools, and onboarding
- [ ] PyInstaller + Inno Setup (`scripts/package.py`, `installer/`)
- [ ] Code signing
- [ ] Licence verification (`licence/verify.py`)
- [ ] Auto-update

**Deliverable:** shippable installer.

## Phase 9 — Commercial (3 weeks, ~65h)

- [ ] Landing page, docs
- [ ] Licence server
- [ ] Payment integration
- [ ] Support workflow

---

## Immediate next actions (§19.4)

1. Check RAM channel configuration — five seconds, largest cheap speedup
   available.
2. Run Phase 0 benchmarks before writing any product code.
3. Decide fork-vs-build on Goose — moves the timeline by 100–150h and
   determines whether MCP support comes free.
4. Verify the exact licence of the specific model weights intended for
   shipping, at the specific size, on the model card (see
   `docs/LICENSING-AUDIT.md`).
5. Record a 30-second demo as soon as Phase 1 works — it's both motivation and
   the entire early marketing asset.
