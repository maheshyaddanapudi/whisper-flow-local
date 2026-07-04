"""Tests for the dictation history buffer."""

from __future__ import annotations

from whisper_flow_local.history import Dictation, History


def test_dictation_text_prefers_cleaned() -> None:
    assert Dictation(raw="r", cleaned="c").text == "c"
    assert Dictation(raw="r", cleaned="").text == "r"


def test_add_and_last() -> None:
    h = History(size=3)
    h.add("one", "One.")
    h.add("two", "Two.")
    assert h.last is not None
    assert h.last.text == "Two."
    assert len(h) == 2


def test_bounded_size_evicts_oldest() -> None:
    h = History(size=2)
    h.add("a")
    h.add("b")
    h.add("c")
    texts = [d.raw for d in h.recent()]
    assert texts == ["c", "b"]  # most-recent-first, "a" evicted
    assert len(h) == 2


def test_recent_limit() -> None:
    h = History(size=5)
    for i in range(5):
        h.add(str(i))
    assert [d.raw for d in h.recent(2)] == ["4", "3"]


def test_size_zero_disables_history() -> None:
    h = History(size=0)
    item = h.add("x", "X")
    assert item.raw == "x"  # returned for immediate use
    assert h.last is None
    assert len(h) == 0


def test_clear() -> None:
    h = History(size=3)
    h.add("a")
    h.clear()
    assert len(h) == 0
    assert h.last is None
