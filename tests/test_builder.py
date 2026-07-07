"""Tests for the pure config->objects wiring."""

from __future__ import annotations

from fakes import FakeInjector
from whisper_flow_local.builder import (
    build_cleanup_engine,
    build_controller_config,
    build_dictionary,
    build_injection_chain,
    build_replacement,
    dictionary_path,
    resolve_stt_backend_name,
)
from whisper_flow_local.config import Config
from whisper_flow_local.dictionary.replacements import Dictionary
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


def test_build_cleanup_engine_enabled() -> None:
    engine = build_cleanup_engine(Config())
    assert engine is not None
    assert "transcript cleaner" in engine.system_prompt.lower()


def test_build_cleanup_engine_disabled() -> None:
    cfg = Config()
    cfg.data["cleanup"]["enabled"] = False
    assert build_cleanup_engine(cfg) is None


def test_build_cleanup_engine_streams_when_on_token_given() -> None:
    tokens: list[str] = []
    engine = build_cleanup_engine(Config(), on_token=tokens.append)
    assert engine is not None
    # The engine routes completions through the streaming client; drive it with a
    # fake stream to prove on_token is wired through.
    engine._chat_stream = lambda *a, **k: (a[4]("Hi."), "Hi.")[1]  # a[4] is on_token
    assert engine.clean("um a reasonably long transcript to clean up here") == "Hi."
    assert tokens == ["Hi."]


def test_build_cleanup_engine_respects_goals() -> None:
    cfg = Config()
    cfg.data["cleanup"]["goal_fillers"] = False
    cfg.data["cleanup"]["goal_grammar"] = False
    cfg.data["cleanup"]["goal_stutters"] = False
    cfg.data["cleanup"]["goal_lists"] = False
    engine = build_cleanup_engine(cfg)
    assert engine is not None
    # only punctuation goal remains
    assert "punctuation" in engine.system_prompt.lower()
    assert "filler" not in engine.system_prompt.lower()


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


def test_build_controller_config_initial_prompt_from_dictionary() -> None:
    cc = build_controller_config(Config(), Dictionary(vocab=("MySQL", "Kubernetes")))
    assert cc.initial_prompt is not None
    assert "MySQL" in cc.initial_prompt


def test_dictionary_path_default_and_override(tmp_path) -> None:
    cfg = Config()
    assert dictionary_path(cfg).name == "dictionary.toml"
    cfg.data["dictionary"]["path"] = str(tmp_path / "custom.toml")
    assert dictionary_path(cfg) == tmp_path / "custom.toml"


def test_build_dictionary_disabled() -> None:
    cfg = Config()
    cfg.data["dictionary"]["enabled"] = False
    assert build_dictionary(cfg) == Dictionary()


def test_build_dictionary_loads_file(tmp_path) -> None:
    d_path = tmp_path / "dictionary.toml"
    d_path.write_text('vocab = ["Anthropic"]\n[words]\num = ""\n', encoding="utf-8")
    cfg = Config()
    cfg.data["dictionary"]["path"] = str(d_path)
    d = build_dictionary(cfg)
    assert d.vocab == ("Anthropic",)


def test_build_replacement_none_when_no_rules() -> None:
    assert build_replacement(Dictionary(vocab=("only", "vocab"))) is None


def test_build_replacement_applies_rules() -> None:
    fn = build_replacement(Dictionary(words=(("gonna", "going to"),)))
    assert fn is not None
    assert fn("i am gonna go") == "i am going to go"


def test_build_profiles_disabled() -> None:
    from whisper_flow_local.builder import build_profiles

    cfg = Config()
    cfg.data["profiles"]["enabled"] = False
    assert build_profiles(cfg) == []


def test_build_profiles_loads_file(tmp_path) -> None:
    from whisper_flow_local.builder import build_profiles

    path = tmp_path / "profiles.toml"
    path.write_text("[[profile]]\nname='slack'\napp='slack'\n", encoding="utf-8")
    cfg = Config()
    cfg.data["profiles"]["path"] = str(path)
    profiles = build_profiles(cfg)
    assert [p.name for p in profiles] == ["slack"]


def test_profiles_path_default_and_override(tmp_path) -> None:
    from whisper_flow_local.builder import profiles_path

    cfg = Config()
    assert profiles_path(cfg).name == "profiles.toml"
    cfg.data["profiles"]["path"] = str(tmp_path / "p.toml")
    assert profiles_path(cfg) == tmp_path / "p.toml"


def test_build_profile_resolver_none_when_empty() -> None:
    from whisper_flow_local.builder import build_profile_resolver

    assert build_profile_resolver([], lambda: ("", "")) is None


def test_build_profile_resolver_matches() -> None:
    from whisper_flow_local.builder import build_profile_resolver
    from whisper_flow_local.profiles import Profile

    profiles = [Profile(name="slack", app_pattern="slack", auto_submit=True)]
    resolve = build_profile_resolver(profiles, lambda: ("Slack", ""))
    assert resolve is not None
    active = resolve()
    assert active.name == "slack"
    assert active.auto_submit is True
