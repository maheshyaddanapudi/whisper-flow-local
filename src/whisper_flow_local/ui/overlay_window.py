"""Always-on-top overlay window (thin tkinter seam).

Renders the :class:`OverlayView` produced by the tested ``OverlayController`` as
a small borderless, always-on-top widget: a status dot + label, the live
transcript, the streaming refinement, and a Stop button. Only the tkinter
drawing lives here, so it is excluded from coverage and verified on a real
desktop. This is *not* a native ``.app`` bundle — it is a plain overlay window
the running daemon shows and hides.

Threading contract (the part that bites on macOS):

- Tk must be created AND driven on the **main thread**. ``start()`` builds the
  window; :meth:`run` (called by ``Daemon.run`` on the main thread) owns the
  Tk mainloop until the daemon's stop event is set.
- ``render()`` is called from pipeline/IPC/hotkey threads. Tkinter is not
  thread-safe, so it never touches Tk: it just puts the view on a queue that a
  Tk-side ``after`` pump drains. Only the latest view is applied.
- The Stop button dispatches to the coordinator on a worker thread so a
  blocked ``controller.cancel()`` can never freeze the UI event loop.
- If tkinter is missing (Homebrew Python needs ``brew install python-tk``) or
  there is no display, the window marks itself unavailable and every method
  degrades to a no-op — the UI must never gate dictation. ``run`` then simply
  waits on the stop event so the daemon keeps serving.

tkinter ships with CPython, so this needs no extra dependency.
"""

from __future__ import annotations

import queue
import sys
import threading
from typing import Any

from .overlay import OverlayController, OverlayView

_PUMP_MS = 50  # queue-drain cadence; also bounds signal/stop latency


class OverlayWindow:  # pragma: no cover - tkinter rendering + event loop
    """A borderless always-on-top dictation widget backed by tkinter."""

    def __init__(self) -> None:
        self._root: Any = None
        self._status: Any = None
        self._dot: Any = None
        self._transcript: Any = None
        self._refined: Any = None
        self._controller: OverlayController | None = None
        self._views: queue.Queue[OverlayView] = queue.Queue()
        self._available = False

    def bind(self, controller: OverlayController) -> None:
        """Attach the coordinator so the Stop button can call back into it."""
        self._controller = controller

    def start(self) -> None:
        """Build the window; on any failure, degrade to unavailable (no-op)."""
        try:
            self._build()
            self._available = True
        except Exception as exc:  # tkinter missing, no display, Tcl init failure
            self._root = None
            print(
                f"whisper-flow: overlay disabled ({exc}); dictation continues without it. "
                "On macOS with Homebrew Python: brew install python-tk. "
                "Or set ui.overlay=false.",
                file=sys.stderr,
            )

    def _build(self) -> None:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        # Borderless + floating. On macOS (aqua), overrideredirect windows are
        # unreliable (may not draw or take clicks); the native "help" window
        # style is the supported way to get a borderless floating panel.
        if root.tk.call("tk", "windowingsystem") == "aqua":
            try:
                root.tk.call(
                    "::tk::unsupported::MacWindowStyle", "style", str(root), "help", "none"
                )
            except Exception:
                root.overrideredirect(True)
        else:
            root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.configure(bg="#1e1e1e")
        # Anchor to the bottom-centre of the primary screen.
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        w, h = 420, 150
        root.geometry(f"{w}x{h}+{(sw - w) // 2}+{sh - h - 80}")

        header = tk.Frame(root, bg="#1e1e1e")
        header.pack(fill="x", padx=12, pady=(10, 4))
        self._dot = tk.Label(header, text="●", fg="#888888", bg="#1e1e1e", font=("", 14))
        self._dot.pack(side="left")
        self._status = tk.Label(
            header, text="Idle", fg="#dddddd", bg="#1e1e1e", font=("", 12, "bold")
        )
        self._status.pack(side="left", padx=(6, 0))
        tk.Button(
            header,
            text="Stop",
            command=self._stop_clicked,
            bg="#333333",
            fg="#ffffff",
            relief="flat",
        ).pack(side="right")

        self._transcript = tk.Label(
            root, text="", fg="#aaaaaa", bg="#1e1e1e", wraplength=396, justify="left", anchor="w"
        )
        self._transcript.pack(fill="x", padx=12)
        self._refined = tk.Label(
            root, text="", fg="#ffffff", bg="#1e1e1e", wraplength=396, justify="left", anchor="w"
        )
        self._refined.pack(fill="x", padx=12, pady=(4, 10))
        self._root = root

    def _stop_clicked(self) -> None:
        # Off the Tk thread: request_stop may block briefly on the controller
        # lock while an aborted stream winds down; the UI must stay live.
        ctl = self._controller
        if ctl is not None:
            threading.Thread(target=ctl.request_stop, daemon=True).start()

    def render(self, view: OverlayView) -> None:
        """Queue a view for the Tk-side pump. Safe from any thread; never blocks."""
        self._views.put(view)

    def run(self, stop: threading.Event) -> None:
        """Drive the Tk event loop on the calling (main) thread until ``stop``.

        When the window is unavailable this just waits on the event, so the
        daemon's run loop behaves identically with or without a display.
        """
        if self._root is None:
            while not stop.wait(0.5):
                pass
            return

        def pump() -> None:
            if stop.is_set():
                self._root.quit()
                return
            view: OverlayView | None = None
            try:
                while True:  # drain; only the newest view matters
                    view = self._views.get_nowait()
            except queue.Empty:
                pass
            if view is not None:
                self._apply(view)
            self._root.after(_PUMP_MS, pump)

        self._root.after(_PUMP_MS, pump)
        self._root.mainloop()
        self._root.destroy()  # still on the Tk thread — the only safe place
        self._root = None

    def _apply(self, view: OverlayView) -> None:
        if not view.visible:
            self._root.withdraw()
            return
        self._dot.configure(fg=view.color)
        self._status.configure(text=view.status)
        self._transcript.configure(text=view.transcript)
        self._refined.configure(text=view.refined)
        self._root.deiconify()
        self._root.lift()

    def stop(self) -> None:
        """No-op: the pump watches the daemon's stop event and exits itself.

        Tearing Tk down from another thread (where Daemon.stop may run) is
        unsafe; quit/destroy happen at the end of :meth:`run` on the Tk thread.
        """
