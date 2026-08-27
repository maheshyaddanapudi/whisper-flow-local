"""Menu-bar tray icon (thin pystray seam).

Renders a status icon whose colour reflects the pipeline state (via the tested
``ui.status.badge_for``) and a menu built by the tested ``ui.menu.build_menu``;
menu clicks dispatch through the tested ``ui.menu.perform``. Only the pystray/
Pillow rendering lives here, so it is excluded from coverage and verified on a
real desktop.
"""

from __future__ import annotations

from typing import Any

from ..pipeline_state import State
from .menu import build_menu, perform
from .status import badge_for


def _icon_image(color: str) -> Any:  # pragma: no cover - Pillow rendering
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((12, 12, 52, 52), fill=color)
    return img


class TrayApp:  # pragma: no cover - pystray event loop + native rendering
    """A menu-bar presence for the daemon."""

    def __init__(self, controller: Any, on_quit: Any) -> None:
        self._controller = controller
        self._on_quit = on_quit
        self._icon: Any = None

    def _menu(self) -> Any:
        import pystray

        items = []
        for entry in build_menu(self._controller.state, self._controller.recent()):
            if entry.action == "separator":
                items.append(pystray.Menu.SEPARATOR)
                continue
            items.append(
                pystray.MenuItem(
                    entry.label,
                    (lambda a: lambda *_: perform(self._controller, a, self._on_quit))(
                        entry.action
                    ),
                    enabled=entry.enabled,
                )
            )
        return pystray.Menu(*items)

    def start(self) -> None:
        import pystray

        badge = badge_for(State.IDLE)
        self._icon = pystray.Icon(
            "whisper-flow", _icon_image(badge.color), "whisper-flow", self._menu()
        )
        self._icon.run_detached()

    def on_state_change(self, state: State) -> None:
        if self._icon is not None:
            self._icon.icon = _icon_image(badge_for(state).color)
            self._icon.menu = self._menu()
            self._icon.update_menu()

    def stop(self) -> None:
        if self._icon is not None:
            self._icon.stop()
            self._icon = None
