"""Global hotkey listener via pynput (thin seam).

Tracks modifier state and fires press/release callbacks (with a monotonic
timestamp) when the configured combo's main key goes down/up while the required
modifiers are held. The hybrid tap/hold interpretation lives in
``recording.RecordingResolver`` — this only reports raw press/release.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from .base import Hotkey

_MOD_KEYS = {
    "ctrl": {"ctrl", "ctrl_l", "ctrl_r"},
    "alt": {"alt", "alt_l", "alt_r", "alt_gr"},
    "shift": {"shift", "shift_l", "shift_r"},
    "cmd": {"cmd", "cmd_l", "cmd_r"},
    "super": {"cmd", "cmd_l", "cmd_r"},
}


class PynputHotkeyListener:
    def __init__(
        self,
        hotkey: Hotkey,
        on_press: Callable[[float], object],
        on_release: Callable[[float], object],
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._hotkey = hotkey
        self._on_press = on_press
        self._on_release = on_release
        self._clock = clock
        self._held_mods: set[str] = set()
        self._active = False
        self._listener: Any = None

    def _key_name(self, key: Any) -> str:
        from pynput import keyboard

        if isinstance(key, keyboard.KeyCode) and key.char:
            return str(key.char).lower()
        if isinstance(key, keyboard.Key):
            return str(key.name).lower()
        return ""

    def _mods_satisfied(self) -> bool:
        for required in self._hotkey.modifiers:
            aliases = _MOD_KEYS.get(required, {required})
            if not (self._held_mods & aliases):
                return False
        return True

    def _update_mod(self, name: str, pressed: bool) -> None:
        for aliases in _MOD_KEYS.values():
            if name in aliases:
                if pressed:
                    self._held_mods.add(name)
                else:
                    self._held_mods.discard(name)
                return

    def _handle_press(self, key: Any) -> None:
        name = self._key_name(key)
        self._update_mod(name, True)
        if name == self._hotkey.key and self._mods_satisfied() and not self._active:
            self._active = True
            self._on_press(self._clock())

    def _handle_release(self, key: Any) -> None:
        name = self._key_name(key)
        if name == self._hotkey.key and self._active:
            self._active = False
            self._on_release(self._clock())
        self._update_mod(name, False)

    def start(self) -> None:
        from pynput import keyboard

        self._listener = keyboard.Listener(
            on_press=self._handle_press, on_release=self._handle_release
        )
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
