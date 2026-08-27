"""Tests for the state-change fan-out."""

from __future__ import annotations

from whisper_flow_local.notifier import StateNotifier
from whisper_flow_local.pipeline_state import State


def test_notifier_fans_out_to_all_listeners() -> None:
    a: list = []
    b: list = []
    notifier = StateNotifier()
    notifier.register(a.append)
    notifier.register(b.append)
    notifier(State.RECORDING)
    notifier(State.IDLE)
    assert a == [State.RECORDING, State.IDLE]
    assert b == [State.RECORDING, State.IDLE]


def test_notifier_no_listeners_is_noop() -> None:
    StateNotifier()(State.IDLE)  # must not raise
