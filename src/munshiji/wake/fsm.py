"""IDLE -> LISTENING -> TRANSCRIBING -> ROUTING -> ACTING -> SPEAKING state
machine, plus push-to-talk hotkey entry. Phase 1 voice loop; Phase 2 wires
real routing/tool-execution into ROUTING/ACTING (see _route_and_act below)."""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable
from enum import Enum
from typing import TYPE_CHECKING

import keyboard
import numpy as np
import structlog

from munshiji.audio.vad import Endpointer, SileroVad
from munshiji.bus import EventBus
from munshiji.tools.registry import REGISTRY, ToolRegistry

if TYPE_CHECKING:
    from munshiji.asr.whisper import WhisperAsr
    from munshiji.audio.capture import AudioCapture
    from munshiji.router.router import Router
    from munshiji.tts.kokoro import KokoroTts
    from munshiji.wake.detector import WakeWordDetector

logger = structlog.get_logger(__name__)

PREFILL_S = 1.0  # how far to rewind into the ring buffer on wake/hotkey fire


class VoiceState(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    ROUTING = "routing"
    ACTING = "acting"
    SPEAKING = "speaking"


class VoiceFSM:
    """Orchestrates the L1 state machine: consumes frames from AudioCapture,
    runs wake-word detection in IDLE, closes LISTENING on VAD silence, calls
    ASR, then routes the transcript through the Phase 2 router/tool registry
    in ROUTING/ACTING (falling back to a Phase-1-style echo-back if no
    router is wired, e.g. in tests) before handing the result to TTS.
    Barge-in during SPEAKING (wake re-fire or hotkey) stops playback and
    re-enters LISTENING.
    """

    def __init__(
        self,
        capture: AudioCapture,
        wake_detector: WakeWordDetector,
        asr: WhisperAsr,
        tts: KokoroTts,
        bus: EventBus,
        vad: SileroVad,
        hotkey: str,
        silence_ms: int,
        min_speech_ms: int,
        now_fn: Callable[[], float] = time.monotonic,
        router: Router | None = None,
        registry: ToolRegistry = REGISTRY,
    ) -> None:
        self._capture = capture
        self._wake_detector = wake_detector
        self._asr = asr
        self._tts = tts
        self._bus = bus
        self._hotkey = hotkey
        self._vad = vad
        self._silence_ms = silence_ms
        self._min_speech_ms = min_speech_ms
        self._now_fn = now_fn
        self._router = router
        self._registry = registry

        self.state = VoiceState.IDLE
        self._endpointer: Endpointer | None = None
        self._utterance_frames: list[np.ndarray] = []
        self._hotkey_fired = threading.Event()
        self._stop_requested = threading.Event()
        self._interrupted = False
        self._speaking_thread: threading.Thread | None = None

    def _transition(self, new_state: VoiceState) -> None:
        old_state = self.state
        self.state = new_state
        logger.debug("fsm_transition", old=old_state.value, new=new_state.value)
        self._bus.publish("fsm.transition", {"old": old_state.value, "new": new_state.value})

    def _enter_listening(self) -> None:
        prefill_samples = int(self._capture.sample_rate * PREFILL_S)
        prefill = self._capture.ring_buffer.read_last(prefill_samples)
        self._utterance_frames = [prefill] if prefill.size else []
        self._endpointer = Endpointer(
            self._vad, self._silence_ms, self._min_speech_ms, now_fn=self._now_fn
        )
        self._transition(VoiceState.LISTENING)

    def _finish_listening(self) -> None:
        audio = (
            np.concatenate(self._utterance_frames)
            if self._utterance_frames
            else np.zeros(0, dtype=np.int16)
        )
        self._utterance_frames = []
        self._endpointer = None
        self._transition(VoiceState.TRANSCRIBING)

        text = self._asr.transcribe(audio, self._capture.sample_rate)
        self._bus.publish("asr.transcript", text)

        self._transition(VoiceState.ROUTING)
        response = self._route(text) if (self._router is not None and text) else text
        self._transition(VoiceState.ACTING)

        self._transition(VoiceState.SPEAKING)
        self._speak(response)

    def _route(self, text: str) -> str:
        """Run the Phase 2 cascade and, for anything that doesn't need
        confirmation, execute the resolved tool. Phase 3 owns the real
        spoken confirm gate (security/confirm.py doesn't exist yet), so a
        route that needs confirmation — or whose tool isn't registered yet,
        e.g. Phase 3's file tools — fails safe: it is described back to the
        user rather than either silently executed or silently dropped.
        Voice-driven teach mode (asking the user what an unmatched utterance
        should do) is deferred past Phase 2 — the FSM has no multi-turn
        dialogue state yet, only single-utterance routing — so a "teach"
        result just reports that nothing matched.
        """
        assert self._router is not None
        route = self._router.route(text)
        self._bus.publish(
            "router.route",
            {"tool": route.tool, "stage": route.stage, "args": route.args},
        )

        if route.tool is None:
            return "I don't know how to do that yet."
        if route.confirm_required is not False:
            # True, or None (tool not registered / risk unknown) — both must
            # block execution per security-and-privacy.md; only an explicit
            # False clears it.
            return f"That needs confirmation, which isn't wired up yet: {route.tool}."

        spec = self._registry.get(route.tool)
        if spec is None:
            return f"I don't have a way to do that yet ({route.tool})."
        try:
            return spec(**route.args)
        except Exception as exc:
            # Tools already catch their own execution errors and return a
            # readable string (engineering-standards.md); this guards only
            # the integration seam — e.g. router-extracted args that don't
            # match the tool's actual parameters.
            return f"Something went wrong trying to do that: {exc}"

    def _speak(self, text: str) -> None:
        self._interrupted = False

        def run() -> None:
            try:
                if text:
                    self._tts.speak(text)
            finally:
                if not self._interrupted:
                    self._transition(VoiceState.IDLE)

        self._speaking_thread = threading.Thread(target=run, daemon=True)
        self._speaking_thread.start()

    def _barge_in(self) -> None:
        self._interrupted = True
        self._tts.stop()
        self._bus.publish("fsm.barge_in", None)
        self._enter_listening()

    def handle_frame(self, frame: np.ndarray) -> None:
        hotkey_fired = self._hotkey_fired.is_set()
        if hotkey_fired:
            self._hotkey_fired.clear()

        if self.state == VoiceState.IDLE:
            if hotkey_fired or self._wake_detector.push_frame(frame):
                self._enter_listening()
        elif self.state == VoiceState.LISTENING:
            self._utterance_frames.append(frame)
            assert self._endpointer is not None
            if self._endpointer.push_frame(frame):
                self._finish_listening()
        elif self.state == VoiceState.SPEAKING:
            if hotkey_fired or self._wake_detector.push_frame(frame):
                self._barge_in()
        # TRANSCRIBING/ROUTING/ACTING happen synchronously inside
        # _finish_listening rather than spanning multiple frames.

    def _on_hotkey(self) -> None:
        self._hotkey_fired.set()

    def start(self) -> None:
        keyboard.add_hotkey(self._hotkey, self._on_hotkey)

    def stop(self) -> None:
        self._stop_requested.set()
        keyboard.remove_hotkey(self._hotkey)

    def run_forever(self) -> None:
        """Consume frames from AudioCapture until stop() is called. Intended
        to run on its own thread — see __main__.py."""
        while not self._stop_requested.is_set():
            try:
                frame = self._capture.frames.get(timeout=0.2)
            except queue.Empty:
                continue
            self.handle_frame(frame)
