"""ROBOT-USER E2E: the whole pipeline with real components, no human.

  real X11 hotkey (xdotool ctrl+shift+space, held)   [real pynput listener]
    -> real Daemon + real Unix-socket IPC
    -> audio source carrying REAL synthesized speech (espeak WAV)
    -> REAL faster-whisper (tiny.en) transcription
    -> REAL dictionary replacement fixing the model's actual mishearing
    -> streaming LLM cleanup over HTTP (mock Ollama, token-by-token)
    -> REAL clipboard-paste injection into a REAL focused tkinter app
       (snapshot/restore verified, no Enter)

Only three things are not real here: the microphone driver (the WAV stands in
for the mic), the LLM weights (mock Ollama), and macOS-specific adapters.
"""

import json
import subprocess
import sys
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import numpy as np

sys.path.insert(0, "src")

from whisper_flow_local.audio import AudioBuffer
from whisper_flow_local.build import _build_injectors
from whisper_flow_local.builder import build_injection_chain
from whisper_flow_local.cleanup.engine import CleanupEngine
from whisper_flow_local.cleanup.prompts import CleanupGoals
from whisper_flow_local.controller import Controller, ControllerConfig, _Deps
from whisper_flow_local.daemon import Daemon
from whisper_flow_local.dictionary.replacements import Dictionary, ReplacementEngine
from whisper_flow_local.history import History
from whisper_flow_local.hotkeys.base import parse_hotkey
from whisper_flow_local.hotkeys.pynput_listener import PynputHotkeyListener
from whisper_flow_local.inject.system import SystemClipboard
from whisper_flow_local.ipc import send
from whisper_flow_local.recording import Mode
from whisper_flow_local.stt.fasterwhisper import FasterWhisperBackend

WAV = sys.argv[1]
DUMP = sys.argv[2]
CLEANED = "This is a test of the local dictation system. The meeting is moved to noon tomorrow."

# --- mock Ollama that streams ----------------------------------------------------
tokens_streamed = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.end_headers()
        toks = CLEANED.split(" ")
        for i, tok in enumerate(toks):
            chunk = tok if i == len(toks) - 1 else tok + " "
            self.wfile.write(
                (json.dumps({"message": {"content": chunk}, "done": False}) + "\n").encode()
            )
        self.wfile.write((json.dumps({"message": {"content": ""}, "done": True}) + "\n").encode())


ollama = HTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=ollama.serve_forever, daemon=True).start()

# --- an AudioSource that "records" the real speech WAV ---------------------------


class WavMicSource:
    """Stands in for the mic driver; everything downstream is real."""

    def __init__(self, path: str) -> None:
        with wave.open(path, "rb") as w:
            rate = w.getframerate()
            frames = w.readframes(w.getnframes())
        samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        if rate != 16000:
            target = int(len(samples) * 16000 / rate)
            samples = np.interp(
                np.linspace(0, len(samples) - 1, target), np.arange(len(samples)), samples
            ).astype(np.float32)
        self._data = samples.tolist()
        self._recording = False

    def start(self) -> None:
        self._recording = True

    def stop(self) -> AudioBuffer:
        self._recording = False
        return AudioBuffer(data=self._data, sample_rate=16000)

    @property
    def is_recording(self) -> bool:
        return self._recording


# --- focus the victim app --------------------------------------------------------
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
subprocess.run(["xdotool", "windowfocus", "--sync", wid], check=True)
time.sleep(0.3)

# --- assemble with REAL components (mirrors build_daemon) -------------------------
clipboard = SystemClipboard()
clipboard.set_text("USER-CLIPBOARD-PRECIOUS")
chain = build_injection_chain(["clipboard", "keystrokes", "copy_only"], _build_injectors(clipboard))

# The correction the user would teach after tiny.en misheard "noon" as "new":
#   whisper-flow correct "moved to new tomorrow" "moved to noon tomorrow"
dictionary = Dictionary(phrases=(("moved to new tomorrow", "moved to noon tomorrow"),))
replace = ReplacementEngine(dictionary).apply

engine = CleanupEngine(
    host=f"http://127.0.0.1:{ollama.server_address[1]}",
    model="gemma3:4b",
    goals=CleanupGoals(),
    on_token=tokens_streamed.append,
)

deps = _Deps(
    audio=WavMicSource(WAV),
    stt=FasterWhisperBackend("tiny.en", device="cpu", compute_type="int8"),
    injection=chain,
    history=History(size=5),
    cleanup=engine.clean,
    replace=replace,
)
controller = Controller(
    ControllerConfig(mode=Mode.HYBRID, hold_threshold_s=0.5, min_duration_s=0.15), deps
)
listener = PynputHotkeyListener(
    parse_hotkey("ctrl+shift+space"), controller.on_hotkey_press, controller.on_hotkey_release
)
sock = Path("/tmp/wf-robot.sock")
daemon = Daemon(controller, sock, hotkey_listener=listener)
daemon.start()
time.sleep(1.0)  # let the X grab settle

print("daemon up:", send(sock, "status")["data"])

# --- the robot user presses and holds the hotkey, speaks, releases ---------------
subprocess.run(["xdotool", "keydown", "ctrl+shift+space"], check=True)
time.sleep(1.0)  # "speaking" (hold > 0.5s threshold -> push-to-talk)
subprocess.run(["xdotool", "keyup", "ctrl+shift+space"], check=True)

# Release triggers: real whisper -> replace -> streaming cleanup -> real paste.
deadline = time.monotonic() + 120
while time.monotonic() < deadline:
    status = send(sock, "status")["data"]
    if status["history_size"] >= 1 and status["state"] == "idle":
        break
    time.sleep(0.5)
else:
    raise SystemExit(f"pipeline never completed: {send(sock, 'status')['data']}")

print("final status:", status)
time.sleep(1.5)  # let the victim app's dump catch up
daemon.stop()

content = Path(DUMP).read_text(encoding="utf-8")
print(f"victim received: {content!r}")
print(f"streamed tokens: {len(tokens_streamed)}")

assert CLEANED in content, f"cleaned text not injected: {content!r}"
assert "\n" not in content.strip(), f"unexpected Enter: {content!r}"
assert len(tokens_streamed) >= 5, "cleanup did not stream token-by-token"
restored = clipboard.get_text()
assert restored == "USER-CLIPBOARD-PRECIOUS", f"clipboard not restored: {restored!r}"
assert status["last_text"] == CLEANED
print()
print("ROBOT-USER E2E: OK — hotkey -> real STT -> dictionary fix -> streamed cleanup -> real paste")
