"""Entry point: boots the event bus and config, then starts the wake/state-machine loop. Phase 1."""

from __future__ import annotations

import signal
import sys
import threading
from pathlib import Path

import structlog
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from munshiji.asr.whisper import WhisperAsr
from munshiji.audio.capture import AudioCapture
from munshiji.audio.playback import AudioPlayback
from munshiji.audio.vad import SileroVad
from munshiji.bus import EventBus
from munshiji.config import MunshijiConfig, load_config
from munshiji.router import slots as router_slots
from munshiji.router.embeddings import EmbeddingIndex, SentenceTransformerEncoder
from munshiji.router.grammar import GrammarRouter
from munshiji.router.router import Router
from munshiji.security.undo import UNDO_STACK
from munshiji.tools import apps as app_tools
from munshiji.tools import system as system_tools
from munshiji.tools.apps import build_app_index
from munshiji.tts.kokoro import KokoroTts
from munshiji.ui.overlay import StatusOverlay
from munshiji.wake.detector import WakeWordDetector
from munshiji.wake.fsm import VoiceFSM

logger = structlog.get_logger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _build_router(config: MunshijiConfig) -> Router:
    """Assemble the Phase 2 cascade: grammar over config/intents, embeddings
    over config/examples, and confirm resolution against the tool registry
    (system_tools/app_tools are imported above purely for their @tool
    registration side effects — REGISTRY needs them loaded before any route
    is resolved)."""
    system_tools.configure(
        volume_step_pct=config.tools.volume_step_pct,
        brightness_step_pct=config.tools.brightness_step_pct,
        subprocess_timeout_s=config.tools.subprocess_timeout_s,
    )
    app_tools.configure(fuzzy_cutoff=config.tools.fuzzy_app_cutoff)
    router_slots.configure(fuzzy_app_cutoff=config.router.slots.fuzzy_app_cutoff)
    UNDO_STACK.configure(max_depth=config.security.undo_depth)

    grammar = GrammarRouter.from_config_dirs(config.router.grammar.dirs, root=REPO_ROOT)

    # config/default.yaml names the model by its short HF handle
    # ("multilingual-e5-small"); SentenceTransformerEncoder needs the full
    # "org/name" id it actually publishes under.
    model_name = config.router.embeddings.model
    if "/" not in model_name:
        model_name = f"intfloat/{model_name}"
    embeddings = EmbeddingIndex(SentenceTransformerEncoder(model_name))
    examples_dir = REPO_ROOT / config.router.embeddings.examples
    embeddings.build_from_dirs([examples_dir])

    known_apps = tuple(build_app_index().keys())
    return Router(
        grammar,
        embeddings,
        config.router,
        known_apps=known_apps or router_slots.DEFAULT_KNOWN_APPS,
    )


def main() -> None:
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(20))  # INFO
    config = load_config()
    router = _build_router(config)

    bus = EventBus()
    bus.subscribe("fsm.transition", lambda _t, p: logger.info("state", **p))
    bus.subscribe("asr.transcript", lambda _t, p: logger.info("heard", text=p))
    bus.subscribe("router.route", lambda _t, p: logger.info("routed", **p))

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
        router=router,
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
