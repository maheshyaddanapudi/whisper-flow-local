"""Tests for the pure config->objects wiring."""

from __future__ import annotations

from fakes import FakeInjector
from whisper_flow_local.builder import (
    build_controller_config,
    build_injection_chain,
    resolve_stt_backend_name,
)
from whisper_flow_local.config import Config
from whisper_flow_local.recording import Mode


def test_resolve_stt_auto_macos() -> None:
    assert resolve_stt_backend_name(Config(), "Darwin") == "whispercpp"


def test_resolve_stt_auto_other() -> None:
    assert resolve_stt_backend_name(Config(), "Linux") == "faster_whisper"
    assert resolve_stt_backend_name(Config(), "Windows") == "faster_whisper"


def test_resolve_stt_explicit_wins() -> None:
    cfg = Config()
    cfg.data["stt"]["backend"] = "faster_whisper"
    assert resolve_stt_backend_name(cfg, "Darwin") == "faster_whisper"


def test_build_chain_orders_and_appends_copyonly() -> None:
    injectors = {
        "clipboard": FakeInjector("clipboard"),
        "keystrokes": FakeInjector("keystrokes"),
        "copy_only": FakeInjector("copy_only"),
    }
    chain = build_injection_chain(["clipboard", "keystrokes"], injectors)
    names = [b.name for b in chain.backends]
    assert names == ["clipboard", "keystrokes", "copy_only"]  # copy_only floor appended


def test_build_chain_skips_unknown_names() -> None:
    injectors = {"copy_only": FakeInjector("copy_only")}
    chain = build_injection_chain(["nonexistent", "copy_only"], injectors)
    assert [b.name for b in chain.backends] == ["copy_only"]


def test_build_chain_no_duplicate_copyonly() -> None:
    injectors = {"copy_only": FakeInjector("copy_only")}
    chain = build_injection_chain(["copy_only"], injectors)
    assert [b.name for b in chain.backends] == ["copy_only"]


def test_build_chain_without_copyonly_available() -> None:
    injectors = {"clipboard": FakeInjector("clipboard")}
    chain = build_injection_chain(["clipboard"], injectors)
    assert [b.name for b in chain.backends] == ["clipboard"]


def test_build_controller_config_maps_fields() -> None:
    cfg = Config()
    cc = build_controller_config(cfg)
    assert cc.mode == Mode.HYBRID
    assert cc.hold_threshold_s == 0.5
    assert cc.min_duration_s == 0.15
    assert cc.language is None  # 'auto' -> None
    assert cc.cleanup_min_chars == 50


def test_build_controller_config_explicit_language() -> None:
    cfg = Config()
    cfg.data["general"]["language"] = "en"
    cfg.data["inject"]["auto_submit"] = True
    cfg.data["inject"]["trailing_space"] = True
    cc = build_controller_config(cfg)
    assert cc.language == "en"
    assert cc.auto_submit is True
    assert cc.trailing_space is True
