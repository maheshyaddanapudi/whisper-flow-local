"""A real GUI 'target app': a tkinter Text box that dumps its content to a file.

Plays the role of the app the user is dictating into. Runs on python3.12
(which has tkinter). Focus is forced so XTEST/pynput/xdotool events land here.
"""

import sys
import tkinter as tk

out_path = sys.argv[1]
seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 60.0

root = tk.Tk()
root.title("victim-editor")
root.geometry("500x200+50+50")
text = tk.Text(root, font=("", 12))
text.pack(fill="both", expand=True)
text.focus_force()


def dump() -> None:
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text.get("1.0", "end-1c"))
    root.after(150, dump)


def bail() -> None:
    root.destroy()


dump()
root.after(int(seconds * 1000), bail)
root.mainloop()
