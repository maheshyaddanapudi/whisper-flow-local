"""Tests for frontmost-app detection dispatch (native paths are seams)."""

from __future__ import annotations

from whisper_flow_local import frontmost


def test_detect_unknown_platform_returns_empty(monkeypatch) -> None:
    monkeypatch.setattr(frontmost.platform, "system", lambda: "Plan9")
    assert frontmost.detect() == ("", "")


def test_detect_swallows_errors(monkeypatch) -> None:
    monkeypatch.setattr(frontmost.platform, "system", lambda: "Darwin")

    def boom() -> tuple[str, str]:
        raise RuntimeError("no AppKit")

    monkeypatch.setattr(frontmost, "_detect_macos", boom)
    assert frontmost.detect() == ("", "")


def test_detect_dispatches_to_platform(monkeypatch) -> None:
    monkeypatch.setattr(frontmost.platform, "system", lambda: "Linux")
    monkeypatch.setattr(frontmost, "_detect_linux", lambda: ("", "My Window"))
    assert frontmost.detect() == ("", "My Window")


def test_detect_dispatches_macos_and_windows(monkeypatch) -> None:
    monkeypatch.setattr(frontmost.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(frontmost, "_detect_macos", lambda: ("Slack", ""))
    assert frontmost.detect() == ("Slack", "")

    monkeypatch.setattr(frontmost.platform, "system", lambda: "Windows")
    monkeypatch.setattr(frontmost, "_detect_windows", lambda: ("", "Notepad"))
    assert frontmost.detect() == ("", "Notepad")
