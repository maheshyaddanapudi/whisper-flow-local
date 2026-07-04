"""Tests for the AudioBuffer and Transcript value types."""

from __future__ import annotations

from whisper_flow_local.audio import AudioBuffer
from whisper_flow_local.stt.base import Transcript


def test_audio_buffer_duration_and_counts() -> None:
    buf = AudioBuffer(data=[0.0] * 16000, sample_rate=16000)
    assert buf.num_samples == 16000
    assert buf.duration_s == 1.0
    assert not buf.is_empty


def test_audio_buffer_empty() -> None:
    buf = AudioBuffer(data=[], sample_rate=16000)
    assert buf.is_empty
    assert buf.duration_s == 0.0


def test_transcript_is_empty() -> None:
    assert Transcript(text="   ").is_empty
    assert not Transcript(text="hi").is_empty
    assert Transcript(text="hi", language="en").language == "en"
