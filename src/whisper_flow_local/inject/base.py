"""Text injection interface and the ordered fallback chain.

An ``Injector`` puts text into the focused application. The chain tries backends
in order (e.g. clipboard-paste -> keystrokes -> copy-only) and the first that
succeeds wins — so a paste-hostile app or a locked-down machine degrades
gracefully to "text is on your clipboard" rather than failing (hyprvoice +
Handy trait).

Two safety rules encoded here as shared pure logic:
- **Never press Enter** unless the user explicitly enabled auto-submit.
- Optional trailing space is opt-in.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class InjectRequest:
    text: str
    auto_submit: bool = False
    trailing_space: bool = False


@dataclass(frozen=True)
class PreparedText:
    """What a backend should actually emit."""

    text: str
    send_enter: bool


def prepare_text(req: InjectRequest) -> PreparedText:
    """Apply trailing-space and the never-press-Enter-by-default rule."""
    text = req.text
    if req.trailing_space:
        text = text + " "
    return PreparedText(text=text, send_enter=req.auto_submit)


class AllInjectorsFailed(RuntimeError):
    """Raised when every backend in the chain failed or was unavailable."""


@runtime_checkable
class Injector(Protocol):
    name: str

    def available(self) -> bool:
        """Whether this backend can run on this machine right now."""

    def inject(self, req: InjectRequest) -> bool:
        """Attempt injection; return True on success, False to fall through."""


class InjectionChain:
    """Runs an ordered list of injectors, first success wins."""

    def __init__(self, backends: list[Injector]) -> None:
        self._backends = backends

    @property
    def backends(self) -> list[Injector]:
        return list(self._backends)

    def inject(self, req: InjectRequest) -> str:
        """Inject via the first available backend that succeeds.

        Returns the name of the backend used. Raises
        :class:`AllInjectorsFailed` if none worked.
        """
        tried: list[str] = []
        for backend in self._backends:
            if not backend.available():
                continue
            tried.append(backend.name)
            if backend.inject(req):
                return backend.name
        raise AllInjectorsFailed(
            f"no injector succeeded (tried: {', '.join(tried) or 'none available'})"
        )
