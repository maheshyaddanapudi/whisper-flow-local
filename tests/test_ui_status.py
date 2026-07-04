"""Tests for the pure state->badge mapping."""

from __future__ import annotations

from whisper_flow_local.pipeline_state import State
from whisper_flow_local.ui.status import badge_for


def test_every_state_has_a_badge() -> None:
    for state in State:
        badge = badge_for(state)
        assert badge.label
        assert badge.color.startswith("#")


def test_idle_is_inactive_others_active() -> None:
    assert badge_for(State.IDLE).active is False
    for state in (State.RECORDING, State.TRANSCRIBING, State.CLEANING, State.INJECTING):
        assert badge_for(state).active is True


def test_distinct_labels_and_colors_for_pipeline_states() -> None:
    states = [State.RECORDING, State.TRANSCRIBING, State.CLEANING]
    labels = {badge_for(s).label for s in states}
    colors = {badge_for(s).color for s in states}
    assert len(labels) == 3  # three visually-distinct states
    assert len(colors) == 3
