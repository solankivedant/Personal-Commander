"""VoiceFSM transition tests with fake capture/wake/ASR/TTS — no hardware needed. Phase 1."""

from __future__ import annotations

import time

import numpy as np

from munshiji.bus import EventBus
from munshiji.wake.fsm import VoiceFSM, VoiceState


class FakeRingBuffer:
    def read_last(self, n: int) -> np.ndarray:
        return np.zeros(0, dtype=np.int16)


class FakeCapture:
    def __init__(self, sample_rate: int = 16_000) -> None:
        self.sample_rate = sample_rate
        self.ring_buffer = FakeRingBuffer()


class FakeWakeDetector:
    """Fires on the Nth call to push_frame (1-indexed), where N is in
    fire_on_calls. push_frame is only called from FSM's IDLE and SPEAKING
    branches, never while LISTENING."""

    def __init__(self, fire_on_calls: set[int]) -> None:
        self._fire_on_calls = fire_on_calls
        self._calls = 0

    def push_frame(self, frame: np.ndarray) -> bool:
        self._calls += 1
        return self._calls in self._fire_on_calls


class FakeVad:
    def __init__(self, speech_flags: list[bool]) -> None:
        self._flags = iter(speech_flags)

    def is_speech(self, frame: np.ndarray) -> bool:
        return next(self._flags, False)


class FakeAsr:
    def __init__(self, text: str = "hello there") -> None:
        self.text = text
        self.calls = 0

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        self.calls += 1
        return self.text


class FakeTts:
    def __init__(self, speak_delay_s: float = 0.0) -> None:
        self.spoken: list[str] = []
        self.stopped = False
        self._speak_delay_s = speak_delay_s

    def speak(self, text: str) -> None:
        self.spoken.append(text)
        if self._speak_delay_s:
            time.sleep(self._speak_delay_s)

    def stop(self) -> None:
        self.stopped = True


class FakeClock:
    """Deterministic stand-in for time.monotonic — avoids flaky real-time
    sleeps around Endpointer's millisecond-scale silence threshold."""

    def __init__(self) -> None:
        self._t = 0.0

    def __call__(self) -> float:
        return self._t

    def advance(self, seconds: float) -> None:
        self._t += seconds


def _frame() -> np.ndarray:
    return np.zeros(1280, dtype=np.int16)


def _make_fsm(
    wake_detector: FakeWakeDetector,
    vad: FakeVad,
    asr: FakeAsr | None = None,
    tts: FakeTts | None = None,
    now_fn: FakeClock | None = None,
) -> VoiceFSM:
    return VoiceFSM(
        capture=FakeCapture(),  # type: ignore[arg-type]
        wake_detector=wake_detector,  # type: ignore[arg-type]
        asr=asr or FakeAsr(),  # type: ignore[arg-type]
        tts=tts or FakeTts(),  # type: ignore[arg-type]
        bus=EventBus(),
        vad=vad,  # type: ignore[arg-type]
        hotkey="ctrl+alt+space",
        silence_ms=300,
        min_speech_ms=0,
        now_fn=now_fn or FakeClock(),
    )


def _wait_for_state(fsm: VoiceFSM, state: VoiceState, timeout_s: float = 2.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if fsm.state == state:
            return
        time.sleep(0.01)
    raise AssertionError(f"expected state {state}, still {fsm.state} after {timeout_s}s")


def test_wake_word_enters_listening() -> None:
    fsm = _make_fsm(FakeWakeDetector(fire_on_calls={1}), FakeVad([]))
    assert fsm.state == VoiceState.IDLE
    fsm.handle_frame(_frame())
    assert fsm.state == VoiceState.LISTENING


def test_non_wake_frame_stays_idle() -> None:
    fsm = _make_fsm(FakeWakeDetector(fire_on_calls=set()), FakeVad([]))
    fsm.handle_frame(_frame())
    assert fsm.state == VoiceState.IDLE


def test_full_round_trip_echoes_transcript_and_returns_to_idle() -> None:
    asr = FakeAsr(text="turn on the lights")
    tts = FakeTts()
    clock = FakeClock()
    fsm = _make_fsm(
        FakeWakeDetector(fire_on_calls={1}),
        FakeVad([True, True, False]),
        asr=asr,
        tts=tts,
        now_fn=clock,
    )

    fsm.handle_frame(_frame())  # wake fires -> LISTENING
    assert fsm.state == VoiceState.LISTENING

    clock.advance(0.08)
    fsm.handle_frame(_frame())  # speech
    clock.advance(0.08)
    fsm.handle_frame(_frame())  # speech
    clock.advance(0.35)
    fsm.handle_frame(_frame())  # silence >= silence_ms (300ms) -> endpoints

    assert asr.calls == 1
    assert tts.spoken == ["turn on the lights"]

    _wait_for_state(fsm, VoiceState.IDLE)  # SPEAKING hands back to IDLE on its own thread


def test_barge_in_during_speaking_stops_tts_and_reenters_listening() -> None:
    slow_tts = FakeTts(speak_delay_s=0.3)
    wake_detector = FakeWakeDetector(fire_on_calls={1, 2})
    clock = FakeClock()
    fsm = _make_fsm(wake_detector, FakeVad([True, False]), tts=slow_tts, now_fn=clock)

    fsm.handle_frame(_frame())  # wake fires -> LISTENING
    clock.advance(0.15)
    fsm.handle_frame(_frame())  # speech
    clock.advance(0.35)
    fsm.handle_frame(_frame())  # silence -> finishes into SPEAKING (own thread, slow)

    _wait_for_state(fsm, VoiceState.SPEAKING)

    fsm.handle_frame(_frame())  # wake fires again during SPEAKING -> barge-in

    assert slow_tts.stopped is True
    assert fsm.state == VoiceState.LISTENING
