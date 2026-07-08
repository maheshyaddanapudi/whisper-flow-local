"""Show the live dictation overlay with scripted data — no mic/Ollama needed.

Run this FIRST on a new machine to verify the widget renders before wiring up
the whole pipeline:

    python scripts/overlay_demo.py

You should see a small dark widget appear near the bottom of the screen, walk
through Recording -> Transcribing -> Cleaning up (with the refined sentence
streaming in word by word) -> Inserting, then disappear. It loops three times;
the Stop button just prints. Ctrl-C to quit early.
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from whisper_flow_local.pipeline_state import State
from whisper_flow_local.ui.overlay import OverlayController
from whisper_flow_local.ui.overlay_window import OverlayWindow


def main() -> int:
    window = OverlayWindow()
    ctl = OverlayController(window)
    ctl.bind_stop(lambda: print("Stop clicked — in the real app this aborts the dictation"))
    window.bind(ctl)
    window.start()
    if window._root is None:
        print("Overlay could not start on this machine (see the warning above).")
        return 1

    stop = threading.Event()

    def scenario() -> None:
        raw = "um so like the meeting is uh moved to noon tomorrow you know"
        refined = "The meeting is moved to noon tomorrow."
        try:
            for _ in range(3):
                ctl.on_state(State.RECORDING)
                partial = ""
                for word in raw.split(" "):
                    partial = (partial + " " + word).strip()
                    ctl.on_partial(partial)
                    time.sleep(0.15)
                ctl.on_state(State.TRANSCRIBING)
                time.sleep(0.6)
                ctl.on_state(State.CLEANING)
                for word in refined.split(" "):
                    ctl.on_token(word + " ")
                    time.sleep(0.12)
                ctl.on_state(State.INJECTING)
                time.sleep(0.4)
                ctl.on_state(State.IDLE)
                time.sleep(1.2)
        finally:
            stop.set()

    threading.Thread(target=scenario, daemon=True).start()
    window.run(stop)  # Tk owns this (main) thread, as in the real daemon
    print("Overlay demo finished.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
