"""Pure wiring: translate a :class:`Config` into runtime objects.

Kept separate from the daemon so the decisions (which STT backend, how to order
the injection chain, how config maps to :class:`ControllerConfig`) are unit
tested with fakes, while the daemon only supplies real adapters and threads.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .cleanup.engine import CleanupEngine, RecordFn, TokenFn
from .cleanup.prompts import CleanupGoals
from .config import Config
from .controller import ControllerConfig, ProfileFn, ReplaceFn
from .dictionary.replacements import Dictionary, ReplacementEngine, initial_prompt, load
from .inject.base import InjectionChain, Injector
from .profiles import ActiveProfile, Profile, match_profile
from .profiles import load as load_profiles
from .recording import Mode


def resolve_stt_backend_name(config: Config, system: str) -> str:
    """Resolve ``stt.backend`` ('auto' -> whisper.cpp on macOS, else faster-whisper)."""
    backend = str(config.get("stt.backend"))
    if backend != "auto":
        return backend
    return "whispercpp" if system == "Darwin" else "faster_whisper"


def build_injection_chain(names: list[str], injectors: dict[str, Injector]) -> InjectionChain:
    """Order the configured injector names, skipping any not provided.

    Copy-only is always appended as the final floor so a dictation is never
    lost, even if the user's configured chain is empty or all unavailable.
    """
    ordered: list[Injector] = []
    seen: set[str] = set()
    for name in names:
        inj = injectors.get(name)
        if inj is not None and name not in seen:
            ordered.append(inj)
            seen.add(name)
    if "copy_only" in injectors and "copy_only" not in seen:
        ordered.append(injectors["copy_only"])
    return InjectionChain(ordered)


def build_cleanup_engine(
    config: Config,
    record: RecordFn | None = None,
    on_token: TokenFn | None = None,
) -> CleanupEngine | None:
    """Build the Ollama cleanup engine, or None if cleanup is disabled.

    ``record`` is an optional transparency callback (kind, system, user, output).
    ``on_token``, when set, streams the refinement token-by-token to the overlay.
    """
    if not bool(config.get("cleanup.enabled")):
        return None
    goals = CleanupGoals(
        punctuation=bool(config.get("cleanup.goal_punctuation")),
        grammar=bool(config.get("cleanup.goal_grammar")),
        fillers=bool(config.get("cleanup.goal_fillers")),
        stutters=bool(config.get("cleanup.goal_stutters")),
        lists=bool(config.get("cleanup.goal_lists")),
    )
    return CleanupEngine(
        host=str(config.get("cleanup.ollama_host")),
        model=str(config.get("cleanup.model")),
        goals=goals,
        prompt_override=str(config.get("cleanup.prompt_override")),
        instruction_override=str(config.get("cleanup.instruction_prompt_override")),
        keep_alive=str(config.get("cleanup.keep_alive")),
        timeout=float(config.get("cleanup.timeout_seconds")),
        max_growth_ratio=float(config.get("cleanup.max_growth_ratio")),
        record=record,
        on_token=on_token,
    )


def default_dictionary_path() -> Path:
    """Standard dictionary location next to the config file."""
    from .config import default_config_path

    return default_config_path().parent / "dictionary.toml"


def dictionary_path(config: Config) -> Path:
    configured = str(config.get("dictionary.path"))
    return Path(configured) if configured else default_dictionary_path()


def build_dictionary(config: Config) -> Dictionary:
    """Load the personal dictionary (empty if disabled or absent)."""
    if not bool(config.get("dictionary.enabled")):
        return Dictionary()
    return load(dictionary_path(config))


def build_replacement(dictionary: Dictionary) -> ReplaceFn | None:
    """Return a replacement function, or None if the dictionary has no rules."""
    if not (dictionary.phrases or dictionary.punctuation or dictionary.words):
        return None
    return ReplacementEngine(dictionary).apply


def default_profiles_path() -> Path:
    from .config import default_config_path

    return default_config_path().parent / "profiles.toml"


def profiles_path(config: Config) -> Path:
    configured = str(config.get("profiles.path"))
    return Path(configured) if configured else default_profiles_path()


def build_profiles(config: Config) -> list[Profile]:
    """Load per-app profiles (empty if disabled or absent)."""
    if not bool(config.get("profiles.enabled")):
        return []
    return load_profiles(profiles_path(config))


def build_profile_resolver(
    profiles: list[Profile], detect: Callable[[], tuple[str, str]]
) -> ProfileFn | None:
    """Return a ``resolve_profile()`` seam, or None if there are no profiles."""
    if not profiles:
        return None

    def resolve() -> ActiveProfile:
        app, title = detect()
        return match_profile(profiles, app, title)

    return resolve


def build_controller_config(
    config: Config, dictionary: Dictionary | None = None
) -> ControllerConfig:
    """Map the persisted config onto the controller's runtime config."""
    language = str(config.get("general.language"))
    prompt = initial_prompt(dictionary) if dictionary is not None else None
    return ControllerConfig(
        mode=Mode(str(config.get("hotkey.mode"))),
        hold_threshold_s=int(config.get("hotkey.hold_threshold_ms")) / 1000.0,
        min_duration_s=int(config.get("hotkey.min_duration_ms")) / 1000.0,
        language=None if language == "auto" else language,
        initial_prompt=prompt,
        auto_submit=bool(config.get("inject.auto_submit")),
        trailing_space=bool(config.get("inject.trailing_space")),
        cleanup_min_chars=int(config.get("cleanup.min_chars")),
    )
