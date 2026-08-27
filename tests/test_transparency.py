"""Tests for the transparency log."""

from __future__ import annotations

from whisper_flow_local.transparency import LlmCall, TransparencyLog


def test_record_and_recent() -> None:
    log = TransparencyLog(size=3)
    log.record("cleanup", "sys", "raw text", "clean text")
    assert len(log) == 1
    call = log.recent()[0]
    assert call == LlmCall("cleanup", "sys", "raw text", "clean text")


def test_most_recent_first_and_bounded() -> None:
    log = TransparencyLog(size=2)
    log.record("cleanup", "s", "a", "A")
    log.record("cleanup", "s", "b", "B")
    log.record("command", "s", "c", "C")
    kinds = [c.user for c in log.recent()]
    assert kinds == ["c", "b"]  # most recent first, "a" evicted


def test_recent_limit() -> None:
    log = TransparencyLog(size=5)
    for i in range(5):
        log.record("cleanup", "s", str(i), str(i))
    assert [c.user for c in log.recent(2)] == ["4", "3"]


def test_size_zero_disables() -> None:
    log = TransparencyLog(size=0)
    log.record("cleanup", "s", "u", "o")
    assert len(log) == 0
    assert log.recent() == []


def test_clear() -> None:
    log = TransparencyLog(size=3)
    log.record("cleanup", "s", "u", "o")
    log.clear()
    assert len(log) == 0
