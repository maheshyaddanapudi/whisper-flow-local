"""Tests for the pipeline state machine."""

from __future__ import annotations

import pytest

from whisper_flow_local.pipeline_state import InvalidTransition, State, StateMachine


def test_initial_state_is_idle() -> None:
    sm = StateMachine()
    assert sm.state == State.IDLE
    assert not sm.is_active


def test_full_forward_flow() -> None:
    sm = StateMachine()
    for target in (
        State.RECORDING,
        State.TRANSCRIBING,
        State.CLEANING,
        State.INJECTING,
        State.IDLE,
    ):
        sm.to(target)
    assert sm.state == State.IDLE


def test_transcribing_can_skip_cleaning() -> None:
    sm = StateMachine()
    sm.to(State.RECORDING)
    sm.to(State.TRANSCRIBING)
    sm.to(State.INJECTING)  # skip cleaning
    assert sm.state == State.INJECTING


def test_is_active_true_when_not_idle() -> None:
    sm = StateMachine()
    sm.to(State.RECORDING)
    assert sm.is_active


@pytest.mark.parametrize(
    ("path", "bad"),
    [
        ([], State.TRANSCRIBING),  # idle -> transcribing illegal
        ([State.RECORDING], State.CLEANING),  # recording -> cleaning illegal
        ([State.RECORDING, State.TRANSCRIBING, State.INJECTING], State.CLEANING),
    ],
)
def test_illegal_transitions_raise(path, bad) -> None:
    sm = StateMachine()
    for p in path:
        sm.to(p)
    assert not sm.can(bad)
    with pytest.raises(InvalidTransition):
        sm.to(bad)


def test_cancel_from_each_active_state() -> None:
    for stop_at in (State.RECORDING, State.TRANSCRIBING, State.CLEANING, State.INJECTING):
        sm = StateMachine()
        for target in (State.RECORDING, State.TRANSCRIBING, State.CLEANING, State.INJECTING):
            sm.to(target)
            if target == stop_at:
                break
        assert sm.cancel() is True
        assert sm.state == State.IDLE


def test_cancel_when_idle_is_noop() -> None:
    sm = StateMachine()
    assert sm.cancel() is False


def test_reset_forces_idle() -> None:
    sm = StateMachine()
    sm.to(State.RECORDING)
    sm.to(State.TRANSCRIBING)
    sm.reset()
    assert sm.state == State.IDLE
