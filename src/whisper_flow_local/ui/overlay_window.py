"""Always-on-top overlay window (thin tkinter seam).

Renders the :class:`OverlayView` produced by the tested ``OverlayController`` as
a small borderless, always-on-top widget: a status dot + label, the live
transcript, the streaming refinement, and a Stop button. Only the tkinter
drawing lives here, so it is excluded from coverage and verified on a real
desktop. This is *not* a native ``.app`` bundle — it is a plain overlay window
the running daemon shows and hides.

tkinter ships with CPython, so this needs no extra dependency. All widget calls
must happen on the Tk main-loop thread; ``render`` marshals via ``after`` so the
coordinator can call it from the pipeline thread.
"""

from __future__ import annotations

from typing import Any

from .overlay import OverlayController, OverlayView


class OverlayWindow:  # pragma: no cover - tkinter rendering + event loop
    """A borderless always-on-top dictation widget backed by tkinter."""

    def __init__(self) -> None:
        self._root: Any = None
        self._status: Any = None
        self._dot: Any = None
        self._transcript: Any = None
        self._refined: Any = None
        self._controller: OverlayController | None = None

    def bind(self, controller: OverlayController) -> None:
        """Attach the coordinator so the Stop button can call back into it."""
        self._controller = controller

    def start(self) -> None:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        root.overrideredirect(True)  # borderless
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
            header, text="Stop", command=self._stop, bg="#333333", fg="#ffffff", relief="flat"
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

    def _stop(self) -> None:
        if self._controller is not None:
            self._controller.request_stop()

    def render(self, view: OverlayView) -> None:
        """Marshal a view onto the Tk thread and apply it (safe from any thread)."""
        if self._root is None:
            return
        self._root.after(0, lambda: self._apply(view))

    def _apply(self, view: OverlayView) -> None:
        if self._root is None:
            return
        if not view.visible:
            self._root.withdraw()
            return
        self._dot.configure(fg=view.color)
        self._status.configure(text=view.status)
        self._transcript.configure(text=view.transcript)
        self._refined.configure(text=view.refined)
        self._root.deiconify()
        self._root.lift()

    def run(self) -> None:
        if self._root is not None:
            self._root.mainloop()

    def stop(self) -> None:
        if self._root is not None:
            self._root.destroy()
            self._root = None
