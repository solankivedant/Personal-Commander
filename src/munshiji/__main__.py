"""Entry point: boots the event bus and config, then starts the wake/state-machine loop. Phase 1.

Two ways to run it, both driving the same engine:

    munshiji                # voice loop + Control Center
    munshiji --no-voice     # Control Center only — no mic, no models, no Qt

`--no-voice` exists because the Control Center is useful before the audio
stack is (and on a machine where the mic or the Whisper/Kokoro weights
aren't set up): commands typed into the local UI take exactly the same path
through the router, the tool registry and the confirmation gate as spoken
ones — see tools/dispatch.py, which both entry points share.
"""

from __future__ import annotations

import argparse
import signal
import sys
import threading
import time
import webbrowser
from pathlib import Path

import structlog

from munshiji.bus import EventBus
from munshiji.config import MunshijiConfig, load_config
from munshiji.router.bootstrap import build_router
from munshiji.router.router import Router
from munshiji.security.audit import AuditLog
from munshiji.security.confirm import ConfirmationGate
from munshiji.tools import files as file_tools
from munshiji.tools.dispatch import CommandDispatcher
from munshiji.ui.server import ControlCenterServer

logger = structlog.get_logger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _build_router(config: MunshijiConfig) -> Router:
    """Kept as the module-level name the tests and older callers use; the
    assembly itself lives in router/bootstrap.py so the Control Center can
    build the same router without importing this module's audio/Qt stack."""
    return build_router(config, REPO_ROOT)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="munshiji", description=__doc__)
    parser.add_argument(
        "--no-voice",
        action="store_true",
        help="Run the Control Center only: no microphone, wake word, ASR or TTS.",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Open the Control Center in the default browser once it is up.",
    )
    return parser.parse_args(argv)


def _start_control_center(
    config: MunshijiConfig,
    dispatcher: CommandDispatcher,
    bus: EventBus,
    voice_enabled: bool,
    open_browser: bool,
) -> ControlCenterServer | None:
    cc_config = config.ui.control_center
    if not cc_config.enabled:
        return None
    ui_dir = REPO_ROOT / cc_config.ui_dir
    if not (ui_dir / "index.html").is_file():
        logger.warning("control_center_ui_missing", ui_dir=str(ui_dir))
        return None
    server = ControlCenterServer(
        dispatcher=dispatcher,
        bus=bus,
        config=cc_config,
        ui_dir=ui_dir,
        voice_enabled=voice_enabled,
    )
    server.start()
    logger.info("control_center_ready", url=server.url)
    if open_browser or cc_config.open_browser:
        webbrowser.open(server.url)
    return server


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(20))  # INFO
    config = load_config()
    router = _build_router(config)

    bus = EventBus()
    bus.subscribe("fsm.transition", lambda _t, p: logger.info("state", **p))
    bus.subscribe("asr.transcript", lambda _t, p: logger.info("heard", text=p))
    bus.subscribe("router.route", lambda _t, p: logger.info("routed", **p))

    # The audit log attaches to the bus rather than being called by the FSM
    # (docs/ARCHITECTURE.md lists it as a cross-cutting subscriber, beside the
    # bus and config). Nothing below can change what the assistant does.
    audit = AuditLog(REPO_ROOT / config.logging.audit, rotate_mb=config.logging.rotate_mb)
    audit.attach(bus)

    confirm_gate = ConfirmationGate(
        timeout_s=config.security.confirm_timeout_s,
        max_attempts=config.security.confirm_max_attempts,
    )
    # One dispatcher and one gate for both entry points: a confirmation
    # proposed by voice and one proposed from the UI are the same pending
    # action, so answering it in either place resolves it exactly once.
    dispatcher = CommandDispatcher(router=router, bus=bus, confirm_gate=confirm_gate)

    control_center = _start_control_center(
        config, dispatcher, bus, voice_enabled=not args.no_voice, open_browser=args.open
    )

    logger.info(
        "munshiji_starting",
        voice=not args.no_voice,
        wake_phrase=config.wake.phrase,
        wake_model=config.wake.detector_model_id,
        hotkey=config.wake.hotkey,
        audit_log=str(audit.path),
        file_roots=len(file_tools.allowed_roots()),
        control_center=control_center.url if control_center else None,
    )

    if args.no_voice:
        _run_headless(control_center)
        return

    _run_voice(config, bus, router, confirm_gate, control_center)


def _run_headless(control_center: ControlCenterServer | None) -> None:
    """Control Center only. Nothing to drive but the HTTP thread, so this
    just parks until Ctrl+C."""
    if control_center is None:
        logger.error("nothing_to_run", reason="control centre disabled and voice off")
        return
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        logger.info("munshiji_stopping")
    finally:
        control_center.stop()


def _run_voice(
    config: MunshijiConfig,
    bus: EventBus,
    router: Router,
    confirm_gate: ConfirmationGate,
    control_center: ControlCenterServer | None,
) -> None:
    """The full voice loop. Imported lazily so `--no-voice` never touches the
    audio stack, Whisper, Kokoro or Qt — on a machine without a working mic
    or without the model weights downloaded, constructing them is exactly
    what fails."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from munshiji.asr.whisper import WhisperAsr
    from munshiji.audio.capture import AudioCapture
    from munshiji.audio.playback import AudioPlayback
    from munshiji.audio.vad import SileroVad
    from munshiji.tts.kokoro import KokoroTts
    from munshiji.ui.overlay import StatusOverlay
    from munshiji.wake.detector import WakeWordDetector
    from munshiji.wake.fsm import VoiceFSM

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
        confirm_gate=confirm_gate,
    )

    # The overlay needs a QApplication, and Qt requires that to run on the
    # main thread. The FSM keeps running on its own background thread, same
    # as before the overlay existed — main() just also drives Qt's loop now.
    app: QApplication | None = None
    if config.ui.overlay.enabled:
        app = QApplication.instance() or QApplication(sys.argv)  # type: ignore[assignment]
        overlay = StatusOverlay(bus, config.ui.overlay)
        overlay.show()

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
        if control_center is not None:
            control_center.stop()


if __name__ == "__main__":
    main()
