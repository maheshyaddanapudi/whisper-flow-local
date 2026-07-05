"""Schema-driven configuration.

Every configurable option is declared exactly once in ``SCHEMA``. That single
source of truth generates the defaults, validation, the documentation table and
the CLI help — so the three can never drift apart (a failure mode seen in prior
art where settings, docs and code disagree).

The core module has no third-party dependencies: TOML reading uses the stdlib
``tomllib`` and writing is done with a tiny local serializer, so config works in
any environment even before the optional hardware extras are installed.
"""

from __future__ import annotations

import os
import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

CONFIG_VERSION = 1
"""Bumped when a migration is needed; written into every config file."""

ENV_PREFIX = "WHISPER_FLOW_"
"""Any setting can be overridden by ``WHISPER_FLOW_<SECTION>_<NAME>`` in the
environment, e.g. ``WHISPER_FLOW_CLEANUP_MODEL``. Precedence: env > file >
default."""

OptionType = Literal["bool", "int", "float", "str", "list[str]"]


class ConfigError(ValueError):
    """Raised when a config file is malformed or fails validation."""


@dataclass(frozen=True)
class Option:
    """One configurable setting, declared once and used everywhere."""

    key: str  # dotted, e.g. "hotkey.primary"
    type: OptionType
    default: Any
    description: str
    choices: tuple[Any, ...] | None = None
    minimum: float | None = None
    maximum: float | None = None

    @property
    def section(self) -> str:
        return self.key.split(".", 1)[0]

    def validate(self, value: Any) -> Any:
        """Return the coerced value or raise ConfigError."""
        value = self._coerce(value)
        if self.choices is not None and value not in self.choices:
            raise ConfigError(f"{self.key}: {value!r} is not one of {list(self.choices)}")
        if self.minimum is not None and value < self.minimum:
            raise ConfigError(f"{self.key}: {value} is below minimum {self.minimum}")
        if self.maximum is not None and value > self.maximum:
            raise ConfigError(f"{self.key}: {value} is above maximum {self.maximum}")
        return value

    def _coerce(self, value: Any) -> Any:
        if self.type == "bool":
            if not isinstance(value, bool):
                raise ConfigError(f"{self.key}: expected true/false, got {value!r}")
            return value
        if self.type == "int":
            if isinstance(value, bool) or not isinstance(value, int):
                raise ConfigError(f"{self.key}: expected an integer, got {value!r}")
            return value
        if self.type == "float":
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise ConfigError(f"{self.key}: expected a number, got {value!r}")
            return float(value)
        if self.type == "str":
            if not isinstance(value, str):
                raise ConfigError(f"{self.key}: expected a string, got {value!r}")
            return value
        if self.type == "list[str]":
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise ConfigError(f"{self.key}: expected a list of strings, got {value!r}")
            return list(value)
        raise ConfigError(f"{self.key}: unknown option type {self.type!r}")  # pragma: no cover


# --- The schema: the ONE place options are defined -------------------------
#
# Options are added here as phases land. Each carries type/default/description
# and optional choices/bounds. Keep keys grouped by dotted section.

SCHEMA: tuple[Option, ...] = (
    # [general]
    Option("general.language", "str", "auto", "Spoken language hint for STT ('auto' to detect)."),
    Option(
        "general.max_recording_seconds",
        "int",
        300,
        "Hard safety cap on a single recording.",
        minimum=1,
        maximum=3600,
    ),
    # [hotkey]
    Option(
        "hotkey.primary",
        "str",
        "ctrl+shift+space",
        "Global hotkey for dictation (tap = toggle, hold = push-to-talk).",
    ),
    Option(
        "hotkey.mode",
        "str",
        "hybrid",
        "Recording mode for the primary hotkey.",
        choices=("hybrid", "toggle", "push_to_talk", "continuous"),
    ),
    Option(
        "hotkey.hold_threshold_ms",
        "int",
        500,
        "Hold longer than this to act as push-to-talk; shorter is a toggle tap.",
        minimum=50,
        maximum=5000,
    ),
    Option(
        "hotkey.min_duration_ms",
        "int",
        150,
        "Recordings shorter than this are discarded as accidental taps.",
        minimum=0,
        maximum=5000,
    ),
    Option(
        "hotkey.release_grace_ms",
        "int",
        500,
        "Grace period after PTT key release before stopping capture.",
        minimum=0,
        maximum=5000,
    ),
    Option(
        "hotkey.backend",
        "str",
        "auto",
        "Hotkey listener backend.",
        choices=("auto", "pynput", "evdev", "quartz", "none"),
    ),
    # [audio]
    Option(
        "audio.sample_rate",
        "int",
        16000,
        "Capture sample rate in Hz (Whisper-native is 16000).",
        choices=(8000, 16000, 22050, 44100, 48000),
    ),
    Option(
        "audio.device", "str", "", "Input device name substring; empty uses the system default."
    ),
    Option(
        "audio.chunk_ms",
        "int",
        500,
        "Audio capture chunk size in milliseconds.",
        minimum=10,
        maximum=2000,
    ),
    Option(
        "audio.cues", "bool", True, "Play short start/stop sounds so push-to-talk works eyes-free."
    ),
    # [vad]
    Option(
        "vad.enabled",
        "bool",
        True,
        "Two-layer VAD: silence auto-stop plus Silero audio scrubbing before STT.",
    ),
    Option(
        "vad.silence_threshold",
        "float",
        0.01,
        "RMS energy below this counts as silence.",
        minimum=0.0,
        maximum=1.0,
    ),
    Option(
        "vad.silence_duration_ms",
        "int",
        900,
        "Stop after this much continuous silence (VAD and continuous modes).",
        minimum=100,
        maximum=10000,
    ),
    # [dictionary]
    Option(
        "dictionary.path",
        "str",
        "",
        "Path to the personal-dictionary TOML; empty uses the default location.",
    ),
    Option(
        "dictionary.enabled",
        "bool",
        True,
        "Apply vocabulary hints and deterministic replacements.",
    ),
    # [profiles]
    Option(
        "profiles.enabled",
        "bool",
        True,
        "Apply per-app tone/formatting profiles based on the focused app.",
    ),
    Option(
        "profiles.path",
        "str",
        "",
        "Path to the per-app profiles TOML; empty uses the default location.",
    ),
    # [stt]
    Option(
        "stt.backend",
        "str",
        "auto",
        "Speech-to-text engine. 'auto' picks whisper.cpp on macOS, else faster-whisper.",
        choices=("auto", "faster_whisper", "whispercpp"),
    ),
    Option("stt.model", "str", "small.en", "Model name/size to load."),
    Option(
        "stt.compute_type",
        "str",
        "int8",
        "faster-whisper compute type.",
        choices=("int8", "int8_float16", "float16", "float32"),
    ),
    Option(
        "stt.device",
        "str",
        "auto",
        "Compute device for faster-whisper.",
        choices=("auto", "cpu", "cuda"),
    ),
    Option(
        "stt.unload_after_seconds",
        "int",
        300,
        "Unload the STT model after this idle period (0 = keep forever).",
        minimum=0,
        maximum=86400,
    ),
    Option(
        "stt.streaming_preview",
        "bool",
        False,
        "Show a live partial transcript (fast model) while you speak.",
    ),
    Option(
        "stt.preview_model",
        "str",
        "tiny.en",
        "Fast model used only for the streaming preview.",
    ),
    # [cleanup]  (wired in Phase 2)
    Option(
        "cleanup.enabled",
        "bool",
        True,
        "Run the Ollama LLM cleanup pass on transcripts (core feature).",
    ),
    Option(
        "cleanup.model",
        "str",
        "gemma3:4b",
        "Ollama model for cleanup. Models under ~3B may transform meaning.",
    ),
    Option(
        "cleanup.ollama_host",
        "str",
        "http://localhost:11434",
        "Base URL of the local Ollama server.",
    ),
    Option(
        "cleanup.min_chars",
        "int",
        50,
        "Skip the LLM stage for transcripts shorter than this (latency guard).",
        minimum=0,
        maximum=10000,
    ),
    Option(
        "cleanup.timeout_seconds",
        "float",
        8.0,
        "Give up on cleanup after this long and inject the raw transcript.",
        minimum=0.1,
        maximum=120.0,
    ),
    Option(
        "cleanup.keep_alive",
        "str",
        "30m",
        "Ollama keep_alive so the model stays warm between dictations.",
    ),
    Option("cleanup.goal_punctuation", "bool", True, "Fix punctuation and capitalization."),
    Option("cleanup.goal_grammar", "bool", True, "Light grammar correction."),
    Option("cleanup.goal_fillers", "bool", True, "Remove filler words (um, uh, like)."),
    Option("cleanup.goal_stutters", "bool", True, "Collapse stutters and self-corrections."),
    Option("cleanup.goal_lists", "bool", True, "Format dictated lists."),
    Option(
        "cleanup.prompt_override",
        "str",
        "",
        "Custom cleanup system prompt; empty uses the compiled default.",
    ),
    Option(
        "cleanup.instruction_prompt_override",
        "str",
        "",
        "Custom command-mode (instruction) system prompt; empty uses the default.",
    ),
    Option(
        "cleanup.max_growth_ratio",
        "float",
        2.5,
        "Safety net: if cleaned text is longer than this ratio of the raw "
        "(a model that answered/expanded instead of cleaning), inject raw instead.",
        minimum=1.0,
        maximum=100.0,
    ),
    # [inject]
    Option(
        "inject.chain",
        "list[str]",
        ["clipboard", "keystrokes", "copy_only"],
        "Ordered injection backends to try, first that works wins.",
    ),
    Option(
        "inject.auto_submit",
        "bool",
        False,
        "Press Enter after injecting (off by default; never surprise the user).",
    ),
    Option("inject.trailing_space", "bool", False, "Append a trailing space after injected text."),
    Option(
        "inject.paste_timeout_seconds",
        "float",
        2.0,
        "Max time to wait for a clipboard-paste backend to confirm.",
        minimum=0.1,
        maximum=30.0,
    ),
    # [history]
    Option(
        "history.size",
        "int",
        10,
        "How many recent dictations to keep for re-paste (in memory).",
        minimum=0,
        maximum=1000,
    ),
    Option(
        "history.persist",
        "bool",
        False,
        "Persist history to disk (off = audio/text never touch disk).",
    ),
    # [transparency]
    Option(
        "transparency.enabled",
        "bool",
        True,
        "Keep an in-memory log of exactly what was sent to the local LLM.",
    ),
    Option(
        "transparency.size",
        "int",
        20,
        "How many recent LLM calls to keep (in memory only, never persisted).",
        minimum=0,
        maximum=1000,
    ),
    # [ui]
    Option("ui.enabled", "bool", True, "Show the tray icon and status overlay."),
)

_SCHEMA_BY_KEY: dict[str, Option] = {opt.key: opt for opt in SCHEMA}


def defaults() -> dict[str, Any]:
    """Nested default config derived from the schema."""
    out: dict[str, Any] = {"version": CONFIG_VERSION}
    for opt in SCHEMA:
        section, name = opt.key.split(".", 1)
        out.setdefault(section, {})[name] = opt.default
    return out


@dataclass
class Config:
    """Validated configuration with dotted-key access."""

    data: dict[str, Any] = field(default_factory=defaults)

    def get(self, key: str, /) -> Any:
        """Fetch by dotted key, e.g. ``cfg.get("hotkey.primary")``."""
        if key not in _SCHEMA_BY_KEY:
            raise KeyError(f"unknown config key: {key}")
        section, name = key.split(".", 1)
        return self.data.get(section, {}).get(name, _SCHEMA_BY_KEY[key].default)

    def section(self, name: str, /) -> Mapping[str, Any]:
        value = self.data.get(name, {})
        return value if isinstance(value, dict) else {}


def _validate(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Merge raw values over defaults, validating every known key.

    Unknown sections/keys raise, so typos surface immediately rather than being
    silently ignored.
    """
    result = defaults()
    version = raw.get("version", CONFIG_VERSION)
    if not isinstance(version, int):
        raise ConfigError(f"version: expected an integer, got {version!r}")
    result["version"] = version

    for section, values in raw.items():
        if section == "version":
            continue
        if not isinstance(values, Mapping):
            raise ConfigError(f"[{section}] must be a table")
        for name, value in values.items():
            key = f"{section}.{name}"
            opt = _SCHEMA_BY_KEY.get(key)
            if opt is None:
                raise ConfigError(f"unknown option: {key}")
            result[section][name] = opt.validate(value)
    return result


def env_var_name(key: str) -> str:
    """The environment variable that overrides a config ``key``.

    ``cleanup.model`` -> ``WHISPER_FLOW_CLEANUP_MODEL``. Because the mapping is
    generated per known key, section/name underscores are never ambiguous.
    """
    return ENV_PREFIX + key.replace(".", "_").upper()


def _parse_env_value(opt: Option, raw: str) -> Any:
    """Coerce an environment-variable string to the option's type."""
    if opt.type == "bool":
        lowered = raw.strip().lower()
        if lowered in ("1", "true", "yes", "on"):
            return True
        if lowered in ("0", "false", "no", "off"):
            return False
        raise ConfigError(f"{env_var_name(opt.key)}: expected a boolean, got {raw!r}")
    if opt.type == "int":
        try:
            return int(raw)
        except ValueError as exc:
            raise ConfigError(f"{env_var_name(opt.key)}: expected an integer, got {raw!r}") from exc
    if opt.type == "float":
        try:
            return float(raw)
        except ValueError as exc:
            raise ConfigError(f"{env_var_name(opt.key)}: expected a number, got {raw!r}") from exc
    if opt.type == "list[str]":
        return [item.strip() for item in raw.split(",") if item.strip()]
    return raw  # str


def apply_env_overrides(data: dict[str, Any], environ: Mapping[str, str]) -> dict[str, Any]:
    """Override config values from ``WHISPER_FLOW_*`` environment variables."""
    for opt in SCHEMA:
        raw = environ.get(env_var_name(opt.key))
        if raw is None:
            continue
        section, name = opt.key.split(".", 1)
        data[section][name] = opt.validate(_parse_env_value(opt, raw))
    return data


def load(path: Path | None = None, environ: Mapping[str, str] | None = None) -> Config:
    """Load config from ``path``, then apply ``WHISPER_FLOW_*`` env overrides.

    Precedence: environment variables > config file > schema defaults.
    """
    environ = os.environ if environ is None else environ
    if path is None or not path.exists():
        data = defaults()
    else:
        try:
            raw = tomllib.loads(path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"{path}: invalid TOML: {exc}") from exc
        data = _validate(raw)
    return Config(apply_env_overrides(data, environ))


def default_config_path() -> Path:
    """Standard config location (``~/.config/whisper-flow/config.toml``)."""
    import os

    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / "whisper-flow" / "config.toml"


def _toml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, list):
        return "[" + ", ".join(_toml_scalar(v) for v in value) + "]"
    return str(value)


def dumps(config: Config | None = None) -> str:
    """Serialize a config to TOML text, with the description of each option as a comment."""
    cfg = config or Config()
    lines: list[str] = [
        "# whisper-flow-local configuration",
        "# Generated from the schema; every option is documented inline.",
        f"version = {cfg.data.get('version', CONFIG_VERSION)}",
        "",
    ]
    sections: dict[str, list[Option]] = {}
    for opt in SCHEMA:
        sections.setdefault(opt.section, []).append(opt)
    for section, opts in sections.items():
        lines.append(f"[{section}]")
        for opt in opts:
            _, name = opt.key.split(".", 1)
            lines.append(f"# {opt.description}")
            if opt.choices is not None:
                lines.append(f"# choices: {', '.join(str(c) for c in opt.choices)}")
            lines.append(f"{name} = {_toml_scalar(cfg.get(opt.key))}")
        lines.append("")
    return "\n".join(lines)


def generate_docs() -> str:
    """Markdown table of every option — the settings reference, from one source."""
    lines = [
        "# Configuration reference",
        "",
        "_Generated from the config schema — do not edit by hand._",
        "",
        "Settings live in `~/.config/whisper-flow/config.toml`. Any option can be",
        "overridden by an environment variable named `WHISPER_FLOW_<SECTION>_<NAME>`",
        "(e.g. `cleanup.model` -> `WHISPER_FLOW_CLEANUP_MODEL`). Precedence:",
        "environment variable > config file > default.",
        "",
        "| Key | Env var | Type | Default | Choices | Description |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for opt in SCHEMA:
        choices = ", ".join(str(c) for c in opt.choices) if opt.choices else ""
        default = _toml_scalar(opt.default)
        env = env_var_name(opt.key)
        lines.append(
            f"| `{opt.key}` | `{env}` | {opt.type} | `{default}` | {choices} | {opt.description} |"
        )
    return "\n".join(lines) + "\n"


def iter_options() -> Iterable[Option]:
    """Iterate the schema (used by the CLI to build help)."""
    return SCHEMA
