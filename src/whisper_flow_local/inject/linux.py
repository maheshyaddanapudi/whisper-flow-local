"""Linux text injection: X11 vs Wayland tool detection and selection.

The *decision* logic — which display server, which tools are installed, what
injector order to use — is pure and tested. The actual injectors shell out to
xdotool / wtype / ydotool and are thin seams. On Wayland the order is
wtype -> ydotool -> (clipboard fallback handled by the chain); on X11, xdotool.
Detection runs at startup so `doctor` can report which backend is active.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Mapping

from .base import InjectRequest, prepare_text

Which = Callable[[str], str | None]


def detect_session_type(env: Mapping[str, str]) -> str:
    """Return 'wayland', 'x11', or 'unknown' from environment variables."""
    session = env.get("XDG_SESSION_TYPE", "").lower()
    if session in ("wayland", "x11"):
        return session
    if env.get("WAYLAND_DISPLAY"):
        return "wayland"
    if env.get("DISPLAY"):
        return "x11"
    return "unknown"


def preferred_tools(session_type: str) -> list[str]:
    """Ordered candidate CLI tools for a session type."""
    if session_type == "wayland":
        return ["wtype", "ydotool"]
    if session_type == "x11":
        return ["xdotool"]
    # Unknown: try everything, X11 first (most common on legacy setups).
    return ["xdotool", "wtype", "ydotool"]


def select_tool(session_type: str, which: Which) -> str | None:
    """First preferred tool that is actually installed, or None."""
    for tool in preferred_tools(session_type):
        if which(tool) is not None:
            return tool
    return None


class CommandInjector:
    """Injects by shelling out to a detected CLI tool (thin seam)."""

    def __init__(self, tool: str, run: Callable[[list[str], str], int] | None = None) -> None:
        self.name = tool
        self._run = run or _default_run

    def available(self) -> bool:
        return True  # constructed only when the tool was detected

    def inject(self, req: InjectRequest) -> bool:
        prepared = prepare_text(req)
        if not prepared.text:
            return False
        argv = _argv_for(self.name, prepared.text)
        if argv is None:  # pragma: no cover - only known tools are constructed
            return False
        code = self._run(argv, prepared.text)
        if code != 0:
            return False
        if prepared.send_enter:
            self._run(_enter_argv(self.name), "")
        return True


def _argv_for(tool: str, text: str) -> list[str] | None:
    if tool == "xdotool":
        return ["xdotool", "type", "--clearmodifiers", text]
    if tool == "wtype":
        return ["wtype", text]
    if tool == "ydotool":
        return ["ydotool", "type", text]
    return None


def _enter_argv(tool: str) -> list[str]:
    if tool == "xdotool":
        return ["xdotool", "key", "Return"]
    if tool == "wtype":
        return ["wtype", "-k", "Return"]
    return ["ydotool", "key", "28:1", "28:0"]  # Linux keycode for Enter


def _default_run(argv: list[str], _text: str) -> int:  # pragma: no cover - subprocess seam
    return subprocess.run(argv, check=False).returncode
