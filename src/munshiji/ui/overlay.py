"""Floating status overlay — a Whisper-Flow/Gemini-style pill docked to the
bottom of the screen, showing listen/think/speak state and the last
transcript. This is the minimal Phase 1 slice pulled forward from Phase 8
(see docs/ROADMAP.md): pure status display, no controls. The real control
dashboard and tray icon (routing to real tools, confirm/undo, settings) stay
Phase 8 until the router (Phase 2) and tool registry (Phase 3) exist to back
them.

Subscribes to the event bus only, per bus.py's "pure subscriber" contract —
never imports or calls into audio/wake/asr/tts directly.
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QObject, QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QPainter, QPaintEvent
from PySide6.QtWidgets import QGraphicsOpacityEffect, QLabel, QVBoxLayout, QWidget

from munshiji.bus import EventBus
from munshiji.config import OverlayConfig

_LABEL_FONT_PX = 12
_LAYOUT_MARGINS = (10, 6, 10, 6)  # left, top, right, bottom

# state value -> (label text, pill color). idle is intentionally label-less
# and dim so the bar doesn't sit on screen as visual clutter between commands.
_STATE_STYLE: dict[str, tuple[str, str]] = {
    "idle": ("", "#3a3a3a"),
    "listening": ("Listening…", "#2f6fed"),
    "transcribing": ("Thinking…", "#8a5cf6"),
    "routing": ("Thinking…", "#8a5cf6"),
    "acting": ("Working…", "#8a5cf6"),
    "speaking": ("Speaking…", "#1fae6b"),
}


def state_style(state: str) -> tuple[str, str]:
    """Pure label/color lookup, kept separate from the widget so it's
    testable without a QApplication or display."""
    return _STATE_STYLE.get(state, _STATE_STYLE["idle"])


class _OverlayBridge(QObject):
    """Marshals event-bus callbacks (fired on the FSM's background thread)
    onto the Qt GUI thread. Qt auto-queues a signal emission when the emitting
    thread differs from the receiving QObject's thread, as long as this
    object was constructed on the GUI thread — see StatusOverlay.__init__."""

    state_changed = Signal(str)
    transcript_received = Signal(str)


class StatusOverlay(QWidget):
    """Frameless, always-on-top, non-focusable pill anchored to the bottom of
    the primary screen."""

    def __init__(
        self, bus: EventBus, config: OverlayConfig, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._current_state = "idle"
        self._color = "#3a3a3a"
        self._pulse: QPropertyAnimation | None = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.resize(config.width_px, config.height_px)

        self._label = QLabel("", self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet(
            f"color: white; font-size: {_LABEL_FONT_PX}px; font-weight: 600; "
            "background: transparent;"
        )
        # Set the QFont explicitly (not just the stylesheet) so
        # QFontMetrics(...) below reflects the actual rendered size when
        # eliding a transcript that's wider than this now-slim pill.
        font = QFont(self._label.font())
        font.setPixelSize(_LABEL_FONT_PX)
        font.setBold(True)
        self._label.setFont(font)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*_LAYOUT_MARGINS)
        layout.addWidget(self._label)

        self._opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity_effect)
        self._opacity_effect.setOpacity(config.opacity)

        self._transcript_timer = QTimer(self)
        self._transcript_timer.setSingleShot(True)
        self._transcript_timer.timeout.connect(self._revert_to_state_label)

        self._bridge = _OverlayBridge()
        self._bridge.state_changed.connect(self._on_state_changed)
        self._bridge.transcript_received.connect(self._on_transcript)
        bus.subscribe("fsm.transition", lambda _t, p: self._bridge.state_changed.emit(p["new"]))
        bus.subscribe("asr.transcript", lambda _t, p: self._bridge.transcript_received.emit(p))

        self._reposition()
        self._apply_state("idle")

    def _reposition(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = geo.x() + (geo.width() - self.width()) // 2
        if self._config.position == "bottom_left":
            x = geo.x() + self._config.margin_px
        elif self._config.position == "bottom_right":
            x = geo.x() + geo.width() - self.width() - self._config.margin_px
        y = geo.y() + geo.height() - self.height() - self._config.margin_px
        self.move(x, y)

    def _apply_state(self, state: str) -> None:
        label, color = state_style(state)
        self._label.setText(label)
        self._color = color
        self._set_pulsing(state == "listening")
        self.update()

    def _set_pulsing(self, enabled: bool) -> None:
        if self._pulse is not None:
            self._pulse.stop()
            self._pulse = None
        if not enabled:
            self._opacity_effect.setOpacity(self._config.opacity)
            return
        anim = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        anim.setDuration(1200)
        anim.setStartValue(self._config.opacity)
        anim.setKeyValueAt(0.5, max(0.35, self._config.opacity - 0.4))
        anim.setEndValue(self._config.opacity)
        anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        anim.setLoopCount(-1)
        anim.start()
        self._pulse = anim

    def _on_state_changed(self, new_state: str) -> None:
        self._current_state = new_state
        self._transcript_timer.stop()
        self._apply_state(new_state)

    def _on_transcript(self, text: str) -> None:
        if not text:
            return
        available_width = self.width() - _LAYOUT_MARGINS[0] - _LAYOUT_MARGINS[2]
        elided = QFontMetrics(self._label.font()).elidedText(
            text, Qt.TextElideMode.ElideRight, available_width
        )
        self._label.setText(elided)
        self._label.setToolTip(text if elided != text else "")
        self._set_pulsing(False)
        self._transcript_timer.start(int(self._config.transcript_display_s * 1000))

    def _revert_to_state_label(self) -> None:
        self._apply_state(self._current_state)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self._color))
        radius = self.height() / 2
        painter.drawRoundedRect(self.rect(), radius, radius)
        painter.end()
