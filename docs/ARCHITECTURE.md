# Architecture

Condensed from `munshiji-full-report.md` §3, §4, §9. Read the full report for
rationale — this is the reference map, not the argument for it.

## Layer diagram

```
┌─────────────────────────────────────────────────────────────┐
│  L8  TTS / Output          Kokoro-82M ONNX · streaming      │
├─────────────────────────────────────────────────────────────┤
│  L7  Memory      Conversation ring · Working state · Chroma │
├─────────────────────────────────────────────────────────────┤
│  L6  Execution   pywin32 · pycaw · psutil · subprocess      │
├─────────────────────────────────────────────────────────────┤
│  L5  Tool Registry     @tool decorator · risk tiers · schema │
├─────────────────────────────────────────────────────────────┤
│  L4  Orchestrator      Ollama 3B · bounded loop · validation │
├─────────────────────────────────────────────────────────────┤
│  L3  ROUTER ★    hassil grammar → e5 embeddings → LLM        │
├─────────────────────────────────────────────────────────────┤
│  L2  ASR               faster-whisper small · OpenVINO       │
├─────────────────────────────────────────────────────────────┤
│  L1  Wake + State      openWakeWord · FSM · hotkey fallback  │
├─────────────────────────────────────────────────────────────┤
│  L0  Audio I/O         sounddevice · ring buffer · SileroVAD │
└─────────────────────────────────────────────────────────────┘
        ╎ Cross-cutting: Event Bus · Config · Audit Log ╎
```

The audit log (`security/audit.py`, Phase 3) is a bus *subscriber*, not a
collaborator any layer calls — that is what keeps it, the GUI and the future
HTTP API decoupled from internals, and it means nothing in it can change what
the assistant does. It records the action, its arguments, its result, a
timestamp and the deciding router stage; that last field is what answers "why
did it delete that" three days later.

★ = the layer that defines this product — see
`.claude/rules/architecture-and-router.md`.

## Build vs. fork per layer (§2.4)

| Layer | Decision | Rationale |
|---|---|---|
| L0–L2 (audio, wake, ASR) | Integrate HF `speech-to-speech` | Maintained, solved |
| L3 (router) | **Build** | Core differentiator, no equivalent exists |
| L4 (orchestrator) | Fork Goose or build thin | MCP support comes free |
| L5–L6 (tools, execution) | **Build** | Windows-specific, no equivalent |
| L7 (memory) | Integrate Chroma / Khoj patterns | Standard |
| L8 (TTS) | Integrate Kokoro | Solved |
| Indic layer | **Build** | The novel contribution |

## State machine (L1)

```
IDLE ──wake/hotkey──▶ LISTENING ──VAD silence──▶ TRANSCRIBING
  ▲                                                    │
  │                                                    ▼
SPEAKING ◀── ACTING ◀── ROUTING ◀────────────────  (text)
  │                        │
  └──── barge-in ──────────┘
```

## Router cascade (L3) — see `.claude/rules/architecture-and-router.md`

1. Grammar (hassil) — <10ms, ~50% coverage
2. Embeddings (multilingual-e5-small, threshold 0.88 — calibrated, see
   `PHASE-2-RESULTS.md`) — ~15ms, ~35% coverage
3. Escalation (`router.escalation`, default `[cloud]`) — ~15% coverage.
   Cloud is the default target; the local Qwen2.5-3B is opt-in and off by
   default, see `decisions/0001-local-llm-off-the-default-path.md`
4. Teach mode — fallback when escalation is disabled, offline, or also fails

## Performance targets (§1, §9.3)

| Path | Coverage | Latency |
|---|---|---|
| Grammar match | ~50% | < 900 ms end-to-end |
| Embedding match | ~35% | < 950 ms end-to-end |
| Cloud escalation (default target) | ~15% | 2–3 s |
| Local 3B LLM (opt-in, off by default) | — | ~4.4 s tool call, ~10.6 s paragraph |

Weighted average at 85% fast-path coverage: ~1.5s, comparable to Siri/Google
Assistant felt-responsiveness on a laptop with no GPU.

**The local 3B row is why it is no longer the default** (ADR 0001). Phase 0's
11.3 tok/s was measured on 4-6 token generations; at ~88ms/token a realistic
tool call is ~4.4s and a paragraph ~10.6s. The original "4-5 s" figure here
was an estimate that a length-realistic benchmark does not support. Re-measure
before trusting any local-path latency claim.

## Memory budget at 16GB RAM (§9.1)

| Component | RAM |
|---|---|
| Windows + normal apps | 5–6 GB |
| Whisper `small` int8 | 0.5 GB |
| multilingual-e5-small | 0.2 GB |
| Kokoro TTS | 0.3 GB |
| Qwen2.5-3B Q4 | 2.2 GB |
| **Total with 3B** | **~9 GB** — comfortable |

RAM is not the constraint on this hardware — **memory bandwidth** is. CPU
inference is bandwidth-bound, not core-bound (§9.1).

## Core tech stack

See `munshiji-full-report.md` §4 for the full, versioned table. Highlights:

- Python 3.11, `uv` package management
- Audio: `sounddevice`, Silero VAD v5, openWakeWord
- ASR: `faster-whisper` (`small`, int8), OpenVINO on Intel iGPU
- Router: `hassil`, `multilingual-e5-small`, `spaCy`, `rapidfuzz`
- Orchestrator: Ollama, Qwen2.5-3B-Instruct Q4_K_M
- Memory: SQLite, ChromaDB, `nomic-embed-text`
- TTS: Kokoro-82M (ONNX), AI4Bharat IndicTTS / `edge-tts` for hi/gu
- Windows: `pywin32`, `pycaw`, `psutil`, `pygetwindow`, `uiautomation`,
  Everything (voidtools) CLI for file search
- Network: `httpx`, FastAPI, Tailscale for remote access, MCP Python SDK
- Frontend: PySide6 or Tauri; PyInstaller → Inno Setup for packaging

## Repository layout

See `CLAUDE.md` for the top-level map and `munshiji-full-report.md` §5 for the
full annotated tree that `src/munshiji/` was scaffolded from.
