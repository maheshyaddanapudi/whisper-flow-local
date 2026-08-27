"""Pure mapping from pipeline state to a user-facing status badge.

Shared by the tray icon and the overlay so the three visually-distinct states
(recording / transcribing / cleaning) are defined once. The rendering itself
(pystray icon, overlay window) is a thin seam; this label/colour logic is tested.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..pipeline_state import State


@dataclass(frozen=True)
class StatusBadge:
    label: str
    color: str  # hex, for the tray dot / overlay accent
    active: bool  # whether a dictation is in flight


_BADGES: dict[State, StatusBadge] = {
    State.IDLE: StatusBadge("Idle", "#888888", False),
    State.RECORDING: StatusBadge("Recording", "#e53935", True),
    State.TRANSCRIBING: StatusBadge("Transcribing", "#fb8c00", True),
    State.CLEANING: StatusBadge("Cleaning up", "#1e88e5", True),
    State.INJECTING: StatusBadge("Inserting", "#43a047", True),
}


def badge_for(state: State) -> StatusBadge:
    """Return the badge for a pipeline state."""
    return _BADGES[state]
