"""Tests for the recording-intent resolver (hybrid tap/hold logic)."""

from __future__ import annotations

from whisper_flow_local.recording import Intent, Mode, RecordingResolver


def test_toggle_mode() -> None:
    r = RecordingResolver(Mode.TOGGLE)
    assert r.press(0.0) == Intent.START
    assert r.recording
    assert r.release(0.1) == Intent.NONE  # release ignored
    assert r.press(1.0) == Intent.STOP
    assert not r.recording


def test_continuous_mode_behaves_like_toggle() -> None:
    r = RecordingResolver(Mode.CONTINUOUS)
    assert r.press(0.0) == Intent.START
    assert r.release(0.1) == Intent.NONE
    assert r.press(1.0) == Intent.STOP


def test_push_to_talk_mode() -> None:
    r = RecordingResolver(Mode.PUSH_TO_TALK)
    assert r.press(0.0) == Intent.START
    assert r.press(0.05) == Intent.NONE  # extra press while held
    assert r.release(0.3) == Intent.STOP
    assert r.release(0.4) == Intent.NONE  # release while idle


def test_hybrid_hold_is_push_to_talk() -> None:
    r = RecordingResolver(Mode.HYBRID, hold_threshold_s=0.5)
    assert r.press(0.0) == Intent.START
    # held longer than threshold -> release stops (PTT)
    assert r.release(0.8) == Intent.STOP
    assert not r.recording


def test_hybrid_tap_latches_then_taps_off() -> None:
    r = RecordingResolver(Mode.HYBRID, hold_threshold_s=0.5)
    # quick tap: press+release under threshold -> latch on, keep recording
    assert r.press(0.0) == Intent.START
    assert r.release(0.1) == Intent.NONE
    assert r.recording  # latched on
    # second tap stops
    assert r.press(1.0) == Intent.NONE
    assert r.release(1.1) == Intent.STOP
    assert not r.recording


def test_hybrid_second_tap_long_hold_still_stops() -> None:
    r = RecordingResolver(Mode.HYBRID, hold_threshold_s=0.5)
    r.press(0.0)
    r.release(0.1)  # latch
    r.press(1.0)  # begin stop-tap
    # even if the second press is held long, releasing stops the latched session
    assert r.release(2.0) == Intent.STOP


def test_hybrid_exact_threshold_is_hold() -> None:
    r = RecordingResolver(Mode.HYBRID, hold_threshold_s=0.5)
    r.press(0.0)
    assert r.release(0.5) == Intent.STOP  # >= threshold counts as hold
