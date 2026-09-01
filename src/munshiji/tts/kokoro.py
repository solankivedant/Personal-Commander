"""Kokoro-82M via ONNX Runtime, streamed sentence-by-sentence. Phase 1."""

from __future__ import annotations

import re
from pathlib import Path

import structlog
from kokoro_onnx import Kokoro

from munshiji.audio.playback import PLAYBACK_SAMPLE_RATE, AudioPlayback

logger = structlog.get_logger(__name__)

DEFAULT_MODEL_DIR = Path(__file__).resolve().parents[3] / "data" / "models" / "kokoro"
# int8 quantized — smallest/fastest variant, fits this project's CPU/no-CUDA
# target (docs/ARCHITECTURE.md §9); kokoro-onnx also offers fp16 and full
# fp32 .onnx files under the same release if quality ever needs to trump size.
MODEL_FILENAME = "kokoro-v1.0.int8.onnx"
VOICES_FILENAME = "voices-v1.0.bin"

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?।])\s+")


def _split_sentences(text: str) -> list[str]:
    """Split on sentence-ending punctuation (incl. Hindi/Gujarati danda `।`).
    Deliberately simple — real Indic sentence segmentation is Phase 6 scope.
    """
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text.strip()) if s.strip()]


class KokoroTts:
    """Streams TTS sentence-by-sentence rather than waiting for the full
    response — perceived latency is time-to-first-audio, per
    docs/ARCHITECTURE.md L8.

    Per `.claude/rules/licensing-and-ip.md`, model weights are never bundled
    in the repo/installer. Kokoro-82M's weights (MODEL_FILENAME +
    VOICES_FILENAME below, both Apache 2.0) must be downloaded from the
    upstream kokoro-onnx release and placed under `model_dir` before first
    use — this class deliberately does not auto-fetch from a hardcoded URL
    (the real first-run download-and-accept flow with a displayed licence is
    Phase 8's onboarding wizard, not this one). Note the kokoro-onnx project
    has renamed these release assets before (v0.19 -> v1.0) — if this error
    fires with filenames that 404, check
    https://github.com/thewh1teagle/kokoro-onnx/releases for the current
    names and update MODEL_FILENAME/VOICES_FILENAME above.
    """

    def __init__(
        self,
        voice: str,
        model_dir: Path = DEFAULT_MODEL_DIR,
        playback: AudioPlayback | None = None,
    ) -> None:
        model_path = model_dir / MODEL_FILENAME
        voices_path = model_dir / VOICES_FILENAME
        if not model_path.exists() or not voices_path.exists():
            raise FileNotFoundError(
                f"Kokoro model files not found in {model_dir}. Download "
                f"'{MODEL_FILENAME}' and '{VOICES_FILENAME}' from the "
                "kokoro-onnx project's GitHub releases "
                "(https://github.com/thewh1teagle/kokoro-onnx/releases) and "
                f"place them in {model_dir}."
            )
        self._kokoro = Kokoro(str(model_path), str(voices_path))
        self._voice = voice
        self._playback = playback or AudioPlayback()

    def speak(self, text: str) -> None:
        """Synthesize and play `text`, one sentence at a time."""
        sentences = _split_sentences(text) or [text.strip()]
        for sentence in sentences:
            if not sentence:
                continue
            samples, sample_rate = self._kokoro.create(sentence, voice=self._voice)
            if sample_rate != PLAYBACK_SAMPLE_RATE:
                logger.warning(
                    "kokoro_sample_rate_mismatch",
                    expected=PLAYBACK_SAMPLE_RATE,
                    got=sample_rate,
                )
            self._playback.play(samples, sample_rate=sample_rate)

    def stop(self) -> None:
        self._playback.stop()
