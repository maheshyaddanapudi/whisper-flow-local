"""Tests for macOS permission guidance."""

from __future__ import annotations

from whisper_flow_local.permissions import describe, render


def test_describe_macos_lists_three() -> None:
    rows = describe("Darwin")
    names = [r[0] for r in rows]
    assert names == ["Microphone", "Input Monitoring", "Accessibility"]


def test_describe_non_macos_empty() -> None:
    assert describe("Linux") == []
    assert describe("Windows") == []


def test_render_macos() -> None:
    text = render("Darwin")
    assert "System Settings" in text
    assert "Accessibility" in text
    assert "copy-only" in text


def test_render_non_macos_empty() -> None:
    assert render("Linux") == ""
