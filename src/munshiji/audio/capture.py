"""Ring-buffer audio capture at 16kHz mono via sounddevice; rewinds into the
buffer on wake-word fire so the first syllable is not clipped. Phase 1."""

from __future__ import annotations

import queue
import threading
from typing import TYPE_CHECKING

import numpy as np
import sounddevice as sd

if TYPE_CHECKING:
    from collections.abc import Callable

FRAME_MS = 80


class RingBuffer:
    """Fixed-size circular buffer of int16 mono samples. Always filling while
    capture runs; `read_last` lets the wake-word FSM rewind into recent audio
    on wake-word fire so the first syllable of the command isn't clipped —
    per the report, the single most common bug in hobby implementations.
    """

    def __init__(self, capacity_samples: int) -> None:
        if capacity_samples <= 0:
            raise ValueError("capacity_samples must be positive")
        self._capacity = capacity_samples
        self._buf = np.zeros(capacity_samples, dtype=np.int16)
        self._write_pos = 0
        self._filled = 0
        self._lock = threading.Lock()

    @property
    def capacity(self) -> int:
        return self._capacity

    def write(self, samples: np.ndarray) -> None:
        n = len(samples)
        with self._lock:
            if n >= self._capacity:
                self._buf[:] = samples[-self._capacity :]
                self._write_pos = 0
                self._filled = self._capacity
                return
            end = self._write_pos + n
            if end <= self._capacity:
                self._buf[self._write_pos : end] = samples
            else:
                first_part = self._capacity - self._write_pos
                self._buf[self._write_pos :] = samples[:first_part]
                self._buf[: end - self._capacity] = samples[first_part:]
            self._write_pos = end % self._capacity
            self._filled = min(self._capacity, self._filled + n)

    def read_last(self, n_samples: int) -> np.ndarray:
        """Return the most recent `n_samples` (oldest-first), clamped to what
        has actually been written so far."""
        with self._lock:
            n = min(n_samples, self._filled, self._capacity)
            if n == 0:
                return np.zeros(0, dtype=np.int16)
            start = (self._write_pos - n) % self._capacity
            if start + n <= self._capacity:
                return self._buf[start : start + n].copy()
            first_part = self._capacity - start
            return np.concatenate([self._buf[start:], self._buf[: n - first_part]])


class AudioCapture:
    """Wraps sounddevice.InputStream at 16kHz mono int16, 80ms frames. Every
    frame is written into the ring buffer and pushed onto a queue that
    consumers (the wake-word detector, the FSM's VAD loop) read from.
    """

    def __init__(
        self,
        sample_rate: int,
        ring_buffer_s: float,
        device: str | None = None,
        on_frame: Callable[[np.ndarray], None] | None = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.frame_samples = int(sample_rate * FRAME_MS / 1000)
        self.ring_buffer = RingBuffer(int(sample_rate * ring_buffer_s))
        self.frames: queue.Queue[np.ndarray] = queue.Queue()
        self._device = None if device in (None, "default") else device
        self._on_frame = on_frame
        self._stream: sd.InputStream | None = None

    def _callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: object,
        status: sd.CallbackFlags,
    ) -> None:
        # Runs on PortAudio's own thread — keep this minimal, no blocking I/O.
        mono = indata[:, 0].copy()
        self.ring_buffer.write(mono)
        self.frames.put_nowait(mono)
        if self._on_frame is not None:
            self._on_frame(mono)

    def start(self) -> None:
        if self._stream is not None:
            return
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="int16",
            blocksize=self.frame_samples,
            device=self._device,
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> None:
        if self._stream is None:
            return
        self._stream.stop()
        self._stream.close()
        self._stream = None
