# Real-device verification scripts (Linux, headless-capable)

These scripts run the coverage-omitted device adapters **for real** using
virtual devices, so "verified" doesn't have to wait for a physical desktop.
They were all run green in the development container; see
`docs/VERIFICATION.md` for the recorded results.

Prereqs (Debian/Ubuntu):

```bash
sudo apt-get install xvfb xdotool xclip espeak-ng libportaudio2 pulseaudio python3-tk
pip install faster-whisper pywhispercpp numpy sounddevice pynput
```

Generate the speech sample once:

```bash
espeak-ng -v en-us -s 145 -w /tmp/speech.wav \
  "Hello, this is a test of the local dictation system. The meeting is moved to noon tomorrow."
```

Then, from the repo root:

| Script | What it proves (all REAL components) |
| --- | --- |
| `real_stt_test.py /tmp/speech.wav` | faster-whisper adapter: model download, inference, warm latency |
| `real_whispercpp_test.py /tmp/speech.wav` | whisper.cpp adapter (the macOS backend, CPU here) |
| `xvfb-run python real_hotkey_test.py` | pynput listener catches a real X11 ctrl+shift+space |
| `real_inject_test.py` (see below) | production injector chain pastes into a real focused app, restores the clipboard, presses no Enter |
| `real_mic_test.py /tmp/speech.wav` | SoundDeviceSource records a PulseAudio virtual mic; capture → whisper |
| `robot_e2e.py` (see below) | hotkey → daemon/IPC → real STT → dictionary fix → streamed cleanup → real paste |

The injection and robot tests need a display, a victim app, and (for the
robot) the WAV:

```bash
Xvfb :99 -screen 0 800x600x24 &
DISPLAY=:99 python3 scripts/verify_linux/victim_app.py /tmp/victim.txt 120 &
DISPLAY=:99 python scripts/verify_linux/real_inject_test.py /tmp/victim.txt
DISPLAY=:99 python scripts/verify_linux/robot_e2e.py /tmp/speech.wav /tmp/victim.txt
```

For `real_mic_test.py`, start PulseAudio with a null sink first:

```bash
pulseaudio -D --exit-idle-time=-1
pactl load-module module-null-sink sink_name=vmic
pactl set-default-sink vmic && pactl set-default-source vmic.monitor
```

What these cannot cover: macOS-specific adapters (pbcopy/pbpaste, the aqua
window style, Metal acceleration, macOS permission prompts) and a physical
microphone. Those remain the on-Mac checklist in `docs/VERIFICATION.md`.
