"""REAL audio capture verification: SoundDeviceSource against a virtual mic.

PulseAudio provides a null sink whose monitor acts as a recording device; we
play the real espeak speech into the sink while the REAL SoundDeviceSource
records from the monitor — the actual PortAudio capture loop, real callback,
real frame concatenation. Then the captured audio goes through REAL
faster-whisper to prove the whole record->transcribe path with device I/O.
"""

import subprocess
import sys
import time

sys.path.insert(0, "src")

from whisper_flow_local.audio_capture import SoundDeviceSource
from whisper_flow_local.stt.fasterwhisper import FasterWhisperBackend

WAV = sys.argv[1]

source = SoundDeviceSource(sample_rate=16000, device="Monitor")
source.start()
assert source.is_recording
# Speak into the virtual mic (paplay pushes the WAV into the null sink).
subprocess.run(["paplay", WAV], check=True)
time.sleep(0.3)
buf = source.stop()
assert not source.is_recording

print(f"captured: {buf.duration_s:.1f}s @ {buf.sample_rate} Hz, {len(buf.data)} samples")
assert buf.duration_s > 4.0, f"too little audio captured: {buf.duration_s}s"
peak = max(abs(x) for x in buf.data)
assert peak > 0.05, f"captured silence (peak={peak}) — the mic loop is broken"

backend = FasterWhisperBackend("tiny.en", device="cpu", compute_type="int8")
result = backend.transcribe(buf, language="en")
print(f"transcript from REAL capture: {result.text!r}")
text = result.text.lower()
hits = sum(w in text for w in ("test", "dictation", "meeting", "tomorrow"))
assert hits >= 3, f"transcript unrecognizable ({hits}/4 keywords): {result.text!r}"
print("REAL SOUNDDEVICE CAPTURE -> REAL WHISPER: OK")
