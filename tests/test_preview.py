"""Tests for the streaming partial-preview coordinator."""

from __future__ import annotations

from whisper_flow_local.audio import AudioBuffer
from whisper_flow_local.stt.preview import StreamingPreview


def _buf(n: int = 16000) -> AudioBuffer:
    return AudioBuffer(data=[0.0] * n, sample_rate=16000)


def test_emits_preview_when_text_changes() -> None:
    scripted = iter(["hello", "hello world", "hello world today"])
    emitted: list[str] = []
    sp = StreamingPreview(lambda _a: next(scripted), emitted.append)
    sp.update(_buf())
    sp.update(_buf())
    sp.update(_buf())
    assert emitted == ["hello", "hello world", "hello world today"]


def test_dedupes_unchanged_partial() -> None:
    emitted: list[str] = []
    sp = StreamingPreview(lambda _a: "same", emitted.append)
    sp.update(_buf())
    sp.update(_buf())
    sp.update(_buf())
    assert emitted == ["same"]  # only once despite three updates


def test_empty_partial_not_emitted() -> None:
    emitted: list[str] = []
    sp = StreamingPreview(lambda _a: "   ", emitted.append)
    assert sp.update(_buf()) == ""
    assert emitted == []


def test_transcribe_error_is_swallowed() -> None:
    emitted: list[str] = []

    def boom(_a: AudioBuffer) -> str:
        raise RuntimeError("tiny model failed")

    sp = StreamingPreview(boom, emitted.append)
    assert sp.update(_buf()) == ""  # falls back to last (empty), no crash
    assert emitted == []


def test_reset_clears_and_hides() -> None:
    emitted: list[str] = []
    sp = StreamingPreview(lambda _a: "partial", emitted.append)
    sp.update(_buf())
    sp.reset()
    assert emitted == ["partial", ""]  # reset hides the overlay
    # after reset the same text emits again (state cleared)
    sp.update(_buf())
    assert emitted == ["partial", "", "partial"]
