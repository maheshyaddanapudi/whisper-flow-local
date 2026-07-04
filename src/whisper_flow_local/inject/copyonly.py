"""Copy-only injection: the always-available floor of the chain.

Puts the (prepared) text on the clipboard and stops there — the user pastes it
themselves with Cmd/Ctrl+V. Needs no Accessibility/Input-Monitoring permission,
so it works on locked-down corporate machines. It is a first-class fallback, not
a hack: the chain ends here so a dictation is never lost.
"""

from __future__ import annotations

from .base import InjectRequest, prepare_text
from .clipboard import Clipboard


class CopyOnlyInjector:
    name = "copy_only"

    def __init__(self, clipboard: Clipboard) -> None:
        self._clipboard = clipboard

    def available(self) -> bool:
        return True

    def inject(self, req: InjectRequest) -> bool:
        prepared = prepare_text(req)
        if not prepared.text:
            return False
        try:
            self._clipboard.set_text(prepared.text)
        except Exception:
            return False
        return True
