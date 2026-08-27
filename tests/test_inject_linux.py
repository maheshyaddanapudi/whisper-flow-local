"""Tests for Linux injection: session detection, tool selection, command injector."""

from __future__ import annotations

import pytest

from whisper_flow_local.inject.base import InjectRequest
from whisper_flow_local.inject.linux import (
    CommandInjector,
    _argv_for,
    _enter_argv,
    detect_session_type,
    preferred_tools,
    select_tool,
)


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({"XDG_SESSION_TYPE": "wayland"}, "wayland"),
        ({"XDG_SESSION_TYPE": "x11"}, "x11"),
        ({"WAYLAND_DISPLAY": "wayland-0"}, "wayland"),
        ({"DISPLAY": ":0"}, "x11"),
        ({}, "unknown"),
    ],
)
def test_detect_session_type(env, expected) -> None:
    assert detect_session_type(env) == expected


def test_preferred_tools() -> None:
    assert preferred_tools("wayland") == ["wtype", "ydotool"]
    assert preferred_tools("x11") == ["xdotool"]
    assert preferred_tools("unknown") == ["xdotool", "wtype", "ydotool"]


def test_select_tool_first_available() -> None:
    def which(tool: str) -> str | None:
        return "/usr/bin/" + tool if tool == "ydotool" else None

    assert select_tool("wayland", which) == "ydotool"  # wtype missing, ydotool present


def test_select_tool_none_available() -> None:
    assert select_tool("x11", lambda t: None) is None


def test_argv_for_each_tool() -> None:
    assert _argv_for("xdotool", "hi")[:2] == ["xdotool", "type"]
    assert _argv_for("wtype", "hi") == ["wtype", "hi"]
    assert _argv_for("ydotool", "hi")[:2] == ["ydotool", "type"]


def test_argv_for_unknown_tool_is_none() -> None:
    assert _argv_for("bogus", "x") is None


def test_enter_argv_each_tool() -> None:
    assert _enter_argv("xdotool") == ["xdotool", "key", "Return"]
    assert _enter_argv("wtype")[:2] == ["wtype", "-k"]
    assert _enter_argv("ydotool")[0] == "ydotool"


def test_command_injector_success() -> None:
    calls: list = []
    inj = CommandInjector("wtype", run=lambda argv, text: calls.append(argv) or 0)
    assert inj.available()
    assert inj.inject(InjectRequest(text="hello")) is True
    assert calls == [["wtype", "hello"]]


def test_command_injector_with_enter() -> None:
    calls: list = []
    inj = CommandInjector("xdotool", run=lambda argv, text: calls.append(argv) or 0)
    inj.inject(InjectRequest(text="hello", auto_submit=True))
    assert calls[-1] == ["xdotool", "key", "Return"]


def test_command_injector_empty_text() -> None:
    inj = CommandInjector("wtype", run=lambda argv, text: 0)
    assert inj.inject(InjectRequest(text="")) is False


def test_command_injector_failure() -> None:
    inj = CommandInjector("wtype", run=lambda argv, text: 1)  # non-zero exit
    assert inj.inject(InjectRequest(text="hi")) is False
