"""SileroVad sub-chunking: the model only accepts fixed 256/512-sample
windows and raises on anything else — confirmed live when AudioCapture's
80ms/1280-sample frames were fed to it directly. These tests pin the
sub-chunking + carry-over fix with a fake model, so a regression back to
"just pass the frame through" fails fast without needing real audio hardware
or the (slow) real ONNX model."""

from __future__ import annotations

import numpy as np
import torch

from munshiji.audio.vad import SileroVad


class FakeModel:
    """Records every window size it's called with and raises like the real
    model does on anything but 512 samples (16kHz) — this is what actually
    crashed in Phase 1's first live run."""

    def __init__(self) -> None:
        self.call_sizes: list[int] = []

    def __call__(self, audio: torch.Tensor, sample_rate: int) -> torch.Tensor:
        size = audio.shape[-1]
        self.call_sizes.append(size)
        if size != 512:
            raise ValueError(
                f"Provided number of samples is {size} (Supported values: "
                "256 for 8000 sample rate, 512 for 16000)"
            )
        # Speech iff the window is non-silent, so tests can control the result.
        return torch.tensor(1.0 if bool(audio.abs().max() > 0) else 0.0)


def _tone_frame(n_samples: int, amplitude: int = 1000) -> np.ndarray:
    return np.full(n_samples, amplitude, dtype=np.int16)


def _silence_frame(n_samples: int) -> np.ndarray:
    return np.zeros(n_samples, dtype=np.int16)


def test_rejects_unsupported_sample_rate() -> None:
    try:
        SileroVad(sample_rate=44_100, model=FakeModel())
    except ValueError:
        return
    raise AssertionError("expected ValueError for an unsupported sample rate")


def test_1280_sample_frame_never_reaches_model_at_wrong_size() -> None:
    # This is the exact frame size AudioCapture produces (80ms @ 16kHz) and
    # the exact crash seen on real hardware before the sub-chunking fix.
    model = FakeModel()
    vad = SileroVad(sample_rate=16_000, model=model)
    vad.speech_prob(_tone_frame(1280))
    assert all(size == 512 for size in model.call_sizes)


def test_remainder_carries_over_between_calls() -> None:
    model = FakeModel()
    vad = SileroVad(sample_rate=16_000, model=model)
    vad.speech_prob(_tone_frame(1280))  # 2 windows consumed, 256 left over
    assert len(model.call_sizes) == 2
    vad.speech_prob(_tone_frame(1280))  # 256 carried + 1280 new = 3 more windows
    assert len(model.call_sizes) == 5


def test_no_complete_window_yet_returns_zero_not_a_crash() -> None:
    model = FakeModel()
    vad = SileroVad(sample_rate=16_000, model=model)
    assert vad.speech_prob(_tone_frame(100)) == 0.0
    assert model.call_sizes == []


def test_is_speech_true_when_any_subwindow_has_speech() -> None:
    model = FakeModel()
    vad = SileroVad(sample_rate=16_000, model=model)
    # 1280 samples: silence, then a loud tone — at least one of the two full
    # 512-sample windows should register speech even though the frame as a
    # whole is mostly silent.
    frame = np.concatenate([_silence_frame(700), _tone_frame(580)])
    assert vad.is_speech(frame) is True


def test_8khz_uses_256_sample_windows() -> None:
    model = FakeModel()

    def model_8k(audio: torch.Tensor, sample_rate: int) -> torch.Tensor:
        assert audio.shape[-1] == 256
        model.call_sizes.append(audio.shape[-1])
        return torch.tensor(0.0)

    vad = SileroVad(sample_rate=8_000, model=model_8k)
    vad.speech_prob(_tone_frame(640))  # 80ms @ 8kHz
    assert model.call_sizes == [256, 256]
