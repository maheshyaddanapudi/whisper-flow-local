"""Exercise the REAL tkinter overlay window when the environment allows it.

This is the one test that runs the coverage-omitted device seam for real:

- On a machine with tkinter + a display (the macOS CI leg, a dev laptop, or
  Linux under ``xvfb-run``), it builds the actual window, drives a full
  dictation's views through the cross-thread queue pump, and tears down.
- On a headless box (Linux CI without a display) it verifies the degrade
  contract instead: ``start()`` must swallow the failure, warn, and leave every
  method a safe no-op — the UI must never gate dictation.

Either way it is deterministic: it asserts whichever contract applies, so it
cannot flake with the environment. ``overlay_window.py`` stays out of the
coverage denominator; this is a behavioral smoke, not a coverage vehicle.
"""

from __future__ import annotations

import threading
import time

from whisper_flow_local.pipeline_state import State
from whisper_flow_local.ui.overlay import OverlayController
from whisper_flow_local.ui.overlay_window import OverlayWindow


def test_overlay_window_real_or_degraded(capsys) -> None:
    window = OverlayWindow()
    stopped: list[int] = []
    ctl = OverlayController(window)
    ctl.bind_stop(lambda: stopped.append(1))
    window.bind(ctl)

    window.start()  # must NEVER raise, whatever the environment

    if window._root is None:
        # Headless: the degrade contract. Everything is a safe no-op and the
        # user got an actionable warning.
        assert "overlay disabled" in capsys.readouterr().err
        ctl.on_state(State.RECORDING)  # render() -> queue, no Tk touched
        stop = threading.Event()
        stop.set()
        window.run(stop)  # returns promptly instead of running a mainloop
        window.stop()
        return

    # Real display: full lifecycle through the actual Tk pump.
    stop = threading.Event()
    failsafe = threading.Timer(15.0, stop.set)  # never hang CI
    failsafe.start()
    errors: list[BaseException] = []

    def dictation() -> None:
        try:
            time.sleep(0.2)
            ctl.on_state(State.RECORDING)
            ctl.on_partial("um the meeting is at noon")
            time.sleep(0.15)
            ctl.on_state(State.CLEANING)
            for tok in ["The ", "meeting ", "is ", "at ", "noon."]:
                ctl.on_token(tok)
            time.sleep(0.15)
            ctl.on_state(State.IDLE)
            time.sleep(0.2)
            window._stop_clicked()  # the button's code path
            time.sleep(0.3)
        except BaseException as exc:
            errors.append(exc)
        finally:
            stop.set()

    worker = threading.Thread(target=dictation, daemon=True)
    worker.start()
    window.run(stop)  # main thread owns Tk, exactly like Daemon.run
    worker.join(timeout=5)
    failsafe.cancel()

    assert not errors, f"pipeline thread failed against the real window: {errors}"
    assert stopped == [1]  # Stop button dispatched to the coordinator
    assert window._root is None  # torn down on the Tk thread
