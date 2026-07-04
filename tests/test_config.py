"""Tests for the schema-driven config module."""

from __future__ import annotations

import pytest

from whisper_flow_local import config as cfgmod
from whisper_flow_local.config import (
    CONFIG_VERSION,
    Config,
    ConfigError,
    Option,
    default_config_path,
    defaults,
    dumps,
    generate_docs,
    iter_options,
    load,
)


def test_defaults_cover_every_schema_option() -> None:
    d = defaults()
    assert d["version"] == CONFIG_VERSION
    for opt in iter_options():
        section, name = opt.key.split(".", 1)
        assert d[section][name] == opt.default


def test_config_get_and_section() -> None:
    cfg = Config()
    assert cfg.get("hotkey.primary") == "ctrl+shift+space"
    assert cfg.get("cleanup.enabled") is True
    assert cfg.section("hotkey")["mode"] == "hybrid"
    assert cfg.section("does_not_exist") == {}


def test_config_get_unknown_key_raises() -> None:
    with pytest.raises(KeyError):
        Config().get("nope.nope")


def test_config_get_falls_back_to_default_when_section_missing() -> None:
    cfg = Config(data={"version": CONFIG_VERSION})
    assert cfg.get("audio.sample_rate") == 16000


@pytest.mark.parametrize(
    ("opt", "value"),
    [
        (Option("s.b", "bool", False, ""), True),
        (Option("s.i", "int", 0, ""), 5),
        (Option("s.f", "float", 0.0, ""), 3),  # int coerces to float
        (Option("s.s", "str", "", ""), "x"),
        (Option("s.l", "list[str]", [], ""), ["a", "b"]),
    ],
)
def test_option_validate_accepts_valid(opt: Option, value: object) -> None:
    result = opt.validate(value)
    if opt.type == "float":
        assert isinstance(result, float)
    else:
        assert result == value


@pytest.mark.parametrize(
    ("opt", "value"),
    [
        (Option("s.b", "bool", False, ""), 1),
        (Option("s.i", "int", 0, ""), True),  # bool is not int here
        (Option("s.i", "int", 0, ""), "5"),
        (Option("s.f", "float", 0.0, ""), "x"),
        (Option("s.f", "float", 0.0, ""), True),
        (Option("s.s", "str", "", ""), 5),
        (Option("s.l", "list[str]", [], ""), ["a", 1]),
        (Option("s.l", "list[str]", [], ""), "notalist"),
    ],
)
def test_option_validate_rejects_wrong_type(opt: Option, value: object) -> None:
    with pytest.raises(ConfigError):
        opt.validate(value)


def test_option_choices_and_bounds() -> None:
    choice = Option("s.c", "str", "a", "", choices=("a", "b"))
    assert choice.validate("b") == "b"
    with pytest.raises(ConfigError):
        choice.validate("c")

    bounded = Option("s.n", "int", 5, "", minimum=1, maximum=10)
    assert bounded.validate(1) == 1
    assert bounded.validate(10) == 10
    with pytest.raises(ConfigError):
        bounded.validate(0)
    with pytest.raises(ConfigError):
        bounded.validate(11)


def test_option_unknown_type_raises() -> None:
    with pytest.raises(ConfigError):
        Option("s.x", "weird", None, "").validate("v")  # type: ignore[arg-type]


def test_option_section_property() -> None:
    assert Option("hotkey.primary", "str", "", "").section == "hotkey"


def test_load_missing_returns_defaults(tmp_path) -> None:
    assert load(tmp_path / "absent.toml").get("stt.model") == "small.en"
    assert load(None).get("stt.model") == "small.en"


def test_load_roundtrip(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(dumps(Config()), encoding="utf-8")
    loaded = load(path)
    assert loaded.get("hotkey.mode") == "hybrid"
    assert loaded.get("cleanup.model") == "gemma3:4b"


def test_load_overrides_merge_over_defaults(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        "\n".join(
            [
                "version = 1",
                "[hotkey]",
                'mode = "toggle"',
                "[cleanup]",
                "min_chars = 20",
            ]
        ),
        encoding="utf-8",
    )
    cfg = load(path)
    assert cfg.get("hotkey.mode") == "toggle"
    assert cfg.get("cleanup.min_chars") == 20
    # untouched keys keep defaults
    assert cfg.get("hotkey.hold_threshold_ms") == 500


def test_load_rejects_unknown_option(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[hotkey]\nbogus = 1\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="unknown option"):
        load(path)


def test_load_rejects_bad_version(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('version = "one"\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="version"):
        load(path)


def test_load_rejects_non_table_section(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("hotkey = 5\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="must be a table"):
        load(path)


def test_load_rejects_invalid_toml(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("this is not = = toml", encoding="utf-8")
    with pytest.raises(ConfigError, match="invalid TOML"):
        load(path)


def test_load_rejects_out_of_choice_value(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('[hotkey]\nmode = "nonsense"\n', encoding="utf-8")
    with pytest.raises(ConfigError):
        load(path)


def test_dumps_contains_sections_and_comments() -> None:
    text = dumps(Config())
    assert "[hotkey]" in text
    assert "# " in text  # descriptions rendered as comments
    assert "version = 1" in text
    # list option serialized as a TOML array
    assert 'chain = ["clipboard", "keystrokes", "copy_only"]' in text


def test_dumps_escapes_quotes() -> None:
    cfg = Config()
    cfg.data["cleanup"]["prompt_override"] = 'say "hi"\\path'
    text = dumps(cfg)
    assert '\\"hi\\"' in text
    assert "\\\\path" in text


def test_generate_docs_table() -> None:
    docs = generate_docs()
    assert "| Key | Env var | Type | Default | Choices | Description |" in docs
    assert "`hotkey.primary`" in docs
    assert "`WHISPER_FLOW_HOTKEY_PRIMARY`" in docs  # env var column
    assert "hybrid" in docs  # a choices cell


def test_default_config_path_respects_xdg(monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", "/custom/cfg")
    assert default_config_path() == cfgmod.Path("/custom/cfg/whisper-flow/config.toml")


def test_default_config_path_without_xdg(monkeypatch) -> None:
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    path = default_config_path()
    assert path.name == "config.toml"
    assert path.parent.name == "whisper-flow"


def test_toml_scalar_number_passthrough() -> None:
    # ints/floats render bare
    assert cfgmod._toml_scalar(5) == "5"
    assert cfgmod._toml_scalar(1.5) == "1.5"


# --- environment-variable overrides ------------------------------------------


def test_env_var_name() -> None:
    assert cfgmod.env_var_name("cleanup.model") == "WHISPER_FLOW_CLEANUP_MODEL"
    assert (
        cfgmod.env_var_name("hotkey.hold_threshold_ms") == "WHISPER_FLOW_HOTKEY_HOLD_THRESHOLD_MS"
    )


def test_env_overrides_string(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WHISPER_FLOW_CLEANUP_MODEL", "gemma2:27b")
    cfg = load(tmp_path / "absent.toml")
    assert cfg.get("cleanup.model") == "gemma2:27b"


def test_env_overrides_beat_file(tmp_path, monkeypatch) -> None:
    path = tmp_path / "config.toml"
    path.write_text('[cleanup]\nmodel = "from-file"\n', encoding="utf-8")
    # file value first
    assert load(path, environ={}).get("cleanup.model") == "from-file"
    # env wins over file
    monkeypatch.setenv("WHISPER_FLOW_CLEANUP_MODEL", "from-env")
    assert load(path).get("cleanup.model") == "from-env"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("true", True),
        ("1", True),
        ("yes", True),
        ("on", True),
        ("false", False),
        ("0", False),
        ("no", False),
        ("off", False),
    ],
)
def test_env_parses_bool(raw: str, expected: bool) -> None:
    cfg = load(None, environ={"WHISPER_FLOW_CLEANUP_ENABLED": raw})
    assert cfg.get("cleanup.enabled") is expected


def test_env_parses_int_and_float() -> None:
    cfg = load(
        None,
        environ={
            "WHISPER_FLOW_CLEANUP_MIN_CHARS": "25",
            "WHISPER_FLOW_CLEANUP_TIMEOUT_SECONDS": "12.5",
        },
    )
    assert cfg.get("cleanup.min_chars") == 25
    assert cfg.get("cleanup.timeout_seconds") == 12.5


def test_env_parses_list() -> None:
    cfg = load(None, environ={"WHISPER_FLOW_INJECT_CHAIN": "clipboard, copy_only"})
    assert cfg.get("inject.chain") == ["clipboard", "copy_only"]


def test_env_invalid_bool_raises() -> None:
    with pytest.raises(ConfigError, match="boolean"):
        load(None, environ={"WHISPER_FLOW_CLEANUP_ENABLED": "maybe"})


def test_env_invalid_int_raises() -> None:
    with pytest.raises(ConfigError, match="integer"):
        load(None, environ={"WHISPER_FLOW_CLEANUP_MIN_CHARS": "lots"})


def test_env_invalid_float_raises() -> None:
    with pytest.raises(ConfigError, match="number"):
        load(None, environ={"WHISPER_FLOW_CLEANUP_TIMEOUT_SECONDS": "soon"})


def test_env_still_validated_against_choices() -> None:
    with pytest.raises(ConfigError):
        load(None, environ={"WHISPER_FLOW_HOTKEY_MODE": "nonsense"})


def test_env_ignores_unrelated_vars() -> None:
    cfg = load(None, environ={"PATH": "/usr/bin", "WHISPER_FLOW_NOT_A_KEY": "x"})
    assert cfg.get("cleanup.model") == "gemma3:4b"  # unchanged default
