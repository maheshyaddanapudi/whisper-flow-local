"""Tests for the CLI entry point."""

from __future__ import annotations

import pytest

from whisper_flow_local import __version__
from whisper_flow_local.cli import main


def test_version(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_no_command_errors() -> None:
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code != 0


def test_config_path(capsys, tmp_path) -> None:
    p = tmp_path / "c.toml"
    assert main(["--config", str(p), "config", "path"]) == 0
    assert str(p) in capsys.readouterr().out


def test_config_show(capsys, tmp_path) -> None:
    assert main(["--config", str(tmp_path / "c.toml"), "config", "show"]) == 0
    out = capsys.readouterr().out
    assert "[hotkey]" in out


def test_config_init_and_force(capsys, tmp_path) -> None:
    p = tmp_path / "sub" / "c.toml"
    assert main(["--config", str(p), "config", "init"]) == 0
    assert p.exists()
    # second init without --force refuses
    assert main(["--config", str(p), "config", "init"]) == 1
    # with --force succeeds
    assert main(["--config", str(p), "config", "init", "--force"]) == 0


def test_gen_docs(capsys) -> None:
    assert main(["gen-docs"]) == 0
    assert "Configuration reference" in capsys.readouterr().out


def test_doctor(capsys, tmp_path) -> None:
    assert main(["--config", str(tmp_path / "c.toml"), "doctor"]) == 0
    assert "environment report" in capsys.readouterr().out


def test_invalid_config_returns_2(capsys, tmp_path) -> None:
    p = tmp_path / "bad.toml"
    p.write_text("[hotkey]\nbogus = 1\n", encoding="utf-8")
    assert main(["--config", str(p), "config", "show"]) == 2
    assert "config error" in capsys.readouterr().err


def test_control_verb_against_running_daemon(capsys, tmp_path) -> None:
    from fakes import FakeAudioSource, FakeInjector, FakeSTT
    from whisper_flow_local.controller import Controller, ControllerConfig, _Deps
    from whisper_flow_local.daemon import Daemon
    from whisper_flow_local.history import History
    from whisper_flow_local.inject.base import InjectionChain

    deps = _Deps(
        audio=FakeAudioSource(),
        stt=FakeSTT("x"),
        injection=InjectionChain([FakeInjector("f")]),
        history=History(),
    )
    sock = tmp_path / "wf.sock"
    daemon = Daemon(Controller(ControllerConfig(), deps), sock)
    daemon.start()
    try:
        rc = main(["--socket", str(sock), "status"])
        assert rc == 0
        assert "idle" in capsys.readouterr().out
    finally:
        daemon.stop()


def test_control_verb_no_daemon_errors(capsys, tmp_path) -> None:
    rc = main(["--socket", str(tmp_path / "absent.sock"), "status"])
    assert rc == 1
    assert "error" in capsys.readouterr().err


def test_start_builds_and_runs_daemon(capsys, tmp_path, monkeypatch) -> None:
    import whisper_flow_local.build as build_mod

    ran: dict = {}

    class FakeServer:
        path = tmp_path / "wf.sock"

    class FakeDaemon:
        _server = FakeServer()

        def run(self) -> None:
            ran["ran"] = True

    monkeypatch.setattr(build_mod, "build_daemon", lambda config: FakeDaemon())
    assert main(["--config", str(tmp_path / "c.toml"), "start"]) == 0
    assert ran.get("ran") is True
    assert "listening" in capsys.readouterr().out


def test_control_verb_reports_handler_error(capsys, tmp_path) -> None:
    from whisper_flow_local.ipc import IPCServer

    def dispatch(verb: str, args: dict) -> dict:
        raise ValueError("boom")

    sock = tmp_path / "wf.sock"
    server = IPCServer(sock, dispatch)
    server.start()
    try:
        rc = main(["--socket", str(sock), "toggle"])
        assert rc == 1
        assert "boom" in capsys.readouterr().err
    finally:
        server.stop()
