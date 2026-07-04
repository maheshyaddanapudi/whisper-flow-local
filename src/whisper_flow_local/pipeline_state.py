"""The dictation pipeline state machine.

An explicit, named state machine with abort paths from every active state — so
"cancel" and status reporting are trivial and a stuck pipeline is impossible by
construction. This module is pure logic (no I/O) and is exercised to 100%.

    idle -> recording -> transcribing -> cleaning -> injecting -> idle
                     \\-------- cancel/abort from any active state -------/
"""

from __future__ import annotations

from enum import StrEnum


class State(StrEnum):
    IDLE = "idle"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"
    CLEANING = "cleaning"
    INJECTING = "injecting"


class InvalidTransition(RuntimeError):
    """Raised when an illegal state transition is attempted."""


# Forward transitions only; `cancel()` handles the abort edges uniformly.
_FORWARD: dict[State, frozenset[State]] = {
    State.IDLE: frozenset({State.RECORDING}),
    State.RECORDING: frozenset({State.TRANSCRIBING, State.IDLE}),
    State.TRANSCRIBING: frozenset({State.CLEANING, State.INJECTING, State.IDLE}),
    State.CLEANING: frozenset({State.INJECTING, State.IDLE}),
    State.INJECTING: frozenset({State.IDLE}),
}

_ACTIVE: frozenset[State] = frozenset(
    {State.RECORDING, State.TRANSCRIBING, State.CLEANING, State.INJECTING}
)


class StateMachine:
    """Tracks the current pipeline state and enforces legal transitions."""

    def __init__(self) -> None:
        self._state = State.IDLE

    @property
    def state(self) -> State:
        return self._state

    @property
    def is_active(self) -> bool:
        """True when a dictation is in flight (anything but idle)."""
        return self._state in _ACTIVE

    def can(self, target: State) -> bool:
        return target in _FORWARD[self._state]

    def to(self, target: State) -> None:
        """Advance to ``target`` or raise :class:`InvalidTransition`."""
        if not self.can(target):
            raise InvalidTransition(f"{self._state.value} -> {target.value}")
        self._state = target

    def cancel(self) -> bool:
        """Abort any active state back to idle.

        Returns True if something was actually aborted, False if already idle.
        """
        if self._state == State.IDLE:
            return False
        self._state = State.IDLE
        return True

    def reset(self) -> None:
        """Force back to idle (used on error recovery)."""
        self._state = State.IDLE
