"""REAL injection verification against a real focused GUI app.

Uses the PRODUCTION assembly (build.py's _build_injectors + the configured
chain order) — real xclip clipboard, real pynput ctrl+v paste, real xdotool
keystroke injector — against a live tkinter Text window on this display.

Verifies the three non-negotiables:
- text lands in the focused app,
- the user's prior clipboard is restored (snapshot/restore),
- no Enter is pressed (auto-submit off).
"""

import subprocess
import sys
import time

sys.path.insert(0, "src")

from whisper_flow_local.build import _build_injectors
from whisper_flow_local.builder import build_injection_chain
from whisper_flow_local.inject.base import InjectRequest
from whisper_flow_local.inject.system import SystemClipboard

dump = sys.argv[1]


def read_victim() -> str:
    try:
        with open(dump, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


# Wait for the victim window and give it focus like a user's click would.
for _ in range(50):
    r = subprocess.run(
        ["xdotool", "search", "--name", "victim-editor"], capture_output=True, text=True
    )
    if r.stdout.strip():
        wid = r.stdout.strip().splitlines()[0]
        break
    time.sleep(0.2)
else:
    raise SystemExit("victim window never appeared")
subprocess.run(["xdotool", "windowactivate", "--sync", wid], check=False)
subprocess.run(["xdotool", "windowfocus", "--sync", wid], check=True)
time.sleep(0.5)

clipboard = SystemClipboard()
clipboard.set_text("USER-CLIPBOARD-PRECIOUS")  # the user's prior clipboard

injectors = _build_injectors(clipboard)
chain = build_injection_chain(["clipboard", "keystrokes", "copy_only"], injectors)
print("chain:", [b.name for b in chain.backends])

backend = chain.inject(InjectRequest(text="Hello from whisper flow.", auto_submit=False))
print("backend used:", backend)
time.sleep(1.0)

content = read_victim()
print(f"victim app content: {content!r}")
assert "Hello from whisper flow." in content, f"text not injected: {content!r}"
assert "\n" not in content.strip(), f"unexpected Enter pressed: {content!r}"
restored = clipboard.get_text()
assert restored == "USER-CLIPBOARD-PRECIOUS", f"clipboard not restored: {restored!r}"

# Round two: force the keystroke injector (xdotool type) specifically.
ks = injectors["keystrokes"]
print("keystroke injector:", type(ks).__name__)
assert ks.inject(InjectRequest(text=" And typed keystrokes too.", auto_submit=False))
time.sleep(1.0)
content = read_victim()
assert "And typed keystrokes too." in content, f"keystrokes missing: {content!r}"

print("REAL INJECTION (clipboard paste + restore, keystrokes, no-Enter): OK")
