"""Tests for hotkey-string parsing."""

from __future__ import annotations

import pytest

from whisper_flow_local.hotkeys.base import Hotkey, HotkeyParseError, parse_hotkey


def test_parse_simple_combo() -> None:
    hk = parse_hotkey("ctrl+shift+space")
    assert hk.key == "space"
    assert hk.modifiers == frozenset({"ctrl", "shift"})


def test_parse_normalizes_aliases() -> None:
    hk = parse_hotkey("control+option+command+a")
    assert hk.modifiers == frozenset({"ctrl", "alt", "cmd"})
    assert hk.key == "a"


def test_parse_bare_modifier() -> None:
    hk = parse_hotkey("cmd")
    assert hk.key == ""
    assert hk.modifiers == frozenset({"cmd"})


def test_parse_is_case_and_space_insensitive() -> None:
    hk = parse_hotkey("  Ctrl + Space ")
    assert hk == Hotkey(frozenset({"ctrl"}), "space")


def test_parse_empty_raises() -> None:
    with pytest.raises(HotkeyParseError):
        parse_hotkey("  ")


def test_parse_two_main_keys_raises() -> None:
    with pytest.raises(HotkeyParseError, match="more than one"):
        parse_hotkey("a+b")


def test_str_roundtrip() -> None:
    assert str(parse_hotkey("shift+ctrl+space")) == "ctrl+shift+space"
    assert str(Hotkey(frozenset({"cmd"}), "")) == "cmd+"
