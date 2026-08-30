# Build Roadmap

Source: `munshiji-full-report.md` §11. Total estimated effort: **~560 hours**
(forking Goose instead of building the orchestrator from scratch removes
roughly 100–150h from Phases 4–5).

Check this file before starting new work — build in phase order. A phase's
**Deliverable** is its acceptance test, not just its checklist.

Status legend: `[ ]` not started · `[~]` in progress · `[x]` done

---

## Phase 0 — Spike (1 week, ~20h)

Prove the hardware works before committing to it.

- [ ] Benchmark Whisper `small` int8 on the actual target laptop
- [ ] Benchmark Qwen2.5-3B tok/s via Ollama on the actual target laptop
- [ ] Check RAM channel configuration (Task Manager → Performance → Memory →
      Slots used) — single-channel forfeits 40–60% memory bandwidth, the
      cheapest largest speedup available (§9.2)
- [ ] Test openWakeWord false-accept rate in a real room

**Gate:** if ASR > 600ms or 3B < 10 tok/s, revise model choices before Phase 1.

## Phase 1 — Voice loop (2 weeks, ~50h)

- [ ] L0 ring buffer + Silero VAD (`audio/`)
- [ ] L1 wake word + FSM + push-to-talk (`wake/`)
- [ ] L2 Whisper integration (`asr/whisper.py`)
- [ ] L8 Kokoro streaming TTS (`tts/kokoro.py`)
- [ ] Echo-back test: say something, hear it repeated

**Deliverable:** a thing that listens and talks.

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

- [ ] Tray UI, onboarding wizard (`ui/`)
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
