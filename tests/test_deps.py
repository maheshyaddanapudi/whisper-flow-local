"""Tests for the environment / dependency report."""

from __future__ import annotations

from whisper_flow_local import deps
from whisper_flow_local.config import Config


def test_collect_includes_core_rows(mock_ollama) -> None:
    cfg = Config()
    cfg.data["cleanup"]["ollama_host"] = mock_ollama.host
    caps = deps.collect(cfg)
    names = {c.name for c in caps}
    assert "Python" in names
    assert "STT: faster-whisper" in names
    assert "Cleanup: Ollama" in names
    assert "Inject: clipboard" in names


def test_ollama_row_reports_present_model(mock_ollama) -> None:
    cfg = Config()
    cfg.data["cleanup"]["ollama_host"] = mock_ollama.host
    cfg.data["cleanup"]["model"] = "gemma3:4b"
    caps = deps.collect(cfg)
    ollama = next(c for c in caps if c.name == "Cleanup: Ollama")
    assert ollama.available
    assert "present" in ollama.detail


def test_ollama_row_reports_missing_model(mock_ollama) -> None:
    cfg = Config()
    cfg.data["cleanup"]["ollama_host"] = mock_ollama.host
    cfg.data["cleanup"]["model"] = "not-installed"
    caps = deps.collect(cfg)
    ollama = next(c for c in caps if c.name == "Cleanup: Ollama")
    assert "MISSING" in ollama.detail


def test_ollama_row_unreachable() -> None:
    cfg = Config()
    cfg.data["cleanup"]["ollama_host"] = "http://127.0.0.1:1"
    caps = deps.collect(cfg)
    ollama = next(c for c in caps if c.name == "Cleanup: Ollama")
    assert not ollama.available
    assert "not reachable" in ollama.detail


def test_render_report_shows_mode_line(mock_ollama) -> None:
    cfg = Config()
    cfg.data["cleanup"]["ollama_host"] = mock_ollama.host
    report = deps.render_report(cfg)
    assert "environment report" in report
    assert "Mode available on this machine:" in report


def test_injection_capabilities_non_linux(monkeypatch) -> None:
    monkeypatch.setattr(deps.platform, "system", lambda: "Darwin")
    caps = deps._injection_capabilities()
    names = {c.name for c in caps}
    assert "Inject: clipboard" in names
    assert not any("xdotool" in n for n in names)  # no Linux tool rows off Linux


def test_injection_capabilities_linux(monkeypatch) -> None:
    monkeypatch.setattr(deps.platform, "system", lambda: "Linux")
    monkeypatch.setattr(deps.shutil, "which", lambda tool: "/usr/bin/" + tool)
    caps = deps._injection_capabilities()
    names = {c.name for c in caps}
    assert "Inject: xdotool" in names
    assert "Inject: wtype" in names


def test_hotkey_capabilities_linux(monkeypatch) -> None:
    monkeypatch.setattr(deps.platform, "system", lambda: "Linux")
    caps = deps._hotkey_capabilities()
    assert any(c.name == "Hotkey: evdev" for c in caps)


def test_hotkey_capabilities_non_linux(monkeypatch) -> None:
    monkeypatch.setattr(deps.platform, "system", lambda: "Darwin")
    caps = deps._hotkey_capabilities()
    assert not any(c.name == "Hotkey: evdev" for c in caps)


def test_ui_capabilities_tkinter_present() -> None:
    caps = deps._ui_capabilities(importer=lambda name: object())
    assert caps[0].name == "UI: overlay (tkinter)"
    assert caps[0].available is True
    assert "overlay" in caps[0].detail


def test_ui_capabilities_tkinter_missing() -> None:
    def importer(name: str) -> object:
        raise ImportError("No module named '_tkinter'")

    caps = deps._ui_capabilities(importer=importer)
    assert caps[0].available is False
    assert "python-tk" in caps[0].detail  # the actionable macOS hint


def test_degradation_levels() -> None:
    from whisper_flow_local.deps import Capability, _degradation_level

    def cap(name: str, ok: bool) -> Capability:
        return Capability(name, ok, "")

    no_stt = [cap("STT: faster-whisper", False), cap("STT: whisper.cpp", False)]
    assert "not-ready" in _degradation_level(no_stt)

    full = [
        cap("STT: faster-whisper", True),
        cap("Inject: keystrokes (pynput)", True),
        cap("Hotkey: pynput", True),
    ]
    assert _degradation_level(full).startswith("full")

    copy_only = [
        cap("STT: faster-whisper", True),
        cap("Inject: keystrokes (pynput)", False),
        cap("Hotkey: pynput", True),
    ]
    assert _degradation_level(copy_only).startswith("copy-only")

    manual = [
        cap("STT: faster-whisper", True),
        cap("Inject: keystrokes (pynput)", False),
        cap("Hotkey: pynput", False),
    ]
    assert _degradation_level(manual).startswith("manual")
