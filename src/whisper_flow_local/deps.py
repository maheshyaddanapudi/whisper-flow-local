"""Environment / dependency report.

Printed on first run and by ``whisper-flow doctor``. It tells the user exactly
which capabilities are available on this machine — which STT backend, whether
Ollama is reachable and has the configured model, which injection and hotkey
backends were found — and, crucially, which graceful-degradation level applies
(e.g. copy-only on a locked-down corporate machine).

Detection is import-based and never raises: a missing optional dependency is a
reported capability, not a crash.
"""

from __future__ import annotations

import importlib
import importlib.util
import platform
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass

from .cleanup.ollama import has_model, probe
from .config import Config


@dataclass(frozen=True)
class Capability:
    name: str
    available: bool
    detail: str


def _module_present(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):  # pragma: no cover - defensive
        return False


def _stt_capabilities() -> list[Capability]:
    caps: list[Capability] = []
    fw = _module_present("faster_whisper")
    caps.append(
        Capability(
            "STT: faster-whisper",
            fw,
            "default backend (Windows/Linux; CPU-only on macOS)"
            if fw
            else "pip install 'whisper-flow-local[dictation]'",
        )
    )
    wc = _module_present("pywhispercpp")
    caps.append(
        Capability(
            "STT: whisper.cpp",
            wc,
            "macOS Metal/CoreML backend"
            if wc
            else "pip install 'whisper-flow-local[macos]' (recommended on Apple Silicon)",
        )
    )
    return caps


def _injection_capabilities() -> list[Capability]:
    caps: list[Capability] = []
    system = platform.system()
    caps.append(
        Capability(
            "Inject: clipboard",
            True,
            "always available (copy-only fallback)",
        )
    )
    caps.append(
        Capability(
            "Inject: keystrokes (pynput)",
            _module_present("pynput"),
            "types/pastes into the focused app",
        )
    )
    if system == "Linux":
        for tool in ("xdotool", "wtype", "ydotool"):
            path = shutil.which(tool)
            caps.append(
                Capability(
                    f"Inject: {tool}",
                    path is not None,
                    path or f"install {tool} for reliable Linux injection",
                )
            )
    return caps


def _hotkey_capabilities() -> list[Capability]:
    caps = [
        Capability(
            "Hotkey: pynput",
            _module_present("pynput"),
            "global hotkey listener",
        )
    ]
    if platform.system() == "Linux":
        caps.append(
            Capability(
                "Hotkey: evdev",
                _module_present("evdev"),
                "Wayland-friendly listener (or bind a compositor key to the CLI)",
            )
        )
    return caps


def _ui_capabilities(
    importer: Callable[[str], object] = importlib.import_module,
) -> list[Capability]:
    """UI seams: the overlay needs tkinter (a real import test, not find_spec —
    the module can exist while the Tcl/Tk libraries are missing)."""
    try:
        importer("tkinter")
        tk_ok = True
    except Exception:
        tk_ok = False
    hint = (
        "live dictation overlay window"
        if tk_ok
        else "overlay disabled — install python-tk (macOS Homebrew: brew install "
        "python-tk) or set ui.overlay=false"
    )
    return [Capability("UI: overlay (tkinter)", tk_ok, hint)]


def _degradation_level(caps: list[Capability]) -> str:
    by_name = {c.name: c.available for c in caps}
    has_stt = by_name.get("STT: faster-whisper") or by_name.get("STT: whisper.cpp")
    has_inject = by_name.get("Inject: keystrokes (pynput)")
    has_hotkey = by_name.get("Hotkey: pynput") or by_name.get("Hotkey: evdev")
    if not has_stt:
        return "not-ready: no STT backend installed"
    if has_inject and has_hotkey:
        return "full: hotkey dictation with direct text injection"
    if has_hotkey:
        return "copy-only: hotkey dictation, text placed on clipboard (press paste yourself)"
    return "manual: trigger via `whisper-flow toggle`, text placed on clipboard"


def collect(config: Config) -> list[Capability]:
    """Collect all capabilities including live Ollama status."""
    caps: list[Capability] = []
    caps.append(
        Capability(
            "Python",
            True,
            f"{sys.version.split()[0]} on {platform.system()} {platform.machine()}",
        )
    )
    caps.extend(_stt_capabilities())

    host = str(config.get("cleanup.ollama_host"))
    model = str(config.get("cleanup.model"))
    status = probe(host, timeout=2.0)
    if status.reachable:
        model_note = (
            "present" if has_model(status, model) else f"MISSING (run: ollama pull {model})"
        )
        caps.append(
            Capability(
                "Cleanup: Ollama",
                True,
                f"{len(status.models)} model(s) at {host}; '{model}' {model_note}",
            )
        )
    else:
        caps.append(
            Capability(
                "Cleanup: Ollama",
                False,
                f"not reachable at {host} — dictation still works, just without cleanup",
            )
        )
    caps.extend(_injection_capabilities())
    caps.extend(_hotkey_capabilities())
    caps.extend(_ui_capabilities())
    return caps


def render_report(config: Config) -> str:
    """Human-readable dependency report for `doctor` / first run."""
    caps = collect(config)
    width = max(len(c.name) for c in caps)
    lines = ["whisper-flow-local — environment report", ""]
    for cap in caps:
        mark = "OK " if cap.available else "-- "
        lines.append(f"  [{mark}] {cap.name.ljust(width)}  {cap.detail}")
    lines.append("")
    lines.append(f"  Mode available on this machine: {_degradation_level(caps)}")
    return "\n".join(lines)
