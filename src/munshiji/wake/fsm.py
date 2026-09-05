"""IDLE -> LISTENING -> TRANSCRIBING -> ROUTING -> ACTING -> SPEAKING state
machine, plus push-to-talk hotkey entry. Phase 1 voice loop; Phase 2 wired
real routing/tool-execution into ROUTING/ACTING; Phase 3 adds CONFIRMING —
the first multi-turn state in the loop.

CONFIRMING is what makes `risk="confirm"` tools reachable at all. Before it,
`_route` could only describe a confirm-tier action back to the user and drop
it, because a spoken yes/no needs the loop to stay in the conversation across
two utterances rather than falling back to IDLE and waiting for the wake word
again. The shape: propose -> speak the prompt -> re-enter LISTENING without a
wake word -> the next transcript resolves the gate instead of being routed.

The gate itself (security/confirm.py) owns every safety decision; this module
only carries transcripts to it and acts on the outcome. It cannot approve
anything on its own, which is the point — see that module's docstring."""

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
from munshiji.security.confirm import ConfirmationGate
from munshiji.tools.dispatch import CommandDispatcher
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
    CONFIRMING = "confirming"
    SPEAKING = "speaking"


class VoiceFSM:
    """Orchestrates the L1 state machine: consumes frames from AudioCapture,
    runs wake-word detection in IDLE, closes LISTENING on VAD silence, calls
    ASR, then routes the transcript through the Phase 2 router/tool registry
    in ROUTING/ACTING (falling back to a Phase-1-style echo-back if no
    router is wired, e.g. in tests) before handing the result to TTS.
    Barge-in during SPEAKING (wake re-fire or hotkey) stops playback and
    re-enters LISTENING.

    With a `confirm_gate` wired, a confirm-tier route enters CONFIRMING and
    the *next* transcript is read as an answer rather than a command. Without
    one the FSM still refuses to execute confirm-tier tools — the gate adds
    the ability to say yes, never the ability to skip being asked.
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
        confirm_gate: ConfirmationGate | None = None,
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
        self._confirm_gate = confirm_gate

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

        awaiting_confirmation = (
            self._confirm_gate is not None and self._confirm_gate.pending is not None
        )
        if awaiting_confirmation:
            # A pending confirmation takes precedence over routing: this
            # utterance is an answer, not a new command. Routing it instead
            # would let "yes" be matched as some unrelated intent while the
            # proposed action sat unanswered.
            self._transition(VoiceState.CONFIRMING)
            response = self._resolve_confirmation(text)
        else:
            self._transition(VoiceState.ROUTING)
            response = self._route(text) if (self._router is not None and text) else text
        self._transition(VoiceState.ACTING)

        self._transition(VoiceState.SPEAKING)
        self._speak(response)

    def _dispatcher(self) -> CommandDispatcher:
        """Build a dispatcher over this FSM's current collaborators.

        Constructed per call rather than held: the dispatcher is stateless
        (the pending confirmation lives in the gate), and building it here
        keeps `self._router` / `self._registry` / `self._confirm_gate`
        swappable after construction, which is how the tests wire fakes in.
        """
        return CommandDispatcher(
            router=self._router,
            bus=self._bus,
            registry=self._registry,
            confirm_gate=self._confirm_gate,
        )

    def _route(self, text: str) -> str:
        """Route one transcript and return what to speak.

        The decision itself lives in `tools/dispatch.py`, shared with the
        Control Center so a typed command and a spoken one take exactly the
        same safety path.

        Voice-driven teach mode (asking the user what an unmatched utterance
        should do) is still deferred: CONFIRMING is a yes/no turn, not the
        open-ended dialogue teach mode needs.
        """
        assert self._router is not None
        return self._dispatcher().route(text).speech

    def _resolve_confirmation(self, text: str) -> str:
        """Interpret this utterance as the answer to the pending action."""
        assert self._confirm_gate is not None
        return self._dispatcher().resolve_confirmation(text).speech

    def _speak(self, text: str) -> None:
        self._interrupted = False

        def run() -> None:
            try:
                if text:
                    self._tts.speak(text)
            finally:
                # No `return` in here: it would swallow an exception raised
                # by tts.speak() and leave the failure invisible.
                if not self._interrupted:
                    awaiting = (
                        self._confirm_gate is not None
                        and self._confirm_gate.pending is not None
                    )
                    if awaiting:
                        # Multi-turn: we just asked a question, so listen for
                        # the answer instead of dropping to IDLE and making
                        # the user say the wake word again mid-sentence.
                        self._enter_listening()
                    else:
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
