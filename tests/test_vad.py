"""Tests for the VAD endpointer and RMS."""

from __future__ import annotations

from whisper_flow_local.vad import Endpointer, rms


def test_rms_of_silence_is_zero() -> None:
    assert rms([0.0, 0.0, 0.0]) == 0.0


def test_rms_of_empty_is_zero() -> None:
    assert rms([]) == 0.0


def test_rms_of_constant() -> None:
    assert rms([0.5, 0.5, 0.5]) == 0.5


def test_endpointer_needs_speech_first() -> None:
    ep = Endpointer(silence_threshold=0.1, silence_duration_s=0.5)
    # leading silence never triggers an endpoint
    for _ in range(10):
        assert ep.observe(0.0, 0.2) is False
    assert not ep.has_speech


def test_endpointer_fires_after_silence_following_speech() -> None:
    ep = Endpointer(silence_threshold=0.1, silence_duration_s=0.5)
    assert ep.observe(0.5, 0.2) is False  # speech
    assert ep.has_speech
    assert ep.observe(0.0, 0.2) is False  # 0.2s silence
    assert ep.observe(0.0, 0.2) is False  # 0.4s silence
    assert ep.observe(0.0, 0.2) is True  # 0.6s >= 0.5s -> endpoint


def test_endpointer_resets_silence_on_new_speech() -> None:
    ep = Endpointer(silence_threshold=0.1, silence_duration_s=0.5)
    ep.observe(0.5, 0.2)  # speech
    ep.observe(0.0, 0.4)  # 0.4s silence
    ep.observe(0.5, 0.2)  # speech again -> resets accumulator
    assert ep.observe(0.0, 0.4) is False  # only 0.4s again, not yet
    assert ep.observe(0.0, 0.2) is True  # now 0.6s


def test_endpointer_threshold_boundary_counts_as_speech() -> None:
    ep = Endpointer(silence_threshold=0.1, silence_duration_s=0.3)
    assert ep.observe(0.1, 0.5) is False  # exactly threshold = speech
    assert ep.has_speech


def test_endpointer_reset() -> None:
    ep = Endpointer(silence_threshold=0.1, silence_duration_s=0.3)
    ep.observe(0.5, 0.2)
    ep.reset()
    assert not ep.has_speech
    assert ep.observe(0.0, 0.5) is False  # post-reset silence doesn't fire
