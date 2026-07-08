"""REAL hotkey verification: pynput listener + real X11 key events (xdotool).

Exercises the coverage-omitted PynputHotkeyListener: real hotkey parse, real
X11 grab, real press/release detection of ctrl+shift+space.
"""

import subprocess
import sys
import time

sys.path.insert(0, "src")

from whisper_flow_local.hotkeys.base import parse_hotkey
from whisper_flow_local.hotkeys.pynput_listener import PynputHotkeyListener

events = []

hotkey = parse_hotkey("ctrl+shift+space")
listener = PynputHotkeyListener(
    hotkey,
    lambda now: events.append(("press", now)),
    lambda now: events.append(("release", now)),
)
listener.start()
time.sleep(1.0)  # let the X grab settle

# A real key event through the X server, like a finger on a keyboard.
subprocess.run(["xdotool", "keydown", "ctrl+shift+space"], check=True)
time.sleep(0.3)
subprocess.run(["xdotool", "keyup", "ctrl+shift+space"], check=True)
time.sleep(1.0)

listener.stop()

kinds = [k for k, _ in events]
assert "press" in kinds, f"hotkey press not detected: {events}"
assert "release" in kinds, f"hotkey release not detected: {events}"
print(f"events: {kinds}")
print("REAL PYNPUT HOTKEY (ctrl+shift+space via X11): OK")
