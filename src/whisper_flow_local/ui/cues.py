"""Audio cues so push-to-talk works eyes-free.

The controller fires notify hooks ("start", "stop", ...). This maps the ones
worth a sound to cue names and builds the notify dict; the actual sound playback
is a thin per-OS seam. The mapping and wiring are pure and tested.
"""

from __future__ import annotations

import platform
import subprocess
from collections.abc import Callable

# Which pipeline events get an audible cue, and the cue name.
CUES: dict[str, str] = {
    "start": "listening-on",
    "stop": "listening-off",
}


def make_cue_hooks(play: Callable[[str], None]) -> dict[str, Callable[[], None]]:
    """Build notify hooks that play a cue for each cued event."""

    def hook(cue: str) -> Callable[[], None]:
        return lambda: play(cue)

    return {event: hook(cue) for event, cue in CUES.items()}


def system_player() -> Callable[[str], None]:  # pragma: no cover - audio device seam
    """Return a ``play(cue_name)`` that plays a short system sound."""
    system = platform.system()

    def play(cue: str) -> None:
        try:
            if system == "Darwin":
                sound = "Tink" if cue == "listening-on" else "Pop"
                subprocess.Popen(["afplay", f"/System/Library/Sounds/{sound}.aiff"])
            elif system == "Linux":
                subprocess.Popen(["paplay", "/usr/share/sounds/freedesktop/stereo/bell.oga"])
            # Windows: winsound is imported lazily to avoid a hard dependency.
            elif system == "Windows":
                import winsound

                winsound.MessageBeep()  # type: ignore[attr-defined]  # Windows-only
        except Exception:
            pass

    return play
