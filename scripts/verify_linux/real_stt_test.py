"""REAL STT verification: actual faster-whisper model on synthesized speech.

Exercises the coverage-omitted FasterWhisperBackend adapter end to end:
real model download, real inference, VAD filter, initial_prompt param.
"""

import sys
import time
import wave

import numpy as np

sys.path.insert(0, "src")

from whisper_flow_local.audio import AudioBuffer
from whisper_flow_local.stt.fasterwhisper import FasterWhisperBackend


def load_wav_16k(path: str) -> AudioBuffer:
    with wave.open(path, "rb") as w:
        rate = w.getframerate()
        frames = w.readframes(w.getnframes())
    samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if rate != 16000:  # linear resample to Whisper-native 16 kHz
        target = int(len(samples) * 16000 / rate)
        samples = np.interp(
            np.linspace(0, len(samples) - 1, target), np.arange(len(samples)), samples
        ).astype(np.float32)
    return AudioBuffer(data=samples.tolist(), sample_rate=16000)


buf = load_wav_16k(sys.argv[1])
print(f"audio: {buf.duration_s:.1f}s @ {buf.sample_rate} Hz")

backend = FasterWhisperBackend("tiny.en", device="cpu", compute_type="int8")
t0 = time.monotonic()
result = backend.transcribe(buf, language="en", initial_prompt=None)
load_and_first = time.monotonic() - t0

t0 = time.monotonic()
result2 = backend.transcribe(buf, language="en")
warm = time.monotonic() - t0

print(f"transcript: {result.text!r}")
print(f"language:   {result.language}")
print(f"first call (incl. model load): {load_and_first:.1f}s; warm: {warm:.1f}s")

text = result.text.lower()
for expected in ("test", "dictation", "meeting", "noon", "tomorrow"):
    assert expected in text, f"missing {expected!r} in transcript: {result.text!r}"
assert result2.text == result.text  # deterministic at temperature 0
backend.unload()
print("REAL FASTER-WHISPER STT: OK")
