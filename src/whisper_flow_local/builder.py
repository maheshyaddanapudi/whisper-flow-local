"""Pure wiring: translate a :class:`Config` into runtime objects.

Kept separate from the daemon so the decisions (which STT backend, how to order
the injection chain, how config maps to :class:`ControllerConfig`) are unit
tested with fakes, while the daemon only supplies real adapters and threads.
"""

from __future__ import annotations

from .cleanup.engine import CleanupEngine
from .cleanup.prompts import CleanupGoals
from .config import Config
from .controller import ControllerConfig
from .inject.base import InjectionChain, Injector
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


def build_cleanup_engine(config: Config) -> CleanupEngine | None:
    """Build the Ollama cleanup engine, or None if cleanup is disabled."""
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
        keep_alive=str(config.get("cleanup.keep_alive")),
        timeout=float(config.get("cleanup.timeout_seconds")),
        max_growth_ratio=float(config.get("cleanup.max_growth_ratio")),
    )


def build_controller_config(config: Config) -> ControllerConfig:
    """Map the persisted config onto the controller's runtime config."""
    language = str(config.get("general.language"))
    return ControllerConfig(
        mode=Mode(str(config.get("hotkey.mode"))),
        hold_threshold_s=int(config.get("hotkey.hold_threshold_ms")) / 1000.0,
        min_duration_s=int(config.get("hotkey.min_duration_ms")) / 1000.0,
        language=None if language == "auto" else language,
        initial_prompt=None,
        auto_submit=bool(config.get("inject.auto_submit")),
        trailing_space=bool(config.get("inject.trailing_space")),
        cleanup_min_chars=int(config.get("cleanup.min_chars")),
    )
