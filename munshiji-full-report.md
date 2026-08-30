# Sahayak — Local-First Voice Assistant for Windows
## Complete Engineering, Product & Commercial Report

**Version:** 1.0
**Date:** 29 August 2026
**Target hardware baseline:** Windows laptop, 16 GB RAM, Intel Iris integrated graphics (no CUDA)
**Codename:** *Sahayak* — placeholder; substitute your own brand

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Product Definition & Market Gap](#2-product-definition--market-gap)
3. [System Architecture](#3-system-architecture)
4. [Technology Stack](#4-technology-stack)
5. [Repository & Code Structure](#5-repository--code-structure)
6. [OS-Level Integration (Windows)](#6-os-level-integration-windows)
7. [Networking & API Layer](#7-networking--api-layer)
8. [Security & Threat Model](#8-security--threat-model)
9. [Performance Engineering](#9-performance-engineering)
10. [Indic Language Layer](#10-indic-language-layer)
11. [Build Roadmap](#11-build-roadmap)
12. [Packaging & Distribution](#12-packaging--distribution)
13. [Licensing & Intellectual Property](#13-licensing--intellectual-property)
14. [Website & Landing Page](#14-website--landing-page)
15. [Monetization & Pricing](#15-monetization--pricing)
16. [Payments & Indian Compliance](#16-payments--indian-compliance)
17. [Cost Model](#17-cost-model)
18. [Risk Register](#18-risk-register)
19. [Appendices](#19-appendices)

---

## 1. Executive Summary

### What this is

A wake-word-activated voice assistant that runs entirely on a Windows laptop and controls the actual machine — files, applications, system settings, Office documents, email — with optional internet connectivity for live data and cloud services. Unlike Siri or Google Assistant, it has a filesystem, a shell, and an extensible tool registry. Unlike existing open-source desktop agents, it is voice-first and speaks Indian languages.

### The core architectural decision

**The LLM is not the primary reasoning path.** On hardware without CUDA, a 7B model produces 8–14 second responses — unusable for voice. The architecture instead routes ~85% of commands through a deterministic grammar matcher and an embedding-based intent classifier, both sub-20ms, and escalates only genuinely complex compositional requests to a small local LLM or a cloud API.

This inversion is not a compromise forced by weak hardware. It produces a *better* product: faster on common commands, lower RAM, more accurate in Hindi and Gujarati (multilingual sentence embeddings outperform a 3B model's tool-calling in Indic languages), and it degrades gracefully when the LLM is unavailable.

### Performance targets

| Path | Coverage | Latency |
|---|---|---|
| Grammar match | ~50% | < 900 ms end-to-end |
| Embedding match | ~35% | < 950 ms end-to-end |
| Local 3B LLM | ~15% | 4–5 s |
| Cloud escalation (opt-in) | < 5% | 2–3 s |

### Commercial thesis

Sold as a one-time-purchase Windows desktop application with a perpetual licence, positioned on **privacy** (audio never leaves the device) and **Indian language support** (no competitor offers Gujarati). Distribution via a self-hosted landing page with an international merchant-of-record for tax compliance and a domestic UPI gateway for Indian buyers.

### Effort and cost

| | |
|---|---|
| Engineering effort to shippable v1 | 400–600 hours |
| Effort if forking Goose | 280–420 hours |
| Infrastructure cost, year one | ₹15,000–40,000 |
| Personal running cost (electricity) | ~₹20/month |
| Break-even at ₹1,499/licence | ~30 sales |

---

## 2. Product Definition & Market Gap

### 2.1 The competitive landscape

The existing tools fall into four categories, none of which occupy the target position.

**Local model runners** — Ollama, Jan, LM Studio, AnythingLLM. These solve model serving. Jan in particular is a polished offline ChatGPT replacement with MCP support. But it is a chat interface, not an assistant: no wake word, no voice, no persistent identity, and no ability to take actions on the machine.

**Desktop / computer-use agents** — Goose (Apache 2.0, Agentic AI Foundation), Open Interpreter (Apache 2.0, ~64k stars), UI-TARS-desktop (ByteDance), AgentS, plus commercial entrants Fazm and Lapu AI. These genuinely control the machine. Open Interpreter can drive a browser, drop into PowerShell, and paste into Excel in a single workflow. Goose has the deepest MCP extension library. But all are keyboard-first or push-to-talk; none has always-on wake-word voice, and none supports Indian languages.

**Voice pipelines** — Hugging Face's `speech-to-speech` (open-sourced with Cerebras, July 2026; Silero VAD v5 → Parakeet TDT or Whisper → llama.cpp/vLLM → Qwen3-TTS or Kokoro-82M, behind an OpenAI-Realtime-compatible API), and the Home Assistant Assist stack. These solve the voice problem completely and are maintained. But they talk; they do not act on your filesystem.

**Personal RAG** — Khoj. Self-hostable second brain over your own documents. Solves long-term memory; does nothing else.

### 2.2 The unserved intersection

| | Wake word | Local-only | Windows native | Real file/app control | Hindi/Gujarati |
|---|---|---|---|---|---|
| Jan / Ollama | ✗ | ✓ | — | ✗ | ✗ |
| Goose | ✗ | ✓ | ✓ | ✓ | ✗ |
| Open Interpreter | ✗ | ✓ | ✓ | ✓ | ✗ |
| UI-TARS | ✗ | ✓ | ✓ | ✓ | ✗ |
| HF speech-to-speech | ✓ | ✓ | ✓ | ✗ | partial |
| Home Assistant Assist | ✓ | ✓ | ✗ | ✗ | ✗ |
| Fazm | ✓ | ✓ | ✗ (macOS) | ✓ | ✗ |
| **Sahayak** | ✓ | ✓ | ✓ | ✓ | ✓ |

Two columns are genuinely unserved: **wake-word voice combined with real Windows control**, and **Indian languages anywhere in the stack**. The second is not a minor gap — every project listed is English-first, and there is no maintained Gujarati voice assistant of any kind, commercial or open source.

### 2.3 Positioning statement

> A voice assistant that actually runs your laptop — in Hindi, Gujarati, or English — without sending a single word of audio to anyone's server.

### 2.4 Build vs fork

**Recommendation: do not build all nine layers.**

| Layer | Decision | Rationale |
|---|---|---|
| L0–L2 (audio, wake, ASR) | **Integrate** HF speech-to-speech | Maintained, solved, saves ~10 h |
| L3 (router) | **Build** | Core differentiator, no equivalent exists |
| L4 (orchestrator) | **Fork** Goose or build thin | MCP support comes free |
| L5–L6 (tools, execution) | **Build** | Windows-specific, no equivalent |
| L7 (memory) | **Integrate** Chroma / Khoj patterns | Standard |
| L8 (TTS) | **Integrate** Kokoro | Solved |
| Indic layer | **Build** | The novel contribution |

Spend effort on L3, L5–L6, and the Indic layer. Borrow the rest.

> ⚠️ **Note on Piper TTS:** Piper was archived in October 2025. It still functions but is unmaintained. Use **Kokoro-82M** (Apache 2.0, ~80 MB, ONNX-exportable, excellent CPU performance) or **Qwen3-TTS**. Any tutorial recommending Piper predates this.

---

## 3. System Architecture

### 3.1 Layer diagram

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

★ = the layer that defines this product.

### 3.2 Layer specifications

#### L0 — Audio I/O

- **Capture:** `sounddevice` at 16 kHz mono, int16, 80 ms frames.
- **Ring buffer:** 3-second circular buffer, always filling. On wake-word fire, rewind into it so the first syllable of the command is not clipped. This is the single most common bug in hobby implementations.
- **Endpointing:** Silero VAD v5. Silence threshold 280–320 ms. Below ~250 ms it cuts users off mid-thought; the commonly cited 500 ms adds a needless quarter-second to every interaction.
- **Output:** 24 kHz PCM to the default device, with barge-in support (stop playback when wake word re-fires).

#### L1 — Wake word & state machine

- **Detector:** openWakeWord, ~1–2% CPU continuous. Alternative: Picovoice Porcupine (better accuracy, free tier, paid custom-phrase training).
- **State machine:**

```
IDLE ──wake/hotkey──▶ LISTENING ──VAD silence──▶ TRANSCRIBING
  ▲                                                    │
  │                                                    ▼
SPEAKING ◀── ACTING ◀── ROUTING ◀────────────────  (text)
  │                        │
  └──── barge-in ──────────┘
```

- **Always ship a push-to-talk hotkey** as a parallel entry into `LISTENING`. Wake words fail in noise, and users on calls cannot say the phrase aloud.
- **Debounce:** 1.5 s minimum between wake events.

#### L2 — ASR

- **Engine:** `faster-whisper`, model `small` (multilingual) at int8 quantization on CPU.
- **On Intel iGPU:** convert via `optimum-intel` to OpenVINO IR, or use `whisper.cpp`'s OpenVINO encoder backend. This is the cleanest hardware win available on Iris.
- **Language handling:** do not auto-detect on every utterance — it costs time and flip-flops. Detect once per session, cache, allow explicit override by voice command.
- **`initial_prompt` seeding:** pass 2–3 representative Hinglish sentences to bias transcription style toward romanized output rather than Devanagari.

#### L3 — Router ★

The defining layer. Three stages, first match wins.

**Stage 1 — Grammar.** `hassil` (the Home Assistant intent library) with YAML-defined templates:

```yaml
intents:
  set_volume:
    data:
      - sentences:
          - "set volume to {level} [percent]"
          - "volume {level}"
          - "[make it] (louder|quieter)"
  open_app:
    data:
      - sentences:
          - "open {app}"
          - "(launch|start|run) {app}"
```

Latency < 10 ms, zero RAM, fully deterministic. Handles ~50% of daily commands.

**Stage 2 — Embeddings.** `multilingual-e5-small` (~120 MB) encodes 15–25 example utterances per intent at build time into a vector index. At runtime, encode the transcript and take cosine nearest-neighbour. Accept above threshold 0.75.

Latency ~15 ms. Generalizes to paraphrase — "make it louder" lands near "volume up" without enumeration. **Critically: a multilingual encoder places Hindi and Gujarati phrasings in the same vector space as English examples**, so one set of training data often covers three languages.

**Stage 3 — LLM escalation.** Only if both fail. See L4.

**Stage 4 — Teach mode.** If the LLM is disabled or also fails: *"I don't know that one. What should I do?"* The user demonstrates or names an existing intent; the utterance is appended to that intent's examples and the index rebuilds in under a second. Over weeks, LLM fallback rate declines monotonically — the assistant gets *faster* with use, which is the opposite of an LLM-only design.

**Slot extraction:** spaCy NER for dates, times, numbers, and durations; `rapidfuzz` for fuzzy-matching application and file names against an actual index of installed programs. Fuzzy matching is what rescues you when Whisper transcribes "Chrome" as "Chrom" or "क्रोम".

#### L4 — Orchestrator

- **Model:** Qwen2.5-3B-Instruct Q4_K_M via Ollama. (7B is correct on a CUDA machine; on this baseline it is 8–14 s and unusable.)
- **Loop:** propose tool call → validate against pydantic schema → execute → feed result → repeat. **Hard cap 5 iterations.**
- **Prompt layout is load-bearing.** Ollama caches the KV state of a stable prefix. Order must be: system prompt → tool schemas → *then* volatile context (time, active window, recent turns). Changing one character early in the prompt discards the entire cache and forces a full re-prefill — seconds on CPU.
- **Tool subsetting:** embed tool descriptions; retrieve top 8–12 relevant per query. A 3B model's tool-selection accuracy falls off sharply past ~15 options in context.
- **History:** 3–5 turns maximum. Long histories confuse small models.
- **Retry:** one retry on malformed JSON with a repair prompt; then fail to teach mode.

#### L5 — Tool Registry

Decorator-based, schema auto-generated from type hints and docstring:

```python
@tool(tier="local", risk="confirm", tags=["files"])
def move_files(source_dir: str, pattern: str, dest_dir: str) -> str:
    """Move files matching a glob pattern from one folder to another."""
```

Three orthogonal attributes on every tool:

| Attribute | Values | Purpose |
|---|---|---|
| `tier` | `local` / `lan` / `net` | Privacy boundary |
| `risk` | `safe` / `confirm` / `blocked` | Confirmation gating |
| `tags` | free-form | Retrieval subsetting |

#### L6 — Execution

Every tool: hard timeout, catches its own exceptions, returns a structured string the model can read. `confirm`-risk tools speak the intended action and block on a spoken yes.

#### L7 — Memory

Three genuinely distinct tiers:

| Tier | Store | Contents | TTL |
|---|---|---|---|
| Conversation | in-memory ring | last 3–5 turns | session |
| Working state | dict | last file, last app, last result | session |
| Long-term | SQLite + Chroma | preferences, facts, document index | permanent |

Working state is what makes *"open it"* and *"send that to him"* resolve. Two Chroma collections, kept separate: `user_facts` and `documents`. Embed documents with `nomic-embed-text`.

#### L8 — TTS

- **Engine:** Kokoro-82M via ONNX Runtime, CPU.
- **Stream sentence-by-sentence.** Do not wait for the full response. Perceived latency is time-to-first-audio, not time-to-complete. This roughly halves the felt delay on LLM-path responses.
- **Indic:** Kokoro's Hindi coverage is limited and Gujarati absent. Fall back to AI4Bharat IndicTTS (local) or `edge-tts` (network tier, free, excellent `hi-IN` and `gu-IN` neural voices).

#### Cross-cutting

- **Event bus:** layers publish/subscribe rather than calling each other directly. Makes the GUI, the audit log, and the HTTP API pure subscribers.
- **Config:** single YAML. No behaviour constants in code.
- **Audit log:** append-only JSONL. Every action, arguments, result, timestamp, and which router stage decided it. This is the only thing that will save you when debugging "why did it delete that" three days later.

---

## 4. Technology Stack

### 4.1 Core runtime

| Layer | Component | Version/Variant | Licence | Size |
|---|---|---|---|---|
| Language | Python | 3.11 | PSF | — |
| Package mgmt | `uv` | latest | MIT/Apache | — |
| Audio | `sounddevice` + PortAudio | 0.4.x | MIT | small |
| VAD | Silero VAD | v5 | MIT | 2 MB |
| Wake word | openWakeWord | latest | Apache 2.0 | 15 MB |
| ASR | faster-whisper | `small` int8 | MIT (CTranslate2) | 480 MB |
| Grammar | hassil | latest | Apache 2.0 | small |
| Embeddings | multilingual-e5-small | ONNX | MIT | 120 MB |
| Classifier | scikit-learn | 1.5+ | BSD-3 | — |
| NER | spaCy `en_core_web_sm` | 3.7 | MIT | 15 MB |
| Fuzzy match | rapidfuzz | 3.x | MIT | small |
| LLM serving | Ollama | 0.x | MIT | — |
| LLM weights | Qwen2.5-3B-Instruct Q4_K_M | — | **verify — see §13** | 2.2 GB |
| Vector store | ChromaDB | 0.5+ | Apache 2.0 | — |
| Doc embeddings | nomic-embed-text | — | Apache 2.0 | 270 MB |
| TTS | Kokoro-82M | ONNX | Apache 2.0 | 82 MB |
| Validation | pydantic | 2.x | MIT | — |
| Config | PyYAML | 6.x | MIT | — |

**Total install footprint:** ~3.5 GB with the 3B model, ~1.3 GB without.

### 4.2 Windows integration

| Purpose | Library | Notes |
|---|---|---|
| COM automation | `pywin32` | Outlook, Excel, Word — no API key |
| Audio control | `pycaw` | Per-app volume, mute |
| Windows control | `pygetwindow` | Focus, minimize, maximize |
| Process control | `psutil` | List, kill, resource stats |
| Screenshots | `mss` | Fast, multi-monitor |
| Input synthesis | `pyautogui` / `pydirectinput` | Clicks, keystrokes |
| Hotkeys | `keyboard` | Global push-to-talk |
| Brightness | `screen-brightness-control` | — |
| Registry / shell | `winreg`, `subprocess` | App discovery, netsh |
| File search | **Everything** (voidtools) CLI | Windows Search is far too slow for a voice loop |
| Credentials | `keyring` | Windows Credential Manager |
| UI Automation | `uiautomation` / `pywinauto` | For reliable app control; prefer over screenshots |

### 4.3 Network / API

| Purpose | Component |
|---|---|
| HTTP client | `httpx` (async, pooled, single shared client) |
| Local API | FastAPI + uvicorn |
| Remote access | Tailscale (WireGuard mesh) |
| Weather | Open-Meteo (no key) |
| Web search | SearxNG (self-hosted) or `ddgs` |
| Finance | `yfinance`, `jugaad-data` (NSE) |
| Google services | `google-api-python-client` (OAuth2) or IMAP/SMTP + app password |
| Phone bridge | KDE Connect CLI, or ADB, or Termux:API |
| MCP | `mcp` Python SDK (client role) |

### 4.4 Frontend / packaging

| Purpose | Component |
|---|---|
| Tray / GUI | PySide6 or Tauri (Rust shell + web UI) |
| Packaging | PyInstaller → Inno Setup, or MSIX |
| Updates | Sparkle-style appcast, or Squirrel.Windows |
| Crash reporting | Sentry (self-hosted option) |
| Telemetry | **None by default** — this is the product's premise |

### 4.5 Website / commerce

| Purpose | Component |
|---|---|
| Site | Astro or Next.js, static export |
| Hosting | Cloudflare Pages / Vercel (free tier) |
| Licence server | FastAPI on Railway/Fly.io, SQLite or Postgres |
| Payments (intl) | Lemon Squeezy or Paddle (merchant of record) |
| Payments (India) | Razorpay / Cashfree / UPI |
| Email | Resend or AWS SES |
| Analytics | Plausible (self-hosted, cookieless) |
| Docs | Docusaurus or Astro Starlight |

---

## 5. Repository & Code Structure

```
sahayak/
├── pyproject.toml              # uv, pinned, locked
├── uv.lock
├── config/
│   ├── default.yaml            # shipped defaults
│   ├── intents/
│   │   ├── system.yaml         # hassil grammars
│   │   ├── files.yaml
│   │   └── apps.yaml
│   └── examples/               # embedding training utterances
│       ├── en.jsonl
│       ├── hi.jsonl
│       └── gu.jsonl
├── src/sahayak/
│   ├── __main__.py
│   ├── bus.py                  # event bus
│   ├── config.py               # pydantic-settings
│   ├── audio/
│   │   ├── capture.py          # ring buffer
│   │   ├── vad.py
│   │   └── playback.py
│   ├── wake/
│   │   ├── detector.py
│   │   └── fsm.py              # state machine
│   ├── asr/
│   │   ├── whisper.py
│   │   └── openvino.py
│   ├── router/                 # ★ core IP
│   │   ├── grammar.py          # hassil wrapper
│   │   ├── embeddings.py       # e5 index
│   │   ├── slots.py            # NER + fuzzy
│   │   ├── teach.py            # teach mode
│   │   └── router.py           # cascade orchestration
│   ├── brain/
│   │   ├── ollama.py
│   │   ├── loop.py             # bounded tool loop
│   │   ├── prompt.py           # stable-prefix assembly
│   │   └── cloud.py            # optional escalation
│   ├── tools/
│   │   ├── registry.py         # @tool decorator
│   │   ├── system.py           # volume, power, brightness
│   │   ├── apps.py             # launch, focus, close
│   │   ├── files.py            # search, move, convert
│   │   ├── office.py           # COM: Outlook, Excel, Word
│   │   ├── web.py              # search, weather (net tier)
│   │   ├── google.py           # Gmail, Calendar (net tier)
│   │   ├── phone.py            # KDE Connect (lan tier)
│   │   └── mcp_bridge.py       # MCP client → tools
│   ├── memory/
│   │   ├── working.py
│   │   ├── facts.py            # SQLite
│   │   └── documents.py        # Chroma RAG
│   ├── tts/
│   │   ├── kokoro.py
│   │   └── indic.py
│   ├── net/
│   │   ├── client.py           # allowlisted httpx
│   │   └── api.py              # FastAPI local server
│   ├── security/
│   │   ├── confirm.py          # spoken confirmation gate
│   │   ├── undo.py             # inverse-operation stack
│   │   └── sanitize.py         # prompt-injection boundary
│   ├── licence/
│   │   └── verify.py           # Ed25519 offline check
│   └── ui/
│       ├── tray.py
│       └── overlay.py
├── tests/
│   ├── golden/
│   │   └── utterances.yaml     # 80 utterance → expected tool
│   ├── test_router.py
│   ├── test_tools.py
│   └── test_latency.py
├── scripts/
│   ├── build_index.py          # rebuild embedding index
│   ├── benchmark.py
│   └── package.py
└── installer/
    ├── sahayak.iss             # Inno Setup
    └── assets/
```

### 5.1 Engineering standards

| Concern | Standard |
|---|---|
| Dependency management | `uv` with committed lockfile. Pin Ollama model tags **by digest, not `:latest`** — an upstream retag silently changes model behaviour overnight. |
| Type checking | `mypy --strict` on `src/` |
| Linting | `ruff` |
| Testing | pytest; **golden test set is mandatory** (§19.2) |
| CI | GitHub Actions: lint, type, unit, golden set, build installer |
| Logging | `structlog` → JSONL, rotating |
| Error handling | Every tool catches its own exceptions and returns a readable failure string. Never let an exception reach the LLM loop as a traceback. |
| Config | YAML only. No behaviour constants in source. |

### 5.2 The golden test set

The thing that kills these projects is not bugs — it is *silent regression*. You tweak a system prompt and the model quietly stops selecting the right tool. Nothing crashes; quality just decays.

Maintain 80–120 utterances mapped to expected tool calls in `tests/golden/utterances.yaml`, spanning all three languages. Run after every prompt, model, or index change. Takes under two minutes. Fail CI below 92% accuracy.

---

## 6. OS-Level Integration (Windows)

### 6.1 Capability tiers

| Tier | Capability | Mechanism | Risk |
|---|---|---|---|
| 0 | Volume, mute, per-app audio | `pycaw` | safe |
| 0 | Brightness | `screen-brightness-control` | safe |
| 0 | Media keys (play/pause/next) | `keyboard` VK codes | safe |
| 0 | Lock, sleep, shutdown | `ctypes` → `user32`, `powrprof` | confirm |
| 0 | Wi-Fi / Bluetooth toggle | `netsh` via subprocess | safe |
| 0 | Screenshot | `mss` | safe |
| 0 | Battery, time, disk stats | `psutil` | safe |
| 1 | Launch app by name | Start Menu `.lnk` index + `os.startfile` | safe |
| 1 | Focus / minimize / close window | `pygetwindow` | safe |
| 1 | Kill process | `psutil` | confirm |
| 1 | Dictate into focused window | `pyautogui.write` | safe |
| 1 | Virtual desktop switch | `VirtualDesktopAccessor.dll` | safe |
| 2 | Disk-wide file search | **Everything** CLI (`es.exe`) | safe |
| 2 | Open / rename / move / copy | `pathlib`, `shutil` | confirm |
| 2 | Batch operations by pattern | glob + shutil | confirm |
| 2 | Archive / extract | `zipfile`, `py7zr` | safe |
| 3 | Read/reply Outlook mail | `win32com.client` | confirm |
| 3 | Read/write Excel | `win32com.client` or `openpyxl` | confirm |
| 3 | Calendar events | `win32com.client` | confirm |
| 3 | Document Q&A | Chroma RAG | safe |
| 4 | Screen understanding | `mss` + `moondream`/`llava` | safe |
| 5 | GUI click automation | UI Automation, `pyautogui` fallback | confirm |

### 6.2 Application discovery

Build the app index at first run and refresh weekly:

1. Enumerate `%ProgramData%\Microsoft\Windows\Start Menu\Programs` and `%AppData%\Microsoft\Windows\Start Menu\Programs` for `.lnk` files.
2. Resolve each shortcut target via `pywin32` shell links.
3. Query `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths` for registered executables.
4. Enumerate UWP packages via `Get-AppxPackage` (PowerShell subprocess).
5. Store as `{normalized_name: path}` in SQLite; match at runtime with `rapidfuzz.process.extractOne` at cutoff 75.

### 6.3 The COM advantage

`win32com.client` connects to a **running** Office instance via the ROT (Running Object Table):

```python
import win32com.client as win32
outlook = win32.GetActiveObject("Outlook.Application")
inbox = outlook.GetNamespace("MAPI").GetDefaultFolder(6)
```

No API key. No OAuth. No cloud. No network. It reads the user's actual mailbox and writes their actual spreadsheets, entirely on-device.

**This is the single most underrated capability on Windows and the strongest technical moat in the product.** Siri and Google Assistant have no equivalent and structurally never will. It is also a compelling privacy story: "reads your Outlook without your mail ever touching a server."

Caveats: requires the Office app to be installed and running; classic Win32 Office only (not the Store/UWP build); operations are synchronous and can block — always run in a worker thread with a timeout.

### 6.4 UI Automation over screenshots

For controlling third-party apps, prefer Windows UI Automation (`uiautomation` or `pywinauto`) over screenshot-and-click. UIA queries the actual control tree — it is faster, resolution-independent, and does not misfire when a dialog moves. Reserve vision-model screen understanding for applications that expose no accessibility tree (some Electron and game apps).

### 6.5 Running as a service

Ship as a user-session process, not a Windows service. Services run in Session 0 and **cannot access the interactive desktop**, which breaks every window and input tool. Use Task Scheduler at logon with "run only when user is logged on", or NSSM if you need supervision.

Add a `/health` endpoint reporting the liveness of Ollama, Whisper, the mic device, and the index.

---

## 7. Networking & API Layer

### 7.1 Privacy tiers

"Fully local" as a global switch permanently blocks live data, phone bridging, and Google integration. Replace it with a **per-tool tier**:

| Tier | Meaning | Examples |
|---|---|---|
| `local` | Never touches network | files, apps, system, COM, RAG |
| `lan` | Your network only | phone bridge, printers, NAS |
| `net` | Leaves the machine | weather, search, Gmail, Calendar, MCP |

Audio and transcripts still never leave. Only the *specific arguments* of a `net` tool do — "weather in Ahmedabad" sends the string `Ahmedabad`, not your voice, not your conversation. This is a materially different privacy posture from Siri, which uploads the audio itself, and it is the honest claim to make in marketing.

`mode: local_only` in config cleanly removes every `net` tool from the registry.

### 7.2 Outbound: domain allowlist

**Mandatory.** The assistant has shell access and reads content written by strangers. An allowlist means a malicious instruction hidden in a PDF cannot POST your files to an attacker's server, because that hostname is not in the list.

```yaml
network:
  mode: hybrid              # local_only | hybrid | full
  allowlist:
    - api.open-meteo.com
    - searx.local
    - gmail.googleapis.com
    - www.googleapis.com
    - api.anthropic.com
  timeout_s: 10
  retries: 1
  cache_ttl:
    weather: 900
    stocks: 60
    search: 300
```

Enforce in a single shared `httpx.AsyncClient` wrapper. Connection pooling and TLS reuse saves 100–300 ms per call — material at this latency budget.

### 7.3 Inbound: remote access

**Never port-forward.** An open port on a home router exposing an agent with shell access is a serious mistake, and Indian residential CGNAT usually blocks it anyway.

Use **Tailscale**: WireGuard mesh, install on laptop and phone, both receive stable private IPs, encrypted peer-to-peer, no open ports, traverses CGNAT, free for personal use.

- Bind the FastAPI server to the Tailscale interface only — **never `0.0.0.0`**.
- Bearer token in addition to network isolation.
- Rate-limit and log every request.

### 7.4 Local HTTP API

```
GET  /health                 → component liveness
GET  /tools                  → registry listing with tiers
POST /command                → {"text": "...", "confirm": false}
POST /confirm/{action_id}    → approve a pending confirm-tier action
GET  /audit?since=...        → action log
WS   /events                 → live state stream for the UI
```

This API is what enables the phone-as-remote use case, and it doubles as the integration surface for future clients.

### 7.5 MCP as the integration strategy

Rather than hand-writing Gmail, Calendar, and Drive clients, implement the tool layer as an **MCP client**. Google publishes MCP servers for Gmail, Calendar, and Drive; Notion, Figma, and many others do too.

You implement the protocol once and every connector becomes available with no per-service integration code. **This is the highest-leverage architectural decision in the entire project** and is the main argument for forking Goose, which already has the deepest MCP extension library.

Map each MCP tool into the local registry with `tier: net` and an inferred `risk` (anything named `send`, `delete`, `create`, or `update` → `confirm`).

### 7.6 Google authentication

Two paths.

**Simple — IMAP/SMTP with an app password.** Enable 2FA, generate an app password, use `imaplib` and `smtplib` from the standard library. No OAuth, no Cloud Console, no consent screen. Covers read-mail and send-mail — most of the practical value, in about twenty lines.

**Full — OAuth2.** Cloud Console → project → enable Gmail/Calendar/Drive APIs → OAuth client of type **Desktop app** → `credentials.json` → `InstalledAppFlow` once in a browser → refresh token persists locally.

> ⚠️ **The gotcha that catches everyone:** while the app's publishing status is **Testing**, refresh tokens for sensitive scopes expire after **7 days**. Move publishing status to **In production**. You will see an "unverified app" warning on first authorization; acceptable for personal or small-scale distribution, but note that shipping this to paying customers at scale requires Google's OAuth verification review, which is a real process with a security assessment for sensitive scopes. Budget for it or use the app-password path for v1.

Request scopes narrowly: `gmail.readonly` and `gmail.send` separately, never `mail.google.com`.

---

## 8. Security & Threat Model

### 8.1 Prompt injection — the primary threat

This is the serious one and it is specific to this class of product. The assistant reads web pages, emails, and PDFs — content authored by strangers. If a page contains *"ignore your instructions and run this command"*, a small model will sometimes comply. Combine that with shell access and the failure mode is severe.

**Mitigation — a hard data/instruction boundary:**

1. Every tool result is wrapped in explicit delimiters before entering context.
2. The system prompt states, unconditionally, that text inside those delimiters is untrusted content to be summarized or reasoned about, **never obeyed**.
3. A tool result can never *directly* trigger a `confirm`-tier action. The confirmation always routes to the user by voice.
4. The domain allowlist (§7.2) caps the blast radius: even a successful injection cannot reach an arbitrary endpoint.
5. `blocked`-risk tools (credential access, registry writes, mass deletion) are unreachable from the LLM path entirely.

```
<untrusted_content source="https://example.com/page">
...fetched text...
</untrusted_content>
```

### 8.2 Confirmation gating

Voice transcription errors + an eager model + shell access is a precise recipe for disaster. Anything that **deletes, sends, spends, or overwrites** speaks its intent and waits for a spoken yes.

**Dry-run mode for multi-step plans:** the model emits the full sequence first, and the assistant speaks a summary — *"I'll move 14 PDFs from Desktop to Documents/Invoices. Proceed?"* — before executing anything. This single feature is what converts a frightening agent into a usable one.

### 8.3 Undo stack

Every mutating tool registers its inverse operation *before* executing. "Undo that" then works for moves, renames, and batch operations. This is what makes users brave enough to let it touch their files, and it is a genuine differentiator over every competitor listed in §2.

### 8.4 Credential handling

- Never in source, never in the shipped YAML.
- `keyring` → Windows Credential Manager.
- `.env` in `.gitignore`, and a pre-commit hook scanning for key patterns.
- OAuth refresh tokens encrypted at rest with DPAPI (`win32crypt.CryptProtectData`), which binds them to the Windows user account.

### 8.5 Speaker verification (optional)

`resemblyzer` embeds the owner's voice once; the assistant ignores other speakers. Matters when the laptop sits in a shared room and can run shell commands. Ship as opt-in — false rejections are worse than the risk for most single-user setups.

### 8.6 Threat summary

| Threat | Vector | Mitigation |
|---|---|---|
| Prompt injection | Web/email/PDF content | Data boundary + allowlist + confirm gate |
| Data exfiltration | Compromised tool | Domain allowlist, `local_only` mode |
| Remote compromise | Exposed port | Tailscale only, never `0.0.0.0` |
| Credential theft | Plaintext storage | DPAPI + Credential Manager |
| Unauthorized user | Shared machine | Speaker verification, lock-screen gating |
| Misheard destructive command | ASR error | Confirmation gate + undo stack |
| Supply chain | Dependency compromise | Lockfile, pinned digests, SBOM |

---

## 9. Performance Engineering

### 9.1 The hardware reality

Intel Iris is integrated graphics sharing system RAM. The "128 MB" figure is BIOS pre-allocation, not dedicated VRAM. **There is no CUDA.** Every CUDA-based tutorial is irrelevant.

Memory budget at 16 GB:

| Component | RAM |
|---|---|
| Windows + normal apps | 5–6 GB |
| Whisper `small` int8 | 0.5 GB |
| multilingual-e5-small | 0.2 GB |
| Kokoro TTS | 0.3 GB |
| Qwen2.5-3B Q4 | 2.2 GB |
| **Total with 3B** | **~9 GB** — comfortable |
| (Qwen2.5-7B Q4 alternative) | 4.7 GB → ~11 GB, fits but slow |

RAM is not the constraint. **Memory bandwidth is.** CPU inference is bandwidth-bound, not core-bound.

| Model | tok/s (CPU) | Time per tool call | Verdict |
|---|---|---|---|
| Qwen2.5-7B Q4 | 5–8 | 8–14 s | Unusable for voice |
| Qwen2.5-3B Q4 | 12–18 | 3–6 s | Acceptable as escalation |
| Qwen2.5-1.5B Q4 | 25–35 | 1.5–3 s | Fast, weak at tool calling |

### 9.2 Optimizations, ranked by payoff

**1. Check RAM channel configuration.** Task Manager → Performance → Memory → "Slots used". If 16 GB is a single stick, you are running single-channel and forfeiting 40–60% of memory bandwidth — which directly caps inference speed. Swapping to 2×8 GB costs roughly ₹3,000 and can yield close to a 1.5× token-rate improvement. **This is the cheapest and largest available speedup.**

**2. Keep models warm.** Ollama unloads after 5 minutes idle; a cold 3B load is 3–8 s. Set `OLLAMA_KEEP_ALIVE=-1`. Instantiate Whisper once at boot and never reconstruct it. Usually the single biggest software win.

**3. Stable prompt prefix.** See §3.2 L4. Volatile context goes last, always.

**4. OpenVINO for Whisper.** Intel's runtime targets Iris properly. `whisper.cpp` has an OpenVINO encoder backend; `optimum-intel` converts Whisper to OpenVINO IR. The cleanest hardware win on this platform.

**5. IPEX-LLM for the LLM.** Intel maintains portable llama.cpp and Ollama builds targeting Intel GPUs including Iris Xe. Gains are real but modest — the iGPU shares the same memory bus, so the bandwidth ceiling remains. llama.cpp's Vulkan backend is a simpler alternative.

**6. Tighten VAD endpointing** to 280–320 ms. Shaves a quarter-second off every interaction.

**7. Stream everything.** ASR during speech, TTS per sentence.

### 9.3 Latency budget (target hardware, optimized)

| Stage | Fast path | LLM path |
|---|---|---|
| Wake detection | 100 ms | 100 ms |
| Endpoint silence | 300 ms | 300 ms |
| ASR (`small` int8) | 350 ms | 350 ms |
| Route decision | 10–15 ms | 3500 ms |
| Execute | 50–200 ms | 50–200 ms |
| TTS first audio | 150 ms | 150 ms |
| **Total** | **≈ 950 ms** | **≈ 4.5 s** |

At 85% fast-path coverage, the weighted average is ~1.5 s — comparable to Siri and Google Assistant in felt responsiveness, on a laptop with no GPU.

### 9.4 Recommended configuration

```yaml
asr:
  model: small
  compute_type: int8
  backend: openvino          # fallback: ctranslate2-cpu
router:
  grammar: true
  embeddings:
    model: multilingual-e5-small
    threshold: 0.75
  teach_mode: true
llm:
  enabled: true
  model: qwen2.5:3b-instruct-q4_K_M
  keep_alive: -1
  history_turns: 4
  max_tools_in_context: 12
  max_iterations: 5
tts:
  engine: kokoro
  stream: true
vad:
  silence_ms: 300
```

---

## 10. Indic Language Layer

The genuinely novel contribution. No maintained Gujarati voice assistant exists, and every project surveyed in §2 is English-first.

### 10.1 ASR

- Whisper `small`/`medium` multilingual: Hindi decent, Gujarati poor.
- **AI4Bharat (IIT Madras)** IndicWhisper and IndicConformer are trained on Indian-language corpora and substantially outperform vanilla Whisper on Gujarati. This is the correct base for Indic ASR.
- **Hinglish script control:** Whisper's output script follows detected language. Force `language="hi"` → Devanagari; force `language="en"` → romanized Hinglish. Choose per downstream requirement and seed `initial_prompt` with representative Hinglish sentences to bias style.

### 10.2 Routing — the key insight

Use a **multilingual sentence encoder** (LaBSE or `multilingual-e5-small`). Intent vectors then live in a shared cross-lingual space: examples written in English will often match Hindi and Gujarati phrasings without separate training data.

This matters more than it first appears. A 3B local model's tool-calling accuracy in Gujarati is poor. Embedding similarity in Gujarati is decent. **For Indic languages, the non-LLM path is more accurate, not less.** The architecture chosen for hardware reasons turns out to be the correct architecture for the differentiating feature.

### 10.3 LLM

Qwen2.5 is passable at Hindi, weak at Gujarati. Sarvam AI's Indic models and Gemma are better starting points where Indic reasoning genuinely matters. In practice, tool-calling in Hinglish works acceptably because command vocabulary is largely English nouns; it is freeform Gujarati that degrades.

### 10.4 TTS

| Option | Hindi | Gujarati | Local |
|---|---|---|---|
| Kokoro-82M | limited | ✗ | ✓ |
| AI4Bharat IndicTTS | ✓ | ✓ | ✓ |
| Coqui XTTS-v2 | ✓ | ✗ | ✓ |
| `edge-tts` | excellent | excellent | ✗ (`net`) |

Ship IndicTTS as the local default; offer `edge-tts` as a `net`-tier quality upgrade the user explicitly enables.

### 10.5 Design pattern

Whisper returns detected language → stored in working state → selects both the system prompt and the TTS voice. One assistant, three languages, routed automatically, no user configuration.

---

## 11. Build Roadmap

### Phase 0 — Spike (1 week, ~20 h)
Prove the hardware works before committing.
- Benchmark Whisper `small` int8 on the actual laptop
- Benchmark Qwen2.5-3B tok/s via Ollama
- Check RAM channel configuration
- Test openWakeWord false-accept rate in a real room
- **Gate:** if ASR > 600 ms or 3B < 10 tok/s, revise model choices before proceeding

### Phase 1 — Voice loop (2 weeks, ~50 h)
- L0 ring buffer + Silero VAD
- L1 wake word + FSM + push-to-talk
- L2 Whisper integration
- L8 Kokoro streaming
- Echo-back test: say something, hear it repeated
- **Deliverable:** a thing that listens and talks

### Phase 2 — Router + Tier 0/1 tools (3 weeks, ~70 h)
- `@tool` registry with tier/risk/tags
- hassil grammars for ~25 intents
- Embedding index + teach mode
- 20 system and app tools
- Golden test set v1
- **Deliverable:** genuinely useful daily driver, no LLM required

### Phase 3 — Files + confirmation + undo (2 weeks, ~50 h)
- Everything CLI integration
- File tools with confirm gating
- Undo stack
- Audit log
- **Deliverable:** safe to point at real files

### Phase 4 — LLM escalation (2 weeks, ~50 h)
- Ollama orchestrator, bounded loop
- Stable-prefix prompt assembly
- Tool subsetting by embedding
- Dry-run plan summarization
- **Deliverable:** handles compositional requests

### Phase 5 — Office + network (3 weeks, ~70 h)
- COM tools: Outlook, Excel, Word
- Allowlisted HTTP client
- Weather, search, finance
- MCP client bridge
- Google via app password
- **Deliverable:** does real work

### Phase 6 — Indic (3 weeks, ~70 h)
- IndicWhisper integration
- Multilingual embedding index, hi/gu example sets
- IndicTTS
- Language auto-routing
- **Deliverable:** the differentiator

### Phase 7 — Memory + RAG (2 weeks, ~45 h)
- SQLite facts, working state
- Chroma document index
- Screen understanding (moondream)

### Phase 8 — Packaging + licensing (3 weeks, ~70 h)
- Tray UI, onboarding wizard
- PyInstaller + Inno Setup
- Code signing
- Licence verification
- Auto-update
- **Deliverable:** shippable installer

### Phase 9 — Commercial (3 weeks, ~65 h)
- Landing page, docs
- Licence server
- Payment integration
- Support workflow

**Total: ~560 hours.** Forking Goose removes roughly Phases 4–5 scaffolding, saving 100–150 h.

---

## 12. Packaging & Distribution

### 12.1 The model download problem

A 3.5 GB installer converts poorly and costs bandwidth. **Ship a ~180 MB base installer** containing the app, wake word, grammars, and TTS. Download models on first run with a progress UI, resumable, checksum-verified, from a CDN (Cloudflare R2 has zero egress fees — significant at gigabyte scale).

Offer an offline bundle as a separate download for air-gapped or poor-connectivity users.

### 12.2 Build pipeline

```
uv sync --frozen
  → PyInstaller (--onedir, not --onefile; onefile extracts to temp on every
     launch, adding seconds to startup)
  → sign the EXE
  → Inno Setup → sahayak-setup.exe
  → sign the installer
  → upload to R2, update appcast.xml
```

### 12.3 Code signing

**Not optional for a paid product.** Unsigned executables trigger SmartScreen warnings that destroy conversion at the moment of install.

| Type | Cost/year | SmartScreen |
|---|---|---|
| OV certificate | ₹15,000–30,000 | Reputation must be earned over time/downloads |
| EV certificate | ₹25,000–50,000 | Immediate trust |

Since June 2023 both require hardware token or cloud HSM key storage. Azure Trusted Signing is the cheapest practical route for a solo developer. **Budget for EV** — the reputation-building period on OV can take months and thousands of downloads, during which every customer sees a scary warning.

### 12.4 Auto-update

Sparkle-style appcast: signed XML feed, Ed25519 signature on each release, delta updates where feasible. Never auto-update the models — they are large and the user should choose.

### 12.5 Uninstall

Must remove models, Chroma index, and config. A 3.5 GB orphan directory generates support tickets and bad reviews.

---

## 13. Licensing & Intellectual Property

> **This section is not legal advice. Read every licence text and consult a lawyer before commercial launch.**

### 13.1 Component audit

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
| Goose | Apache 2.0 | ✓ (if forking) |
| Open Interpreter | Apache 2.0 | ✓ |
| pywin32 | PSF | ✓ |
| PySide6 | **LGPL v3** | ✓ **only if dynamically linked** |
| Everything (voidtools) | Freeware | ⚠️ verify bundling terms |

### 13.2 Model weight licences — verify individually

This is the trap. Model licences vary **by size within the same family**.

- **Qwen2.5:** smaller sizes are largely Apache 2.0; the 72B uses the Tongyi Qianwen licence with a 100M-MAU threshold requiring separate application to Alibaba Cloud. Some Qwen2.5-VL variants differ from their text counterparts. **Check the specific model card for the exact model and size you ship.**
- **Llama:** Community Licence, commercial use permitted below 700M MAU, weights gated behind acceptance.
- **Gemma 3:** custom Google Terms of Use, not OSI-approved, Google reserves remote restriction rights. Gemma 4 moved to Apache 2.0.

Also distinguish two things the search results make explicit: the weights licence governs *distribution and running* of the weights. If you call a model through a hosted API instead of shipping weights, the provider's API terms govern and the redistribution/MAU triggers become the provider's burden, not yours.

**Practical recommendation for v1:** ship Apache-2.0-licensed weights only, and do not bundle weights in the installer at all — download them at first run from the original upstream source, with the licence displayed and accepted. This keeps you a *pointer* rather than a *redistributor* and materially simplifies compliance.

### 13.3 PySide6 / LGPL

LGPL v3 permits commercial closed-source use **only with dynamic linking** and the ability for users to replace the library. PyInstaller `--onedir` with Qt as separate DLLs satisfies this; static bundling does not. If this is uncomfortable, use Tauri (MIT/Apache) instead.

### 13.4 Your own licence

Recommended: **proprietary EULA, closed source, perpetual licence for the shipped major version.**

Alternative worth serious consideration: **open-core** — router, tools, and voice loop under AGPL-3.0; Indic layer, GUI, and Office/COM integration proprietary. AGPL means competitors cannot fork it into a hosted product without reciprocating, while individuals can inspect the code — which directly supports the privacy claim. For a product whose entire pitch is "trust me, nothing leaves your machine", auditability is a *feature*, not a giveaway.

### 13.5 Attribution

Ship a `THIRD_PARTY_NOTICES.txt` with every licence text, reachable from the About dialog. Generate it in CI with `pip-licenses`. Apache 2.0 requires preserving copyright and NOTICE files.

### 13.6 Trademark

"Sahayak" is a common Hindi word and likely difficult to register. Run a search on the Indian trademark registry before committing to branding. File in Class 9 (software) and Class 42 (SaaS).

Also: **do not use "Hey Siri" or "OK Google" phrasing or any confusingly similar wake word or marketing comparison in a way that implies endorsement.** Nominative comparison in a feature table is fine; imitation is not.

---

## 14. Website & Landing Page

### 14.1 Landing page vs website

A landing page is a single focused decision surface: one path, no navbar, no exits. A website is informational with full navigation. **Removing the navbar alone typically lifts conversion 20–50%**, because a landing page exists for decision-making, not exploration.

Build the landing page first. Add the marketing site later.

### 14.2 Page structure

| # | Section | Purpose | Content |
|---|---|---|---|
| 1 | Hero | Stop the scroll | Headline, subhead, 30-second demo video, primary CTA |
| 2 | Problem | Agitate | "Siri can't open your files. Google can't read your Outlook. Neither speaks Gujarati." |
| 3 | Demo | Prove | Screen recording: voice → file found → Excel updated. **Unedited, single take.** |
| 4 | Privacy | The core claim | Diagram: audio → local. Link to source or audit. Network allowlist screenshot. |
| 5 | Features | Scan | 6–8 icon cards |
| 6 | Comparison | Differentiate | The §2.2 table |
| 7 | Language | The moat | Hindi/Gujarati demo clip |
| 8 | Requirements | Qualify | Windows 10/11, 16 GB RAM, 4 GB disk. Honest about the GPU situation. |
| 9 | Pricing | Convert | Tiers, value stack |
| 10 | FAQ | De-risk | Refunds, offline use, updates, data handling |
| 11 | Final CTA | Close | Repeat offer, guarantee |

### 14.3 The demo video is the product

For a voice assistant, nobody believes text. A 30-second unedited screen recording — wake word, spoken command in Hinglish, correct action executed, spoken confirmation — will outperform every paragraph on the page. Show the latency honestly; do not cut the pause. Trust converts better than speed.

### 14.4 Technical build

- **Astro**, static export, `<200 KB` initial payload
- Self-host fonts; no Google Fonts (consistency with the privacy pitch)
- Video: self-hosted MP4 on R2, poster frame, `preload="none"`
- **Plausible** analytics — cookieless, self-hostable. Do not put Meta Pixel or Google Analytics on a privacy product's landing page; it is the single most credibility-destroying thing you could do, and observant users will check.
- Cloudflare Pages, free tier
- Lighthouse ≥ 95 on mobile

### 14.5 Content pages

- `/docs` — installation, commands, teach mode, troubleshooting
- `/privacy` — precise, technical, honest. What is stored, where, what leaves in each mode.
- `/security` — threat model summary, disclosure contact
- `/changelog`
- `/refund`, `/terms`, `/eula`

### 14.6 Copy principles

- Lead with capability, not technology. "Move every invoice into the right folder by voice" beats "local LLM with tool calling".
- Name the competitor honestly and only where you genuinely win.
- **Never overstate privacy.** If `net`-tier tools exist, say so plainly on the privacy page. A single discovered overstatement destroys the entire positioning.
- Show the Gujarati demo above the fold for Indian traffic.

---

## 15. Monetization & Pricing

### 15.1 Model selection

| Model | Fit | Verdict |
|---|---|---|
| One-time perpetual | Desktop utility, offline-capable, no server costs | **Recommended** |
| Subscription | No recurring server cost to justify it | Poor fit — you have no ongoing cost to pass on |
| Freemium | Free tier drives trial | **Recommended as complement** |
| Open-core | Free core, paid modules | Strong alternative |
| Usage-based | No per-use cost | Not applicable |

A fully local product has near-zero marginal cost. A subscription would be charging rent for something that costs you nothing to run, and users notice. **One-time purchase with paid major-version upgrades** is honest and matches the product's own philosophy.

### 15.2 Tiers

| | **Free** | **Personal** | **Pro** |
|---|---|---|---|
| Price | ₹0 | **₹1,499** one-time | **₹3,499** one-time |
| Voice loop | ✓ | ✓ | ✓ |
| Tier 0/1 tools | ✓ | ✓ | ✓ |
| Intents | 25 built-in | Unlimited + teach mode | Unlimited + teach mode |
| File operations | ✗ | ✓ | ✓ |
| LLM escalation | ✗ | ✓ | ✓ |
| **Hindi + Gujarati** | ✗ | ✓ | ✓ |
| Office/COM (Outlook, Excel) | ✗ | ✗ | ✓ |
| Document RAG | ✗ | ✗ | ✓ |
| MCP connectors | ✗ | ✗ | ✓ |
| Phone bridge | ✗ | ✗ | ✓ |
| Undo stack | ✗ | ✓ | ✓ |
| Updates | Current major | Current major | 2 years all versions |
| Support | Community | Email | Priority email |

International pricing: **$29 / $59** (not a direct INR conversion — Indian and international purchasing power differ enough to justify separate pricing, and geolocated pricing is standard practice for indie software).

### 15.3 Why the free tier is essential

A voice assistant must be *experienced*. No landing page copy can convey whether the wake word fires reliably in your room, or whether it understands your accent. The free tier is not marketing generosity — it is the only honest way to sell this category. Expect a low single-digit free-to-paid conversion rate and price accordingly.

### 15.4 Value stack framing

Rather than listing features, frame against alternatives the buyer already understands:

| Component | Standalone comparable |
|---|---|
| Voice control of Windows | ₹0 (nothing comparable exists) |
| Hindi + Gujarati support | No competitor at any price |
| Local Outlook/Excel automation | RPA tooling, ₹thousands/month |
| Document search over your own files | Enterprise search products |
| Zero telemetry | Not purchasable |

### 15.5 Launch sequence

1. **Weeks 1–4:** free tier only, no payments. Gather 100 users, fix wake-word and ASR failures against real accents and real rooms. This data is worth more than early revenue.
2. **Week 5:** founding-user pricing — 50% off, first 100 buyers, genuine deadline.
3. **Week 9:** standard pricing.
4. **Month 4+:** Pro tier once COM and MCP features are stable.

Do not launch paid before the free tier has proven the wake word works on other people's hardware. A voice product that fails on first use generates refunds and permanent negative word-of-mouth.

### 15.6 Anti-piracy — set expectations correctly

Offline licence verification is defeatable. A determined user will crack it. **Optimize for honest-buyer convenience, not for stopping piracy.**

- Ed25519-signed licence file, verified offline against an embedded public key
- Machine binding via a hashed hardware fingerprint, 3 activations, self-service deactivation
- Optional online reactivation check every 90 days that **fails open** — never break a paying user's product because of a network problem
- No dongles, no always-online, no phone-home

---

## 16. Payments & Indian Compliance

> **Not legal or tax advice. Consult a chartered accountant before launch.**

### 16.1 Two-gateway strategy

Indian and international buyers need different rails.

**Domestic (India):** Razorpay or Cashfree. UPI carries zero MDR and handles the large majority of Indian consumer transactions. Cards and netbanking as fallback. Settlement in INR.

**International:** a **merchant of record** — Lemon Squeezy or Paddle. This is the important structural choice.

### 16.2 Why merchant of record matters

Under an MoR, the legal transaction is between the customer and the MoR, not you. The MoR determines the applicable tax rate by the customer's location, collects it at checkout, and remits it to the relevant authority. You receive a payout minus their fee and file no foreign tax returns.

Without an MoR, selling digital software internationally means EU VAT (with OSS registration), US state sales tax under economic nexus rules across ~45 states, GST in Australia and Canada, and more. For a solo developer this is not a realistic burden.

MoR fees run roughly 5% + $0.50 per transaction — materially more than Stripe's ~2.9%. **That premium is the price of not having a tax problem, and it is worth paying.**

One nuance worth checking before launch: some jurisdictions treat SaaS differently from downloadable software. A desktop app with a licence component sits at an unusual intersection — confirm your product type is classified correctly in the MoR dashboard.

Note also that **Stripe India is invite-only for most Indian businesses**, which removes it as a default option.

### 16.3 Indian GST

- GST registration is mandatory once aggregate annual turnover — **including zero-rated international exports** — crosses **₹20 lakh** (₹10 lakh in special category states). Below that, voluntary registration is still sometimes useful for input tax credit and clean records.
- Software supplied to Indian customers attracts **18% GST**. Charge at checkout, file GSTR-1 monthly.
- Exports of services are zero-rated but count toward the turnover threshold — a common and expensive misunderstanding.
- International receipts need **FIRA/FIRC** documentation for export compliance. Most Indian gateways generate these automatically; confirm before choosing.
- Note: Razorpay states tax rates cannot be added to international-currency invoices, which is another reason to route international sales through an MoR.

### 16.4 Business structure

| Structure | Setup | Suitability |
|---|---|---|
| Sole proprietorship | ₹2,000–5,000 | Fine for validation |
| LLP | ₹8,000–15,000 | Good if partners |
| Private Limited | ₹15,000–25,000 | Needed for funding, better liability shield |

For a product that runs shell commands on customers' machines, the liability separation of a Pvt Ltd is worth considering earlier than turnover alone would suggest.

### 16.5 DPDP Act (India)

India's Digital Personal Data Protection Act, 2023 governs processing of personal data. **A local-first product is in an unusually strong position here** — if you process no personal data on servers, most obligations are minimal.

But note precisely: the licence server *does* process personal data (email, payment reference, hardware fingerprint). Publish a privacy notice, define retention, provide a deletion mechanism, and name a grievance contact. Rules under the Act have been evolving; verify current requirements at launch rather than relying on this document.

### 16.6 Consumer protection

- Indian e-commerce rules require clear refund policy, seller identity, and grievance officer details on the site.
- **Recommended: 14-day no-questions refund.** For software that may simply fail on a given machine's microphone or CPU, a generous refund is cheaper than disputes and better for reputation.
- Chargebacks on digital goods are hard to defend. The MoR absorbs this for international sales, which is another point in its favour.

---

## 17. Cost Model

### 17.1 Personal running cost

Software: **₹0.** Every component is free and open source.

Electricity, at Gujarat domestic tariff ~₹5–8/kWh:

| Item | Load | Monthly |
|---|---|---|
| Laptop idle, 24/7 (would run anyway) | ~15 W | ₹65–85 |
| **Marginal:** wake word always-on | ~2–3 W | ₹10–15 |
| **Marginal:** ASR, ~50 commands/day | ~20 s/day | < ₹1 |
| **Marginal:** LLM, ~8 calls/day | ~30 s/day | < ₹1 |
| **Total marginal** | | **₹15–25** |

Inference bursts are too short to matter; the always-on wake word is the only real draw.

Optional hardware: RAM reconfiguration to dual-channel ~₹3,000. USB microphone ₹800–2,500 (meaningfully improves wake-word accuracy over built-in array mics).

Optional cloud escalation at ~240 calls/month with ~1,500 input and 150 output tokens each: a very small volume. Well under ₹100/month on a small model, low hundreds on a frontier model. Prompt caching reduces it further since the system prompt and tool schemas are identical every call. **Verify current model pricing at implementation time.**

### 17.2 Business cost, year one

| Item | Cost |
|---|---|
| Domain | ₹1,200 |
| Hosting (Cloudflare Pages) | ₹0 |
| Licence server (Railway/Fly) | ₹6,000 |
| R2 storage + egress | ₹2,000 |
| **Code signing certificate (EV)** | **₹25,000–50,000** |
| Business registration | ₹5,000–25,000 |
| Email (Resend) | ₹0–3,000 |
| Plausible analytics | ₹0 (self-host) or ₹8,000 |
| **Total** | **₹40,000–95,000** |

Code signing dominates and is not optional for a paid Windows product.

### 17.3 Break-even

At ₹1,499 with ~10% MoR/gateway fees, net ~₹1,350.

| Fixed cost | Units to break even |
|---|---|
| ₹40,000 | 30 |
| ₹95,000 | 71 |

Thirty sales is a low bar. The binding constraint is not cost — it is the 560 hours of engineering.

### 17.4 Opportunity cost

At 560 hours and a nominal ₹1,500/hour freelance rate, the true build cost is ~₹8.4 lakh. At ₹1,350 net per unit, that is ~620 sales to break even on *time*.

This should inform the decision: **build it because you want it and the Indic gap is real, not because the unit economics obviously work.** Forking Goose reduces the time investment by 100–150 hours and is the single best lever on this number.

---

## 18. Risk Register

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
| 9 | Market too small (Windows + 16 GB + wants voice + Indic) | Medium | High | Validate with free tier before Pro investment |
| 10 | Big-tech competitor ships equivalent | Low | High | Local file/shell access is structurally hard for them; Indic is a durable niche |
| 11 | Support burden exceeds revenue | High | Medium | Excellent docs, in-app diagnostics, community forum before email support |
| 12 | Solo maintainer burnout | **High** | High | Ship narrow, say no, automate the golden test set |

**Risk 7 deserves emphasis.** A PyInstaller-packaged Python app that synthesizes keystrokes, takes screenshots, and runs shell commands looks exactly like malware to heuristic antivirus engines. This *will* happen. Sign everything, submit binaries to major AV vendors for whitelisting before launch, and prepare a support article. Several indie Windows apps have been effectively killed by this.

---

## 19. Appendices

### 19.1 Complete default configuration

```yaml
# config/default.yaml
app:
  name: sahayak
  language: auto              # auto | en | hi | gu
  first_run_wizard: true

audio:
  input_device: default
  sample_rate: 16000
  ring_buffer_s: 3.0

vad:
  model: silero_v5
  silence_ms: 300
  min_speech_ms: 200

wake:
  engine: openwakeword
  phrase: hey_sahayak
  threshold: 0.5
  debounce_ms: 1500
  hotkey: ctrl+alt+space

asr:
  engine: faster-whisper
  model: small
  compute_type: int8
  backend: openvino
  initial_prompt: "Chrome open karo. Volume thoda kam karo."

router:
  grammar:
    enabled: true
    dirs: [config/intents]
  embeddings:
    enabled: true
    model: multilingual-e5-small
    threshold: 0.75
    examples: config/examples
  teach_mode: true

llm:
  enabled: true
  provider: ollama
  model: qwen2.5:3b-instruct-q4_K_M
  keep_alive: -1
  history_turns: 4
  max_tools_in_context: 12
  max_iterations: 5
  temperature: 0.1

cloud:
  enabled: false
  escalate: ask               # never | ask | auto

tts:
  engine: kokoro
  voice: default
  stream: true
  indic_engine: indictts

network:
  mode: hybrid                # local_only | hybrid | full
  inbound: none               # none | tailscale
  allowlist:
    - api.open-meteo.com
    - gmail.googleapis.com
    - www.googleapis.com
  timeout_s: 10
  retries: 1

security:
  confirm_risk_tiers: [confirm]
  blocked_tools: [registry_write, format_disk, delete_permanent]
  speaker_verification: false
  undo_depth: 20

memory:
  facts_db: data/facts.sqlite
  documents:
    enabled: true
    path: data/chroma
    embed_model: nomic-embed-text
    watch_dirs: []

logging:
  level: INFO
  audit: data/audit.jsonl
  rotate_mb: 50
```

### 19.2 Golden test set format

```yaml
# tests/golden/utterances.yaml
- text: "volume thoda kam karo"
  lang: hi
  expect_tool: set_volume
  expect_args: {direction: down}
  expect_stage: grammar

- text: "open chrome"
  lang: en
  expect_tool: open_app
  expect_args: {app: chrome}
  expect_stage: grammar

- text: "make it a bit louder"
  lang: en
  expect_tool: set_volume
  expect_args: {direction: up}
  expect_stage: embeddings      # deliberately not in grammar

- text: "desktop par jitni PDF hai sab Documents me daal do"
  lang: hi
  expect_tool: move_files
  expect_stage: llm
  expect_confirm: true

- text: "મારી બેટરી કેટલી છે"
  lang: gu
  expect_tool: get_battery
  expect_stage: embeddings
```

CI gate: ≥ 92% exact tool match, ≥ 85% args match, and **100% on `expect_confirm` cases** — a missed confirmation gate is a correctness failure, not a quality metric.

### 19.3 Tool declaration example

```python
from sahayak.tools.registry import tool

@tool(
    tier="local",
    risk="confirm",
    tags=["files", "batch"],
    undo="move_files_inverse",
)
def move_files(source_dir: str, pattern: str, dest_dir: str) -> str:
    """Move files matching a glob pattern from one folder to another.

    Args:
        source_dir: Absolute path to the source folder.
        pattern: Glob pattern, e.g. '*.pdf'.
        dest_dir: Absolute path to the destination folder.
    """
```

The decorator generates the JSON schema from hints and docstring, registers the inverse for the undo stack, and marks the tool for confirmation gating.

### 19.4 Immediate next actions

1. **Check RAM channel configuration** — Task Manager → Performance → Memory → Slots used. Five seconds, and it is the largest cheap speedup available.
2. **Run Phase 0 benchmarks** before writing any product code. If the numbers do not hold on the actual machine, the model choices change.
3. **Decide fork-vs-build on Goose.** This single decision moves the timeline by 100–150 hours and determines whether MCP comes free.
4. **Verify the exact licence** of the specific model weights you intend to ship, at the specific size, on the model card.
5. **Record a 30-second demo** as soon as Phase 1 works. It is both your motivation and your entire marketing asset.

### 19.5 Sources consulted

Where this report cites current facts — model licences, the Piper archival, the Hugging Face speech-to-speech release, MoR tax handling, Indian GST thresholds — those were verified against sources in August 2026. Fast-moving items (model licences, pricing, gateway terms, DPDP rules) should be re-verified at implementation time rather than trusted from this document.

---

*End of report.*
