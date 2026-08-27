"""Clipboard-paste injection with snapshot/restore (the default backend).

Injection strategy, split so the *logic* is testable without a real clipboard:

1. Snapshot the user's current clipboard.
2. Write our text and **poll until the clipboard actually holds it** — no blind
   sleep before pasting, so we never paste stale content (a documented prior-art
   bug).
3. Send the paste keystroke (and Enter only if auto-submit is on).
4. Restore the snapshot.

The ``Clipboard`` and paste-key seams are injected, so ``ClipboardInjector`` is
covered by fakes; the real OS adapters (``SystemClipboard`` + a pynput paste)
are thin.
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Callable
from typing import Protocol, runtime_checkable

from .base import InjectRequest, prepare_text


@runtime_checkable
class Clipboard(Protocol):
    def get_text(self) -> str: ...
    def set_text(self, text: str) -> None: ...


class ClipboardInjector:
    """Paste via clipboard with verified set and snapshot restore."""

    name = "clipboard"

    def __init__(
        self,
        clipboard: Clipboard,
        paste: Callable[[bool], None],
        *,
        available: Callable[[], bool] | None = None,
        timeout_s: float = 2.0,
        poll_interval_s: float = 0.01,
        restore_delay_s: float = 0.05,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._clipboard = clipboard
        # paste(send_enter): emit the paste keystroke, plus Enter if requested.
        self._paste = paste
        self._available = available or (lambda: True)
        self._timeout_s = timeout_s
        self._poll_interval_s = poll_interval_s
        self._restore_delay_s = restore_delay_s
        self._clock = clock
        self._sleep = sleep

    def available(self) -> bool:
        return self._available()

    def inject(self, req: InjectRequest) -> bool:
        prepared = prepare_text(req)
        if not prepared.text:
            return False
        try:
            snapshot = self._clipboard.get_text()
        except Exception:
            return False
        try:
            self._clipboard.set_text(prepared.text)
            if not self._wait_until_holds(prepared.text):
                self._restore(snapshot)
                return False
            self._paste(prepared.send_enter)
            # Give the target app a moment to consume the paste before we put
            # the old clipboard back (bounded; injected sleep is a no-op in tests).
            if self._restore_delay_s > 0:
                self._sleep(self._restore_delay_s)
            self._restore(snapshot)
            return True
        except Exception:
            self._restore(snapshot)
            return False

    def _wait_until_holds(self, text: str) -> bool:
        deadline = self._clock() + self._timeout_s
        while True:
            if self._clipboard.get_text() == text:
                return True
            if self._clock() >= deadline:
                return False
            self._sleep(self._poll_interval_s)

    def _restore(self, snapshot: str) -> None:
        with contextlib.suppress(Exception):
            self._clipboard.set_text(snapshot)
