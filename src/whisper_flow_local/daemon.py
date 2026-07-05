"""The daemon: owns the controller, serves IPC, drives the hotkey listener.

The verb->controller mapping (:func:`make_dispatch`) is pure and tested. The
:class:`Daemon` wires an IPC server to a controller and is covered by starting
it with a fake-backed controller and driving it over a real socket. Building a
daemon with *real* hardware adapters lives in :func:`build_daemon` (a thin seam,
excluded from coverage — it just imports device libraries)."""

from __future__ import annotations

import signal
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .controller import Controller
from .hotkeys.base import HotkeyListener
from .ipc import Dispatch, IPCError, IPCServer


def make_dispatch(controller: Controller) -> Dispatch:
    """Map IPC verbs to controller actions, returning JSON-able dicts."""

    def dispatch(verb: str, args: dict[str, Any]) -> dict[str, Any]:
        if verb == "ping":
            return {"pong": True}
        if verb == "status":
            return controller.status()
        if verb == "log":
            return controller.transparency_recent(int(args.get("n", 10)))
        if verb == "toggle":
            return asdict(
                controller.toggle(
                    clean=bool(args.get("clean", True)),
                    command=bool(args.get("command", False)),
                )
            )
        if verb == "ptt-down":
            return asdict(controller.ptt_down())
        if verb == "ptt-up":
            return asdict(
                controller.ptt_up(
                    clean=bool(args.get("clean", True)),
                    command=bool(args.get("command", False)),
                )
            )
        if verb == "cancel":
            return asdict(controller.cancel())
        if verb == "paste-last":
            return asdict(controller.paste_last())
        if verb == "paste-last-raw":
            return asdict(controller.paste_last(raw=True))
        raise IPCError(f"unknown verb: {verb}")

    return dispatch


class Daemon:
    """Serves IPC for a controller and runs until stopped."""

    def __init__(
        self,
        controller: Controller,
        socket_path: Path,
        *,
        hotkey_listener: HotkeyListener | None = None,
        tray: Any = None,
    ) -> None:
        self._controller = controller
        self._server = IPCServer(socket_path, make_dispatch(controller))
        self._hotkey_listener = hotkey_listener
        self._tray = tray
        self._stop = threading.Event()

    @property
    def controller(self) -> Controller:
        return self._controller

    def attach_tray(self, tray: Any) -> None:
        self._tray = tray

    def start(self) -> None:
        self._server.start()
        if self._hotkey_listener is not None:
            self._hotkey_listener.start()
        if self._tray is not None:
            self._tray.start()

    def stop(self) -> None:
        self._stop.set()
        if self._tray is not None:
            self._tray.stop()
        if self._hotkey_listener is not None:
            self._hotkey_listener.stop()
        self._server.stop()

    def run(self) -> None:  # pragma: no cover - blocks on signals; exercised manually
        self.start()
        signal.signal(signal.SIGINT, lambda *_: self._stop.set())
        signal.signal(signal.SIGTERM, lambda *_: self._stop.set())
        try:
            while not self._stop.is_set():
                self._stop.wait(0.5)
        finally:
            self.stop()
