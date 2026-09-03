"""Silero VAD v5 endpointing, 280-320ms silence threshold. Phase 1."""

from __future__ import annotations

import time
from collections.abc import Callable

import numpy as np
import torch
from silero_vad import load_silero_vad

SPEECH_PROB_THRESHOLD = 0.5


class SileroVad:
    """Wraps Silero VAD v5 (ONNX backend via the `silero-vad` package) for
    per-frame speech probability. The model itself only accepts fixed-size
    windows — 512 samples at 16kHz, 256 at 8kHz — and raises on anything else
    (confirmed live: AudioCapture's 80ms/1280-sample frames crash it
    directly). Frames are sub-chunked into model-sized windows internally,
    with the remainder carried over to the next call, so callers can keep
    pushing whatever frame size AudioCapture hands them.
    """

    _WINDOW_SAMPLES = {8_000: 256, 16_000: 512}

    def __init__(
        self,
        sample_rate: int,
        model: Callable[[torch.Tensor, int], torch.Tensor] | None = None,
    ) -> None:
        if sample_rate not in self._WINDOW_SAMPLES:
            raise ValueError(
                f"Silero VAD only supports 8000/16000Hz, got {sample_rate}"
            )
        self.sample_rate = sample_rate
        self._window_samples = self._WINDOW_SAMPLES[sample_rate]
        self._model = model if model is not None else load_silero_vad(onnx=True)
        self._carry = np.zeros(0, dtype=np.int16)

    def speech_prob(self, frame: np.ndarray) -> float:
        buffer = np.concatenate([self._carry, frame])
        probs: list[float] = []
        window = self._window_samples
        n_complete = len(buffer) // window
        for i in range(n_complete):
            chunk = buffer[i * window : (i + 1) * window]
            audio = torch.from_numpy(chunk.astype(np.float32) / 32768.0)
            with torch.no_grad():
                probs.append(self._model(audio, self.sample_rate).item())
        self._carry = buffer[n_complete * window :].copy()
        # Max, not mean: a short burst of speech within this frame should
        # register as speech even if most of the frame was still silence.
        return max(probs) if probs else 0.0

    def is_speech(self, frame: np.ndarray) -> bool:
        return self.speech_prob(frame) >= SPEECH_PROB_THRESHOLD


class Endpointer:
    """Tracks running silence during LISTENING and signals when the utterance
    has ended. `silence_ms` should stay in the 280-320ms band (see
    docs/ARCHITECTURE.md) — shorter cuts users off mid-thought, longer adds
    needless perceived latency. `min_speech_ms` guards against endpointing on
    a burst of noise before any real speech was heard.
    """

    def __init__(
        self,
        vad: SileroVad,
        silence_ms: int,
        min_speech_ms: int,
        now_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self._vad = vad
        self._silence_ms = silence_ms
        self._min_speech_ms = min_speech_ms
        self._now_fn = now_fn
        self._speech_started_at: float | None = None
        self._last_speech_at: float | None = None

    def reset(self) -> None:
        self._speech_started_at = None
        self._last_speech_at = None

    def push_frame(self, frame: np.ndarray) -> bool:
        """Feed one frame; returns True once the utterance has ended (enough
        speech was seen, then enough trailing silence)."""
        now = self._now_fn()
        if self._vad.is_speech(frame):
            if self._speech_started_at is None:
                self._speech_started_at = now
            self._last_speech_at = now
            return False

        if self._speech_started_at is None or self._last_speech_at is None:
            return False  # silence before any speech — not endpointed yet

        speech_duration_ms = (self._last_speech_at - self._speech_started_at) * 1000
        silence_duration_ms = (now - self._last_speech_at) * 1000
        return (
            speech_duration_ms >= self._min_speech_ms
            and silence_duration_ms >= self._silence_ms
        )
