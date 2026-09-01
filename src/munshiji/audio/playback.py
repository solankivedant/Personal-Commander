"""24kHz PCM playback with barge-in support (stop on wake-word re-fire). Phase 1."""

from __future__ import annotations

import threading

import numpy as np
import sounddevice as sd

PLAYBACK_SAMPLE_RATE = 24_000


class AudioPlayback:
    """24kHz PCM output. `stop()` is barge-in: the FSM calls it the moment the
    wake word or push-to-talk hotkey re-fires during SPEAKING, so the user
    doesn't have to wait out a full response to interrupt it.
    """

    def __init__(self, device: str | None = None) -> None:
        self._device = None if device in (None, "default") else device
        self._stream: sd.OutputStream | None = None
        self._lock = threading.Lock()

    def play(self, pcm: np.ndarray, sample_rate: int = PLAYBACK_SAMPLE_RATE) -> None:
        """Blocking play of one chunk (typically one sentence, called
        repeatedly by the streaming TTS layer). stop() from another thread
        aborts the in-flight chunk.
        """
        with self._lock:
            self._stream = sd.OutputStream(
                samplerate=sample_rate,
                channels=1,
                dtype="float32",
                device=self._device,
            )
            self._stream.start()
        try:
            self._stream.write(pcm.astype(np.float32))
        finally:
            with self._lock:
                if self._stream is not None:
                    self._stream.stop()
                    self._stream.close()
                    self._stream = None

    def stop(self) -> None:
        with self._lock:
            if self._stream is not None:
                self._stream.abort()
                self._stream.close()
                self._stream = None
