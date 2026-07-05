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


def _cfg_with_dict(tmp_path):
    cfg = tmp_path / "c.toml"
    dict_path = tmp_path / "dictionary.toml"
    cfg.write_text(f'[dictionary]\npath = "{dict_path}"\n', encoding="utf-8")
    return cfg


def test_dict_add_and_show(capsys, tmp_path) -> None:
    cfg = _cfg_with_dict(tmp_path)
    assert main(["--config", str(cfg), "dict", "add", "Anthropic"]) == 0
    assert "added 'Anthropic'" in capsys.readouterr().out
    assert main(["--config", str(cfg), "dict", "show"]) == 0
    out = capsys.readouterr().out
    assert "Anthropic" in out


def test_dict_show_empty(capsys, tmp_path) -> None:
    cfg = _cfg_with_dict(tmp_path)
    assert main(["--config", str(cfg), "dict", "show"]) == 0
    assert "(empty)" in capsys.readouterr().out


def test_dict_add_empty_word_errors(capsys, tmp_path) -> None:
    cfg = _cfg_with_dict(tmp_path)
    assert main(["--config", str(cfg), "dict", "add", "   "]) == 1
    assert "error" in capsys.readouterr().err


def test_doctor_shows_macos_permissions(capsys, tmp_path, monkeypatch) -> None:
    import whisper_flow_local.cli as climod

    monkeypatch.setattr(climod.platform, "system", lambda: "Darwin")
    assert main(["--config", str(tmp_path / "c.toml"), "doctor"]) == 0
    out = capsys.readouterr().out
    assert "macOS permissions" in out
    assert "Accessibility" in out


def test_bench_audio_not_found(capsys, tmp_path) -> None:
    rc = main(["--config", str(tmp_path / "c.toml"), "bench", "--audio", str(tmp_path / "no.wav")])
    assert rc == 1
    assert "not found" in capsys.readouterr().err


def _write_wav(path, seconds=1.0, rate=16000) -> None:
    import struct
    import wave

    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack("<" + "h" * int(rate * seconds), *([0] * int(rate * seconds))))


def test_bench_runs_with_fake_timer(capsys, tmp_path, monkeypatch) -> None:
    import whisper_flow_local.cli as climod

    wav = tmp_path / "clip.wav"
    _write_wav(wav, seconds=2.0)
    # Replace the hardware timer with a deterministic fake.
    monkeypatch.setattr(climod, "_make_bench_timer", lambda cfg, audio: lambda m: 0.5)
    rc = main(
        ["--config", str(tmp_path / "c.toml"), "bench", "--audio", str(wav), "--models", "small.en"]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "small.en" in out
    assert "Recommended" in out


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


def test_raw_flag_sends_clean_false(tmp_path) -> None:
    from whisper_flow_local.ipc import IPCServer

    seen: list = []

    def dispatch(verb: str, args: dict) -> dict:
        seen.append((verb, args))
        return {"status": "injected"}

    sock = tmp_path / "wf.sock"
    server = IPCServer(sock, dispatch)
    server.start()
    try:
        assert main(["--socket", str(sock), "--raw", "toggle"]) == 0
        assert seen == [("toggle", {"clean": False})]
    finally:
        server.stop()


def test_log_command_shows_calls(capsys, tmp_path) -> None:
    from fakes import FakeAudioSource, FakeInjector, FakeSTT
    from whisper_flow_local.controller import Controller, ControllerConfig, _Deps
    from whisper_flow_local.daemon import Daemon
    from whisper_flow_local.history import History
    from whisper_flow_local.inject.base import InjectionChain
    from whisper_flow_local.transparency import TransparencyLog

    log = TransparencyLog(size=5)
    log.record("cleanup", "system prompt", "um raw", "clean")
    deps = _Deps(
        audio=FakeAudioSource(),
        stt=FakeSTT("x"),
        injection=InjectionChain([FakeInjector("f")]),
        history=History(),
        transparency=log,
    )
    sock = tmp_path / "wf.sock"
    daemon = Daemon(Controller(ControllerConfig(), deps), sock)
    daemon.start()
    try:
        assert main(["--socket", str(sock), "log"]) == 0
        out = capsys.readouterr().out
        assert "cleanup" in out
        assert "clean" in out
    finally:
        daemon.stop()


def test_log_command_empty(capsys, tmp_path) -> None:
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
        assert main(["--socket", str(sock), "log"]) == 0
        assert "no LLM calls" in capsys.readouterr().out
    finally:
        daemon.stop()


def test_log_command_no_daemon(capsys, tmp_path) -> None:
    assert main(["--socket", str(tmp_path / "absent.sock"), "log"]) == 1
    assert "error" in capsys.readouterr().err


def test_log_command_handler_error(capsys, tmp_path) -> None:
    from whisper_flow_local.ipc import IPCServer

    def dispatch(verb: str, args: dict) -> dict:
        raise ValueError("kaboom")

    sock = tmp_path / "wf.sock"
    server = IPCServer(sock, dispatch)
    server.start()
    try:
        assert main(["--socket", str(sock), "log"]) == 1
        assert "kaboom" in capsys.readouterr().err
    finally:
        server.stop()


def test_command_flag_sends_command_true(tmp_path) -> None:
    from whisper_flow_local.ipc import IPCServer

    seen: list = []

    def dispatch(verb: str, args: dict) -> dict:
        seen.append((verb, args))
        return {"status": "injected"}

    sock = tmp_path / "wf.sock"
    server = IPCServer(sock, dispatch)
    server.start()
    try:
        assert main(["--socket", str(sock), "--command", "ptt-up"]) == 0
        assert seen == [("ptt-up", {"command": True})]
    finally:
        server.stop()


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
