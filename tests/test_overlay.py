"""Tests for the overlay's pure state->label/color mapping. Deliberately does
not construct StatusOverlay itself (that needs a QApplication and, on most CI
runners, a display) — state_style is kept separate from the widget for
exactly this reason. Phase 1 (pulled forward from Phase 8, see
docs/ROADMAP.md)."""

from __future__ import annotations

from munshiji.ui.overlay import state_style

_ACTIVE_STATES = ["listening", "transcribing", "routing", "acting", "speaking"]


def test_active_states_have_a_label_and_color() -> None:
    for state in _ACTIVE_STATES:
        label, color = state_style(state)
        assert label != ""
        assert color.startswith("#")


def test_idle_has_no_label() -> None:
    label, color = state_style("idle")
    assert label == ""
    assert color.startswith("#")


def test_unknown_state_falls_back_to_idle_style() -> None:
    assert state_style("bogus") == state_style("idle")
