"""REAL whisper.cpp verification: the WhisperCppBackend adapter with a real model.

This is the backend macOS uses (there with Metal; here CPU — the adapter code
path is identical). Catches API misuse in the never-executed adapter.
"""

import sys
import wave

import numpy as np

sys.path.insert(0, "src")

from whisper_flow_local.audio import AudioBuffer
from whisper_flow_local.stt.whispercpp import WhisperCppBackend

with wave.open(sys.argv[1], "rb") as w:
    rate = w.getframerate()
    frames = w.readframes(w.getnframes())
samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
if rate != 16000:
    target = int(len(samples) * 16000 / rate)
    samples = np.interp(
        np.linspace(0, len(samples) - 1, target), np.arange(len(samples)), samples
    ).astype(np.float32)
buf = AudioBuffer(data=samples.tolist(), sample_rate=16000)

backend = WhisperCppBackend("tiny.en")
result = backend.transcribe(buf, language="en", initial_prompt="whisper flow dictation")
print(f"whisper.cpp transcript: {result.text!r}")
text = result.text.lower()
hits = sum(w in text for w in ("test", "dictation", "meeting", "tomorrow"))
assert hits >= 3, f"unrecognizable ({hits}/4): {result.text!r}"
backend.unload()
print("REAL WHISPER.CPP BACKEND (pywhispercpp): OK")
