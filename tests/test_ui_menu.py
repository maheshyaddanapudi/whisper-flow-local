"""Tests for the pure tray-menu structure and action dispatch."""

from __future__ import annotations

from whisper_flow_local.history import Dictation
from whisper_flow_local.pipeline_state import State
from whisper_flow_local.ui.menu import build_menu, perform


def test_menu_idle_no_history() -> None:
    entries = build_menu(State.IDLE, [])
    actions = [e.action for e in entries]
    assert actions[0] == "toggle"
    assert entries[0].label == "Start dictation"
    # cancel disabled when idle; paste-last disabled with no history
    cancel = next(e for e in entries if e.action == "cancel")
    assert cancel.enabled is False
    paste = next(e for e in entries if e.action == "paste-last")
    assert paste.enabled is False
    assert entries[-1].action == "quit"


def test_menu_recording_label_and_cancel() -> None:
    entries = build_menu(State.RECORDING, [])
    assert entries[0].label == "Stop dictation"
    assert next(e for e in entries if e.action == "cancel").enabled is True


def test_menu_with_history_lists_recent() -> None:
    recent = [Dictation(raw="one", cleaned="One."), Dictation(raw="two", cleaned="Two.")]
    entries = build_menu(State.IDLE, recent)
    hist = [e for e in entries if e.action.startswith("paste-history:")]
    assert [e.action for e in hist] == ["paste-history:0", "paste-history:1"]
    assert hist[0].label == "One."


def test_menu_long_preview_truncated() -> None:
    long = "word " * 30
    entries = build_menu(State.IDLE, [Dictation(raw=long, cleaned=long)])
    hist = next(e for e in entries if e.action == "paste-history:0")
    assert hist.label.endswith("…")
    assert len(hist.label) <= 40


class FakeController:
    def __init__(self) -> None:
        self.calls: list = []

    def toggle(self) -> None:
        self.calls.append(("toggle",))

    def cancel(self) -> None:
        self.calls.append(("cancel",))

    def paste_last(self, *, raw: bool = False) -> None:
        self.calls.append(("paste_last", raw))

    def paste_history(self, index: int) -> None:
        self.calls.append(("paste_history", index))


def test_perform_dispatches_actions() -> None:
    ctl = FakeController()
    quit_called = []
    perform(ctl, "toggle", lambda: quit_called.append(True))
    perform(ctl, "cancel", lambda: None)
    perform(ctl, "paste-last", lambda: None)
    perform(ctl, "paste-last-raw", lambda: None)
    perform(ctl, "paste-history:3", lambda: None)
    perform(ctl, "quit", lambda: quit_called.append(True))
    perform(ctl, "separator", lambda: None)  # no-op
    assert ctl.calls == [
        ("toggle",),
        ("cancel",),
        ("paste_last", False),
        ("paste_last", True),
        ("paste_history", 3),
    ]
    assert quit_called == [True]
