"""Recent-dictations history for re-paste.

Kept in memory by default (nothing touches disk unless ``history.persist`` is
enabled — audio never does). Stores both the raw transcript and the cleaned
result so the user can re-paste either. Pure logic; fully tested.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class Dictation:
    """One completed dictation: the raw transcript and the cleaned output."""

    raw: str
    cleaned: str

    @property
    def text(self) -> str:
        """The user-facing result (cleaned if present, else raw)."""
        return self.cleaned or self.raw


class History:
    """Bounded most-recent-first history of dictations."""

    def __init__(self, size: int = 10) -> None:
        self._items: deque[Dictation] = deque(maxlen=size if size > 0 else None)
        self._size = size

    def add(self, raw: str, cleaned: str = "") -> Dictation:
        item = Dictation(raw=raw, cleaned=cleaned)
        if self._size == 0:
            # size 0 disables history entirely
            return item
        self._items.appendleft(item)
        return item

    @property
    def last(self) -> Dictation | None:
        return self._items[0] if self._items else None

    def recent(self, n: int | None = None) -> list[Dictation]:
        items = list(self._items)
        return items[:n] if n is not None else items

    def __len__(self) -> int:
        return len(self._items)

    def clear(self) -> None:
        self._items.clear()
