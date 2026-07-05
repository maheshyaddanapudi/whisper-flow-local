"""Fan-out of pipeline state changes to multiple listeners.

The controller takes a single ``on_state_change`` callable; the tray, an overlay,
and logging all want to hear about state changes. This tiny pure primitive lets
build-time wiring register several listeners behind that one callable.
"""

from __future__ import annotations

from collections.abc import Callable

from .pipeline_state import State

Listener = Callable[[State], None]


class StateNotifier:
    """Callable that forwards each state change to all registered listeners."""

    def __init__(self) -> None:
        self._listeners: list[Listener] = []

    def register(self, listener: Listener) -> None:
        self._listeners.append(listener)

    def __call__(self, state: State) -> None:
        for listener in self._listeners:
            listener(state)
