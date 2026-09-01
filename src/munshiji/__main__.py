"""Entry point: boots the event bus and config, then starts the wake/state-machine loop. Phase 1."""

from __future__ import annotations

import signal
import sys
import threading

import structlog
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from munshiji.asr.whisper import WhisperAsr
from munshiji.audio.capture import AudioCapture
from munshiji.audio.playback import AudioPlayback
from munshiji.audio.vad import SileroVad
from munshiji.bus import EventBus
from munshiji.config import load_config
from munshiji.tts.kokoro import KokoroTts
from munshiji.ui.overlay import StatusOverlay
from munshiji.wake.detector import WakeWordDetector
from munshiji.wake.fsm import VoiceFSM

logger = structlog.get_logger(__name__)


def main() -> None:
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(20))  # INFO
    config = load_config()

    bus = EventBus()
    bus.subscribe("fsm.transition", lambda _t, p: logger.info("state", **p))
    bus.subscribe("asr.transcript", lambda _t, p: logger.info("heard", text=p))

    capture = AudioCapture(
        sample_rate=config.audio.sample_rate,
        ring_buffer_s=config.audio.ring_buffer_s,
        device=config.audio.input_device,
    )
    wake_detector = WakeWordDetector(
        model_id=config.wake.detector_model_id,
        threshold=config.wake.threshold,
        debounce_ms=config.wake.debounce_ms,
    )
    asr = WhisperAsr(
        model_size=config.asr.model,
        compute_type=config.asr.compute_type,
        backend=config.asr.backend,
        initial_prompt=config.asr.initial_prompt,
    )
    tts = KokoroTts(voice=config.tts.voice, playback=AudioPlayback())
    vad = SileroVad(sample_rate=config.audio.sample_rate)

    fsm = VoiceFSM(
        capture=capture,
        wake_detector=wake_detector,
        asr=asr,
        tts=tts,
        bus=bus,
        vad=vad,
        hotkey=config.wake.hotkey,
        silence_ms=config.vad.silence_ms,
        min_speech_ms=config.vad.min_speech_ms,
    )

    # The overlay needs a QApplication, and Qt requires that to run on the
    # main thread. The FSM keeps running on its own background thread, same
    # as before the overlay existed — main() just also drives Qt's loop now.
    app: QApplication | None = None
    if config.ui.overlay.enabled:
        app = QApplication.instance() or QApplication(sys.argv)  # type: ignore[assignment]
        overlay = StatusOverlay(bus, config.ui.overlay)
        overlay.show()

    logger.info(
        "munshiji_starting",
        wake_phrase=config.wake.phrase,
        wake_model=config.wake.detector_model_id,
        hotkey=config.wake.hotkey,
    )
    capture.start()
    fsm.start()
    fsm_thread = threading.Thread(target=fsm.run_forever, daemon=True)
    fsm_thread.start()

    try:
        if app is not None:
            # Qt's loop doesn't poll for SIGINT on its own; restore the
            # default handler and give the interpreter a periodic chance to
            # notice it, so Ctrl+C in the console still works.
            signal.signal(signal.SIGINT, signal.SIG_DFL)
            keepalive = QTimer()
            keepalive.timeout.connect(lambda: None)
            keepalive.start(200)
            app.exec()
        else:
            fsm_thread.join()
    except KeyboardInterrupt:
        logger.info("munshiji_stopping")
    finally:
        fsm.stop()
        capture.stop()


if __name__ == "__main__":
    main()
