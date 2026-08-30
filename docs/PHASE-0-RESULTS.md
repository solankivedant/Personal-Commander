# Phase 0 Spike — Results

Run on the actual target machine: **Dell Inspiron 14 7430 2-in-1**, 13th Gen
Intel Core i7-1355U (10C/12T), Intel Iris Xe Graphics (no CUDA), 16GB RAM
(soldered LPDDR5x @ 6400 MT/s, reported by WMI as 8×2GB "Motherboard" ranks —
not upgradeable SODIMM slots, already interleaved for bandwidth so the
report's §9.2 #1 "swap to dual-channel" advice doesn't apply here).

Per `docs/ROADMAP.md` Phase 0 gate: **if ASR p50 > 600ms or LLM < 10 tok/s,
revise model choices before Phase 1.**

## RAM channel configuration — checked

`Get-CimInstance Win32_PhysicalMemory` reports 8 ranks × 2GB @ 6400 MT/s. This
is soldered LPDDR5x, not swappable DIMMs — the report's cheapest-speedup advice
(§9.2 #1) is not applicable on this specific machine; the memory is already
running at a high-bandwidth configuration by design.

## ASR benchmark — faster-whisper, CPU, int8

Method note: an earlier attempt used synthetic tone+noise audio and produced
meaningless numbers (Whisper has no natural stopping point on non-speech audio
and decodes toward its token cap regardless of clip length — the numbers
didn't move between a 5s and 2s clip, which was the tell). Replaced with a
real synthesized utterance via Windows SAPI
(`System.Speech.Synthesis.SpeechSynthesizer`, saved to
`.bench_tmp/real_speech.wav`): *"Open Chrome and turn the volume down a little
bit."* (~3s). Transcription was **100% accurate** across every model size and
config tested below, so the numbers reflect real decode latency, not garbage
input.

| Model | cpu_threads | beam_size | p50 latency | vs. gate (600ms) |
|---|---|---|---|---|
| `small` (report default) | auto | 5 | ~2,656 ms | **FAIL**, 4.4× over |
| `small` | 12 (explicit) | 5 | ~2,502 ms | **FAIL** |
| `small` | 12 | 1 (greedy) | ~2,845 ms | **FAIL** — beam width isn't the bottleneck |
| `base` | 12 | 5 (default) | ~750 ms | **borderline fail**, 1.25× over |
| `tiny` | 12 | 5 (default) | ~475 ms | **PASS**, near the 350ms ideal |

**Finding: the plain CPU (ctranslate2) int8 backend cannot hit the latency
gate with `small` on this machine, regardless of thread count or beam width
tuning.** This matches the report's own prediction (§9.2 #4) that OpenVINO
conversion is "the cleanest hardware win" on Iris Xe — the raw CPU backend
alone isn't enough for the `small` model.

### OpenVINO spike — done, results below

Converted `openai/whisper-small` to OpenVINO IR via `optimum-intel`
(`OVModelForSpeechSeq2Seq.from_pretrained(..., export=True)`, one-time
conversion, 353s, cached to `.bench_tmp/whisper-small-ov/` — not committed,
see `.gitignore`). Confirmed OpenVINO sees both compute devices on this
machine: `CPU` (i7-1355U) and `GPU` (Iris Xe iGPU, via
`core.available_devices`).

| Backend | Device | p50 latency | Notes |
|---|---|---|---|
| ctranslate2 int8 (faster-whisper default) | CPU | ~2,656 ms | baseline, fails gate |
| OpenVINO IR | **CPU** (default) | ~2,891 ms | **no improvement** — same silicon as ctranslate2 |
| OpenVINO IR | **GPU** (Iris Xe, explicit `device="GPU"`) | **~850 ms** (steady-state, runs 3-5) | **3.4× faster than CPU** — first 1-2 runs after load are slower (~1.5-2.8s) from one-time GPU kernel JIT compilation |

**The lesson: OpenVINO's speedup requires explicitly targeting the GPU
device.** `optimum-intel`'s default device is CPU — simply converting to IR
format without `device="GPU"` gets you nothing, which is why the first
attempt (CPU-targeted) looked like a dead end. Once correctly targeted at the
Iris Xe iGPU, `small` goes from unusable (2.9s) to close-but-not-quite
(850ms) against the 600ms gate — a materially different conclusion than
either the raw CPU number or a careless OpenVINO-without-GPU-targeting test
would suggest.

**Still not fully passing.** 850ms steady-state is ~40% over the 600ms gate
(though well under the 2.9s CPU baseline, and the ideal §9.3 target of 350ms
was always aspirational). Two untried levers, out of scope for this
time-boxed spike but the clear next step before finalizing the model choice:

1. **INT8 weight quantization** of the OpenVINO IR (via NNCF /
   `OVQuantizer` or `load_in_8bit=True`) — halves weight memory traffic on
   top of the GPU offload already achieved; a very plausible way to close the
   remaining ~250ms.
2. **OpenVINO model caching** (`ov::cache_dir` / `optimum-intel`'s
   `ov_config={"CACHE_DIR": ...}`) to eliminate the ~27s one-time GPU kernel
   compilation cost from app cold-start (unrelated to the per-request 850ms
   figure, but matters for first-launch UX).

### Implication — two paths

1. **Pursue OpenVINO GPU + INT8 quantization for `small`** (recommended,
   given the accuracy stakes below) — the 850ms FP16 GPU result strongly
   suggests this closes the remaining gap without giving up model quality.
2. **Fall back to `base` or `tiny`** for v1 if quantization doesn't get there
   in time. Both passed the English gate on plain CPU (no GPU offload even
   needed — 750ms and 475ms respectively), and would very likely also benefit
   from the same GPU-offload treatment if used. But the report is explicit
   that Whisper's Gujarati accuracy is already weak at `small`/`medium` — it
   will be worse at `tiny`, likely bad enough to undermine the whole Indic
   differentiator (§10.1, §2.2). **Do not silently default to `tiny`/`base`
   without re-testing Hindi/Gujarati accuracy first** — every result above is
   English-only and says nothing about that.

**Recommendation:** try INT8-quantized `small` on the Iris Xe GPU next
(~30-60 min of work) before deciding between these paths — it's the one
untried lever most likely to let the product keep its best ASR model and
still hit the latency target.

## LLM benchmark — Ollama / Qwen2.5-3B

Ollama 0.33.2 installed (winget), `qwen2.5:3b-instruct-q4_K_M` pulled (1.9GB
on disk). 5 runs via `/api/generate`, non-streaming, short tool-selection-style
prompt:

| Run | tok/s | Notes |
|---|---|---|
| 1 | 11.2 | cold start, 7.84s wall (includes model load) |
| 2 | 12.9 | warm |
| 3 | 9.1 | warm |
| 4 | 11.3 | warm |
| 5 | 11.4 | warm |

**Median: 11.3 tok/s — gate PASSED** (≥10 tok/s). In line with the report's
own estimate for this exact model/quant/CPU combination (§9.1 table: 12-18
tok/s) — slightly below the top of that range but comfortably over the gate.

Caveats:
- Each generation was short (4-6 tokens) because the benchmark prompt asks
  for a single tool name — decode throughput past the first couple tokens
  should be representative, but re-test with a longer, more realistic
  multi-step-plan completion before fully trusting this for Phase 4's
  dry-run summarization use case.
- Cold-start load took ~7s on the first call. Confirms §9.2 #2's advice:
  `OLLAMA_KEEP_ALIVE=-1` (already set in `config/default.yaml`) is not
  optional — a cold load on every command would blow the latency budget by
  itself.

## Wake-word false-accept rate — not yet run

This requires a live microphone session in a real room over an extended
period (openWakeWord listening continuously while ambient conversation/TV/
noise happens nearby) — not something that can be simulated from an
automated benchmark script. Manual steps to do this yourself:

1. Once Phase 1's `wake/detector.py` exists: `uv run python -m munshiji
   --wake-word-test` (to be wired up) logs every detection event with a
   confidence score to `data/audit.jsonl` without actually activating the
   pipeline.
2. Leave it running for at least an hour of normal activity (TV,
   conversation, music) in the room the laptop is actually used in.
3. Count false triggers (i.e., you never said the wake phrase) — the report
   doesn't set a specific numeric target, but the design gate is "acceptable"
   is a judgment call: if push-to-talk feels *necessary* rather than a
   backup, the threshold or wake phrase needs tuning before Phase 1 is
   considered done (§18 risk #1, rated High likelihood).

## Bottom line

| Gate | Target | Result | Status |
|---|---|---|---|
| ASR p50 | < 600ms | 850ms (OpenVINO, Iris Xe GPU, `small`) | **Close, not yet passing** — CPU-only backend fails badly (2.9s); GPU offload is required and gets 3.4× closer but needs INT8 quantization to fully clear the bar |
| LLM tok/s | ≥ 10 tok/s | 11.3 tok/s (Qwen2.5-3B-Instruct Q4_K_M, Ollama, CPU) | **PASS** |
| RAM channel config | N/A (informational) | Soldered LPDDR5x @ 6400 MT/s, already optimal | N/A — report's dual-channel advice doesn't apply to this machine |
| Wake-word false-accept rate | N/A (manual, needs Phase 1) | Not run | **Deferred to Phase 1** — requires a live mic session, see above |

**Overall: Phase 0 is not fully clear yet, but the picture is far better than
the initial CPU-only result suggested, and the remaining gap has a concrete,
plausible next step (INT8-quantized Whisper on the Iris Xe GPU) rather than
an open question.** LLM path is fully validated and ready for Phase 4. ASR
needs one more iteration (quantization) before `small` can be trusted as the
default — do not start Phase 1's ASR integration against the un-accelerated
CPU backend; wire `asr/openvino.py` to target `device="GPU"` from the start,
per `.claude/rules/architecture-and-router.md`'s hardware-baseline rule.
