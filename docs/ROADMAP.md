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
      (transcript passes straight through to TTS in Phase 1, no router yet)
      but needs to be run on the actual target laptop with a live mic; not
      verifiable from this dev environment
- [x] Minimal floating status overlay (`ui/overlay.py`) — a Whisper-Flow/
      Gemini-style pill docked to the bottom of the screen showing
      listen/think/speak state and the last transcript. **Pulled forward from
      Phase 8 by explicit user decision** (user asked for a dashboard +
      floating control UI; Phase 2/3 — the router and tools a real dashboard
      would control — don't exist yet, so scope was cut to a pure status
      subscriber on the event bus, no controls). The full tray icon, control
      dashboard, and onboarding wizard remain Phase 8.

**Note:** no trained "hey munshiji" openWakeWord model exists yet — training
one needs synthetic-TTS data and a training run, tracked as a follow-up, not
done as part of this phase. `wake/detector.py` defaults to the stock
`hey_jarvis` pretrained model (`config/default.yaml`'s `wake.detector_model_id`) as a
placeholder; push-to-talk (`ctrl+alt+space`) is the reliable entry point in
the meantime, per the report's own guidance that wake words fail in noise.

**Deliverable:** a thing that listens and talks. Code-complete; live-hardware
verification (the echo-back test above) is the one remaining gate.

## Phase 2 — Router + Tier 0/1 tools (3 weeks, ~70h)

- [ ] `@tool` registry with tier/risk/tags (`tools/registry.py`)
- [ ] hassil grammars for ~25 intents (`config/intents/`)
- [ ] Embedding index + teach mode (`router/embeddings.py`, `router/teach.py`)
- [ ] 20 system and app tools (`tools/system.py`, `tools/apps.py`)
- [ ] Golden test set v1 (`tests/golden/utterances.yaml`)

**Deliverable:** genuinely useful daily driver, no LLM required.

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
