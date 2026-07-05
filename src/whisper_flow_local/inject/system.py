"""Real OS clipboard, paste keystroke, and character typing (thin seams).

Platform clipboard via native tools (pbcopy/pbpaste, wl-copy/xclip, Windows
clip/PowerShell); paste and typing via pynput. All imported/spawned lazily so
the core never depends on them. Verified on the target machines, not in CI.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
from typing import Any

from .base import InjectRequest, prepare_text


class SystemClipboard:
    """Cross-platform clipboard using native command-line tools."""

    def __init__(self) -> None:
        self._system = platform.system()

    def _copy_cmd(self) -> list[str] | None:
        if self._system == "Darwin":
            return ["pbcopy"]
        if self._system == "Windows":
            return ["clip"]
        if shutil.which("wl-copy"):
            return ["wl-copy"]
        if shutil.which("xclip"):
            return ["xclip", "-selection", "clipboard"]
        return None

    def _paste_cmd(self) -> list[str] | None:
        if self._system == "Darwin":
            return ["pbpaste"]
        if self._system == "Windows":
            return ["powershell", "-command", "Get-Clipboard"]
        if shutil.which("wl-paste"):
            return ["wl-paste", "-n"]
        if shutil.which("xclip"):
            return ["xclip", "-selection", "clipboard", "-o"]
        return None

    def get_text(self) -> str:
        cmd = self._paste_cmd()
        if cmd is None:
            return ""
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return result.stdout

    def set_text(self, text: str) -> None:
        cmd = self._copy_cmd()
        if cmd is None:
            raise RuntimeError("no clipboard tool available")
        subprocess.run(cmd, input=text, text=True, check=True)


def make_paster() -> Any:
    """Return a ``paste(send_enter: bool)`` callable using pynput."""
    from pynput.keyboard import Controller, Key

    keyboard = Controller()
    modifier = Key.cmd if platform.system() == "Darwin" else Key.ctrl

    def paste(send_enter: bool) -> None:
        with keyboard.pressed(modifier):
            keyboard.press("v")
            keyboard.release("v")
        if send_enter:
            keyboard.press(Key.enter)
            keyboard.release(Key.enter)

    return paste


def make_selection_reader(clipboard: SystemClipboard) -> Any:
    """Return a ``get_selection() -> str`` that copies the focused selection.

    Sends Cmd/Ctrl+C, waits briefly for the clipboard to update, reads it, then
    restores the prior clipboard. Thin seam (pynput + OS clipboard); verified on
    the target machine.
    """
    import time

    from pynput.keyboard import Controller, Key

    keyboard = Controller()
    modifier = Key.cmd if platform.system() == "Darwin" else Key.ctrl

    def get_selection() -> str:
        saved = clipboard.get_text()
        with keyboard.pressed(modifier):
            keyboard.press("c")
            keyboard.release("c")
        time.sleep(0.1)  # let the app place the selection on the clipboard
        selection = clipboard.get_text()
        if selection == saved:
            return ""  # nothing was selected (clipboard unchanged)
        clipboard.set_text(saved)
        return selection

    return get_selection


class KeystrokeInjector:
    """Types text character-by-character via pynput (paste-hostile-app fallback)."""

    name = "keystrokes"

    def __init__(self, key_delay_s: float = 0.0) -> None:
        self._key_delay_s = key_delay_s
        self._keyboard: Any = None

    def _ensure(self) -> Any:
        if self._keyboard is None:
            from pynput.keyboard import Controller

            self._keyboard = Controller()
        return self._keyboard

    def available(self) -> bool:
        try:
            import pynput  # noqa: F401
        except ImportError:
            return False
        return True

    def inject(self, req: InjectRequest) -> bool:
        from pynput.keyboard import Key

        prepared = prepare_text(req)
        if not prepared.text:
            return False
        keyboard = self._ensure()
        keyboard.type(prepared.text)
        if prepared.send_enter:
            keyboard.press(Key.enter)
            keyboard.release(Key.enter)
        return True
