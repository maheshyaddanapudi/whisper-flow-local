"""Pure tray-menu structure.

The tray renderer (pystray) is a thin seam; the *structure* of the menu — which
entries exist, their labels given the current state, and which are enabled — is
built here and tested. The renderer walks this list to draw native menu items
and dispatch the actions.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..history import Dictation
from ..pipeline_state import State


@dataclass(frozen=True)
class MenuEntry:
    label: str
    action: str  # "toggle" | "cancel" | "paste-last" | "paste-last-raw" |
    # "quit" | f"paste-history:{index}" | "separator"
    enabled: bool = True


SEPARATOR = MenuEntry(label="", action="separator", enabled=False)


def build_menu(state: State, recent: list[Dictation]) -> list[MenuEntry]:
    """Build the tray menu for the current state and recent dictations."""
    active = state != State.IDLE
    entries: list[MenuEntry] = [
        MenuEntry(
            label="Stop dictation" if state == State.RECORDING else "Start dictation",
            action="toggle",
        ),
        MenuEntry(label="Cancel", action="cancel", enabled=active),
        SEPARATOR,
        MenuEntry(label="Paste last", action="paste-last", enabled=bool(recent)),
        MenuEntry(label="Paste last (raw)", action="paste-last-raw", enabled=bool(recent)),
    ]
    if recent:
        entries.append(SEPARATOR)
        for i, item in enumerate(recent):
            entries.append(MenuEntry(label=_preview(item.text), action=f"paste-history:{i}"))
    entries.append(SEPARATOR)
    entries.append(MenuEntry(label="Quit", action="quit"))
    return entries


def _preview(text: str, width: int = 40) -> str:
    text = " ".join(text.split())
    return text if len(text) <= width else text[: width - 1] + "…"


def perform(controller: object, action: str, on_quit: object) -> None:
    """Execute a menu action against the controller (thin dispatch, tested)."""
    if action == "toggle":
        controller.toggle()  # type: ignore[attr-defined]
    elif action == "cancel":
        controller.cancel()  # type: ignore[attr-defined]
    elif action == "paste-last":
        controller.paste_last()  # type: ignore[attr-defined]
    elif action == "paste-last-raw":
        controller.paste_last(raw=True)  # type: ignore[attr-defined]
    elif action.startswith("paste-history:"):
        controller.paste_history(int(action.split(":", 1)[1]))  # type: ignore[attr-defined]
    elif action == "quit":
        on_quit()  # type: ignore[operator]
    # "separator" and unknown actions are no-ops.
