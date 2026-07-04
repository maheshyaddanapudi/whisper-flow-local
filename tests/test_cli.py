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
