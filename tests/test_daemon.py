"""Tests for the daemon: IPC dispatch mapping + socket integration."""

from __future__ import annotations

import pytest

from fakes import FakeAudioSource, FakeInjector, FakeSTT
from whisper_flow_local.controller import Controller, ControllerConfig, _Deps
from whisper_flow_local.daemon import Daemon, make_dispatch
from whisper_flow_local.history import History
from whisper_flow_local.inject.base import InjectionChain
from whisper_flow_local.ipc import IPCError, send


def _controller() -> Controller:
    deps = _Deps(
        audio=FakeAudioSource(duration_s=1.0),
        stt=FakeSTT("a long enough sentence to be injected without cleanup here"),
        injection=InjectionChain([FakeInjector("fake")]),
        history=History(size=5),
    )
    return Controller(ControllerConfig(min_duration_s=0.15), deps)


def test_dispatch_ping() -> None:
    dispatch = make_dispatch(_controller())
    assert dispatch("ping", {}) == {"pong": True}


def test_dispatch_status() -> None:
    dispatch = make_dispatch(_controller())
    assert dispatch("status", {})["state"] == "idle"


def test_dispatch_log() -> None:
    from whisper_flow_local.transparency import TransparencyLog

    log = TransparencyLog(size=5)
    log.record("cleanup", "sys", "raw", "clean")
    deps = _Deps(
        audio=FakeAudioSource(),
        stt=FakeSTT("x"),
        injection=InjectionChain([FakeInjector("f")]),
        history=History(),
        transparency=log,
    )
    dispatch = make_dispatch(Controller(ControllerConfig(), deps))
    result = dispatch("log", {"n": 5})
    assert result["calls"][0]["output"] == "clean"


def test_dispatch_all_control_verbs() -> None:
    dispatch = make_dispatch(_controller())
    assert dispatch("toggle", {})["status"] == "started"
    assert dispatch("toggle", {})["status"] == "injected"
    assert dispatch("ptt-down", {})["status"] == "started"
    assert dispatch("ptt-up", {})["status"] == "injected"
    assert dispatch("cancel", {})["status"] == "noop"
    assert dispatch("paste-last", {})["status"] == "injected"
    assert dispatch("paste-last-raw", {})["status"] == "injected"


def test_dispatch_unknown_verb_raises() -> None:
    dispatch = make_dispatch(_controller())
    with pytest.raises(IPCError, match="unknown verb"):
        dispatch("frobnicate", {})


def test_dispatch_toggle_clean_arg() -> None:
    # A controller whose cleanup would fire, to prove clean=false skips it.
    calls: list[str] = []
    deps = _Deps(
        audio=FakeAudioSource(duration_s=1.0),
        stt=FakeSTT("a long enough transcript to exceed the fifty character gate here"),
        injection=InjectionChain([FakeInjector("f")]),
        history=History(size=5),
        cleanup=lambda raw, _o="": calls.append(raw) or "CLEANED",
    )
    from whisper_flow_local.controller import ControllerConfig

    ctl = Controller(ControllerConfig(min_duration_s=0.15, cleanup_min_chars=50), deps)
    dispatch = make_dispatch(ctl)
    dispatch("toggle", {})  # start
    result = dispatch("toggle", {"clean": False})  # stop, raw
    assert result["cleaned"] == ""
    assert calls == []  # cleanup skipped


def test_dispatch_ptt_up_clean_arg() -> None:
    dispatch = make_dispatch(_controller())
    dispatch("ptt-down", {})
    result = dispatch("ptt-up", {"clean": False})
    assert result["status"] == "injected"


def test_dispatch_command_arg() -> None:
    from whisper_flow_local.controller import ControllerConfig

    injector = FakeInjector("f")
    deps = _Deps(
        audio=FakeAudioSource(duration_s=1.0),
        stt=FakeSTT("make it formal"),
        injection=InjectionChain([injector]),
        history=History(),
        instruct=lambda instruction, text: "FORMAL TEXT",
        get_selection=lambda: "hey",
    )
    ctl = Controller(ControllerConfig(min_duration_s=0.15), deps)
    dispatch = make_dispatch(ctl)
    dispatch("ptt-down", {})
    result = dispatch("ptt-up", {"command": True})
    assert result["status"] == "injected"
    assert injector.requests[-1].text == "FORMAL TEXT"


def test_daemon_over_socket(tmp_path) -> None:
    sock = tmp_path / "wf.sock"
    daemon = Daemon(_controller(), sock)
    daemon.start()
    try:
        assert send(sock, "status")["data"]["state"] == "idle"
        assert send(sock, "toggle")["data"]["status"] == "started"
        assert send(sock, "toggle")["data"]["status"] == "injected"
        assert send(sock, "paste-last")["data"]["status"] == "injected"
        assert daemon.controller.status()["history_size"] == 1
    finally:
        daemon.stop()


def test_daemon_controller_property(tmp_path) -> None:
    ctl = _controller()
    daemon = Daemon(ctl, tmp_path / "wf.sock")
    assert daemon.controller is ctl


def test_daemon_manages_hotkey_listener(tmp_path) -> None:
    class FakeListener:
        def __init__(self) -> None:
            self.started = False
            self.stopped = False

        def start(self) -> None:
            self.started = True

        def stop(self) -> None:
            self.stopped = True

    listener = FakeListener()
    daemon = Daemon(_controller(), tmp_path / "wf.sock", hotkey_listener=listener)
    daemon.start()
    assert listener.started
    daemon.stop()
    assert listener.stopped


def test_daemon_manages_tray(tmp_path) -> None:
    class FakeTray:
        def __init__(self) -> None:
            self.started = False
            self.stopped = False

        def start(self) -> None:
            self.started = True

        def stop(self) -> None:
            self.stopped = True

    tray = FakeTray()
    daemon = Daemon(_controller(), tmp_path / "wf.sock")
    daemon.attach_tray(tray)
    daemon.start()
    assert tray.started
    daemon.stop()
    assert tray.stopped
