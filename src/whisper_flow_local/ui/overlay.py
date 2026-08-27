"""Live overlay coordinator: what the on-screen dictation widget should show.

On a hotkey press the daemon flips to ``recording`` and a small always-on-top
widget appears; it shows the live partial transcript as you speak, then streams
the LLM's refinement token-by-token while cleaning, and offers a stop control.
When the pipeline returns to idle the widget hides.

All of that *logic* lives here, over a thin :class:`OverlaySurface` seam, so it
is fully tested. The actual window (tkinter, always-on-top, borderless) is the
device seam in ``ui/overlay_window.py`` and is verified on a real desktop.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ..pipeline_state import State
from .status import badge_for


@dataclass(frozen=True)
class OverlayView:
    """The full, immutable picture the surface should render each update."""

    visible: bool
    status: str  # human label, e.g. "Recording"
    color: str  # accent hex from the status badge
    transcript: str  # live partial STT text
    refined: str  # streaming cleanup text so far


class OverlaySurface(Protocol):
    """The thin window seam the coordinator drives."""

    def render(self, view: OverlayView) -> None: ...


# Called when the user hits the widget's stop control (wired to controller.cancel).
# The return value (a DictationResult from cancel) is discarded.
StopFn = Callable[[], object]


class OverlayController:
    """Turns pipeline state + partials + refinement tokens into overlay views."""

    def __init__(self, surface: OverlaySurface, *, on_stop: StopFn | None = None) -> None:
        self._surface = surface
        self._on_stop = on_stop
        self._visible = False
        self._badge = badge_for(State.IDLE)
        self._transcript = ""
        self._refined = ""

    def bind_stop(self, on_stop: StopFn) -> None:
        """Wire the stop control (deferred: the controller is built after us)."""
        self._on_stop = on_stop

    def on_state(self, state: State) -> None:
        """React to a pipeline state change (registered on the StateNotifier)."""
        if state == State.IDLE:
            # Dictation finished/aborted: clear and hide.
            self._visible = False
            self._transcript = ""
            self._refined = ""
        elif state == State.RECORDING:
            # A fresh dictation starts here — reset everything and show.
            self._visible = True
            self._transcript = ""
            self._refined = ""
        elif state == State.CLEANING:
            # Refinement is about to stream in; start it fresh but keep showing.
            self._visible = True
            self._refined = ""
        else:
            self._visible = True
        self._badge = badge_for(state)
        self._render()

    def on_partial(self, text: str) -> None:
        """Update the live partial transcript (from the streaming preview)."""
        self._transcript = text
        self._render()

    def on_token(self, token: str) -> None:
        """Append one streamed refinement token (from the cleanup engine)."""
        self._refined += token
        self._render()

    def request_stop(self) -> None:
        """The widget's stop control was clicked — abort the dictation."""
        if self._on_stop is not None:
            self._on_stop()

    def _render(self) -> None:
        self._surface.render(
            OverlayView(
                visible=self._visible,
                status=self._badge.label,
                color=self._badge.color,
                transcript=self._transcript,
                refined=self._refined,
            )
        )
