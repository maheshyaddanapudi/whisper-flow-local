"""Serial task dispatch off the input-event thread.

OS input callbacks must return fast: macOS disables a CGEventTap whose
callback blocks (roughly a second), and on X11 sending keystrokes from inside
the listener callback that is still processing one can deadlock. Discovered
the hard way by a robot-user E2E — the pipeline (STT + LLM + paste) must never
run on the hotkey listener's thread.

The hotkey adapter therefore captures the event timestamp in the callback and
submits the actual handler here; a single worker thread runs handlers one at a
time, preserving press-before-release order. Handler errors are swallowed so a
failing pipeline can never kill the input listener.
"""

from __future__ import annotations

import contextlib
import queue
import threading
from collections.abc import Callable

_STOP = object()


class SerialDispatcher:
    """Runs submitted callables one at a time on a background thread."""

    def __init__(self) -> None:
        self._tasks: queue.Queue[object] = queue.Queue()
        self._worker: threading.Thread | None = None

    def start(self) -> None:
        if self._worker is None:
            self._worker = threading.Thread(target=self._run, daemon=True)
            self._worker.start()

    def submit(self, task: Callable[[], object]) -> bool:
        """Queue a task; returns False (dropped) when not started or stopped."""
        if self._worker is None:
            return False
        self._tasks.put(task)
        return True

    def stop(self, timeout_s: float = 2.0) -> None:
        """Finish queued tasks and stop the worker (bounded wait)."""
        if self._worker is None:
            return
        self._tasks.put(_STOP)
        self._worker.join(timeout=timeout_s)
        self._worker = None

    def _run(self) -> None:
        while True:
            task = self._tasks.get()
            if task is _STOP:
                return
            # A handler error must not kill the input worker.
            with contextlib.suppress(Exception):
                task()  # type: ignore[operator]
