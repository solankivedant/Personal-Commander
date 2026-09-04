"""Phase 0 spike: benchmark Whisper `small` int8 and Qwen2.5-3B tok/s on the
actual target machine.

Source: munshiji-full-report.md Phase 0 (§11) and §9 (performance targets).
Run this BEFORE writing any product code — the gate is:

    if ASR p50 latency > 600ms  or  LLM throughput < 10 tok/s:
        revisit model choices (config/default.yaml, .claude/rules/architecture-and-router.md)
        before starting Phase 1.

Usage:
    uv run python scripts/benchmark.py                # both benchmarks
    uv run python scripts/benchmark.py --asr-only
    uv run python scripts/benchmark.py --llm-only
    uv run python scripts/benchmark.py --llm-model qwen2.5:3b-instruct-q4_K_M
"""

from __future__ import annotations

import argparse
import statistics
import struct
import time
import wave
from pathlib import Path

OLLAMA_URL = "http://localhost:11434"
SAMPLE_RATE = 16_000


def _synthetic_wav(path: Path, seconds: float = 5.0) -> Path:
    """Generate a synthetic speech-shaped WAV (not real speech) purely to
    exercise the ASR pipeline's decode path for latency measurement. This is
    NOT a substitute for testing against real recorded utterances — swap in
    a real sample under tests/fixtures/ once one exists, and re-run before
    trusting these numbers for the Phase 0 gate.
    """
    import math
    import random

    n_samples = int(SAMPLE_RATE * seconds)
    random.seed(0)
    samples = []
    # A handful of overlapping tones plus noise, loosely mimicking the
    # broadband energy of speech so faster-whisper has something to chew on.
    freqs = (180, 420, 900, 1800)
    for i in range(n_samples):
        t = i / SAMPLE_RATE
        val = sum(math.sin(2 * math.pi * f * t) for f in freqs) / len(freqs)
        val += (random.random() - 0.5) * 0.05
        samples.append(int(max(-1.0, min(1.0, val)) * 32767 * 0.3))

    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return path


def benchmark_asr(runs: int = 5, duration_s: float = 2.0, wav_path: Path | None = None) -> None:
    """Benchmark faster-whisper `small` int8 latency (§9, ASR row of the
    latency budget table — target < 350-600ms). The target is specified for
    a typical post-VAD command length (~1-3s of speech), not an arbitrary
    clip.

    IMPORTANT: pass a real speech `wav_path` if at all possible. Synthetic
    tone+noise audio (the fallback below) has no natural phonetic stopping
    point, so Whisper often decodes to its token cap regardless of clip
    length — that produces inflated, meaningless latency numbers. A quick way
    to get real speech without a microphone: Windows SAPI via PowerShell's
    System.Speech.Synthesis.SpeechSynthesizer.
    """
    from faster_whisper import WhisperModel

    tmp_dir = Path(__file__).resolve().parent.parent / ".bench_tmp"
    tmp_dir.mkdir(exist_ok=True)
    using_synthetic = wav_path is None
    if wav_path is None:
        print("WARNING: no --wav given, falling back to synthetic tone+noise audio. "
              "This measures worst-case decode-to-token-cap latency, NOT realistic "
              "ASR latency. Pass --wav pointing at a real speech clip instead.")
        wav_path = _synthetic_wav(tmp_dir / f"synthetic_{duration_s:.0f}s.wav", seconds=duration_s)

    print(f"\n=== ASR benchmark: faster-whisper `small`, int8, CPU ({wav_path.name}) ===")
    print("Loading model (first run downloads ~480MB)...")
    load_start = time.perf_counter()
    model = WhisperModel("small", device="cpu", compute_type="int8")
    load_s = time.perf_counter() - load_start
    print(
        f"Model load time: {load_s:.2f}s (one-time cost; keep the model warm — "
        "construct once at boot, never per-request)"
    )

    latencies_ms: list[float] = []
    transcript = ""
    for i in range(runs):
        start = time.perf_counter()
        segments, info = model.transcribe(
            str(wav_path), language="en", vad_filter=not using_synthetic
        )
        segs = list(segments)  # force full decode
        transcript = " ".join(s.text.strip() for s in segs)
        elapsed_ms = (time.perf_counter() - start) * 1000
        latencies_ms.append(elapsed_ms)
        print(f"  run {i + 1}/{runs}: {elapsed_ms:.0f} ms  ->  \"{transcript}\"")

    p50 = statistics.median(latencies_ms)
    p95 = sorted(latencies_ms)[max(0, int(len(latencies_ms) * 0.95) - 1)]
    print(
        f"\nASR p50: {p50:.0f} ms | p95: {p95:.0f} ms | "
        "target: < 600 ms (gate), < 350 ms (ideal, §9.3)"
    )
    if p50 > 600:
        print("GATE FAILED: ASR p50 exceeds 600ms. Consider the OpenVINO backend "
              "(§9.2 #4) or revisit the model size before Phase 1.")
    else:
        print("Gate passed.")
    if using_synthetic:
        print("NOTE: synthetic audio used — treat this number as unreliable. "
              "Re-run with --wav pointing at real speech before trusting it "
              "for the Phase 0 gate.")


def benchmark_llm(model: str, runs: int = 5) -> None:
    """Benchmark local Ollama LLM throughput (§9.1 tok/s table). Requires
    Ollama running (`ollama serve`, usually auto-started) and the model
    pulled (`ollama pull <model>`)."""
    import httpx

    print(f"\n=== LLM benchmark: {model} via Ollama ===")
    prompt = (
        "You are a voice assistant tool router. Given the user's request, "
        "reply with the single best matching tool name and nothing else.\n"
        "Request: move all PDF files from Desktop to Documents folder."
    )

    with httpx.Client(base_url=OLLAMA_URL, timeout=120.0) as client:
        try:
            client.get("/api/version")
        except httpx.ConnectError as exc:
            raise SystemExit(
                "Could not reach Ollama at http://localhost:11434 — is it "
                "installed and running? See "
                ".claude/agents/router-engineer.md and munshiji-full-report.md §4."
            ) from exc

        tok_per_s: list[float] = []
        for i in range(runs):
            start = time.perf_counter()
            resp = client.post(
                "/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
            )
            resp.raise_for_status()
            elapsed = time.perf_counter() - start
            data = resp.json()
            eval_count = data.get("eval_count", 0)
            eval_duration_ns = data.get("eval_duration", 0)
            rate = (eval_count / (eval_duration_ns / 1e9)) if eval_duration_ns else 0.0
            tok_per_s.append(rate)
            print(
                f"  run {i + 1}/{runs}: {rate:.1f} tok/s "
                f"({eval_count} tokens, {elapsed:.2f}s wall)"
            )

    median_rate = statistics.median(tok_per_s) if tok_per_s else 0.0
    print(f"\nLLM median throughput: {median_rate:.1f} tok/s | gate: >= 10 tok/s (§11 Phase 0)")
    if median_rate < 10:
        print("GATE FAILED: throughput below 10 tok/s. Per docs/ARCHITECTURE.md's "
              "tok/s table, this points at either a smaller model (1.5B) or "
              "revisiting whether the LLM escalation path is viable at all on "
              "this hardware before Phase 4.")
    else:
        print("Gate passed.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asr-only", action="store_true")
    parser.add_argument("--llm-only", action="store_true")
    parser.add_argument("--llm-model", default="qwen2.5:3b-instruct-q4_K_M")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument(
        "--asr-duration", type=float, default=2.0,
        help="Synthetic-fallback clip length in seconds (only used without --wav)",
    )
    parser.add_argument(
        "--wav", type=Path, default=None,
        help="Path to a real speech WAV clip — strongly preferred over the synthetic fallback",
    )
    args = parser.parse_args()

    if not args.llm_only:
        benchmark_asr(runs=args.runs, duration_s=args.asr_duration, wav_path=args.wav)
    if not args.asr_only:
        benchmark_llm(model=args.llm_model, runs=args.runs)


if __name__ == "__main__":
    main()
