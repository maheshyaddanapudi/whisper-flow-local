"""Hotkey listener interface and hotkey-string parsing.

The parser (pure, tested) turns a config string like ``"ctrl+shift+space"`` into
a normalized set of modifiers plus a main key. Backends (pynput/evdev/quartz)
consume that and call back on press/release; those adapters are thin seams.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

_MODIFIERS = {"ctrl", "control", "alt", "option", "shift", "cmd", "command", "super", "win", "fn"}
_MOD_ALIASES = {
    "control": "ctrl",
    "option": "alt",
    "command": "cmd",
    "win": "super",
    "super": "super",
}


class HotkeyParseError(ValueError):
    """Raised for an empty or malformed hotkey string."""


@dataclass(frozen=True)
class Hotkey:
    modifiers: frozenset[str]
    key: str

    def __str__(self) -> str:
        parts = [*sorted(self.modifiers), self.key]
        return "+".join(parts)


def parse_hotkey(spec: str) -> Hotkey:
    """Parse ``"ctrl+shift+space"`` into a :class:`Hotkey`.

    A bare modifier (e.g. ``"cmd"``) is allowed and yields no main key — used
    for bare-modifier push-to-talk (``key == ""``).
    """
    tokens = [t.strip().lower() for t in spec.split("+") if t.strip()]
    if not tokens:
        raise HotkeyParseError(f"empty hotkey: {spec!r}")
    mods: set[str] = set()
    key = ""
    for token in tokens:
        if token in _MODIFIERS:
            mods.add(_MOD_ALIASES.get(token, token))
        elif key:
            raise HotkeyParseError(f"more than one non-modifier key in {spec!r}")
        else:
            key = token
    if not key and not mods:  # pragma: no cover - unreachable given the empty check
        raise HotkeyParseError(f"no keys in {spec!r}")
    return Hotkey(modifiers=frozenset(mods), key=key)


@runtime_checkable
class HotkeyListener(Protocol):
    """Listens for a hotkey and calls press/release callbacks with a timestamp."""

    def start(self) -> None: ...
    def stop(self) -> None: ...
