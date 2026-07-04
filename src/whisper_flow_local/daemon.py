"""The daemon: owns the controller, serves IPC, drives the hotkey listener.

The verb->controller mapping (:func:`make_dispatch`) is pure and tested. The
:class:`Daemon` wires an IPC server to a controller and is covered by starting
it with a fake-backed controller and driving it over a real socket. Building a
daemon with *real* hardware adapters lives in :func:`build_daemon` (a thin seam,
excluded from coverage — it just imports device libraries)."""

from __future__ import annotations

import signal
import threading
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .controller import Controller
from .ipc import Dispatch, IPCError, IPCServer
from .pipeline_state import State


def make_dispatch(controller: Controller) -> Dispatch:
    """Map IPC verbs to controller actions, returning JSON-able dicts."""

    def dispatch(verb: str, args: dict[str, Any]) -> dict[str, Any]:
        if verb == "ping":
            return {"pong": True}
        if verb == "status":
            return controller.status()
        if verb == "toggle":
            return asdict(controller.toggle())
        if verb == "ptt-down":
            return asdict(controller.ptt_down())
        if verb == "ptt-up":
            return asdict(controller.ptt_up())
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
        ui_notify: Callable[[State], None] | None = None,
    ) -> None:
        self._controller = controller
        self._server = IPCServer(socket_path, make_dispatch(controller))
        self._ui_notify = ui_notify
        self._stop = threading.Event()

    @property
    def controller(self) -> Controller:
        return self._controller

    def start(self) -> None:
        self._server.start()

    def stop(self) -> None:
        self._stop.set()
        self._server.stop()

    def on_state_change(self, state: State) -> None:  # pragma: no cover - UI seam
        if self._ui_notify is not None:
            self._ui_notify(state)

    def run(self) -> None:  # pragma: no cover - blocks on signals; exercised manually
        self.start()
        signal.signal(signal.SIGINT, lambda *_: self._stop.set())
        signal.signal(signal.SIGTERM, lambda *_: self._stop.set())
        try:
            while not self._stop.is_set():
                self._stop.wait(0.5)
        finally:
            self.stop()
