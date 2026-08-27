# Packaging & install

The goal is "install → speaking in under two minutes": one command to install,
the small default STT model auto-downloads on first run, and `doctor` reports
what's available.

## PyPI (the floor — works everywhere)

```bash
# Trial, no install:
uvx whisper-flow-local doctor

# Install with desktop dictation:
pipx install "whisper-flow-local[dictation]"          # Windows / Linux
pipx install "whisper-flow-local[dictation,macos]"    # macOS (whisper.cpp Metal)
```

`[dictation]` pulls numpy, sounddevice, faster-whisper, pynput, webrtcvad.
`[macos]` adds pywhispercpp (Metal/CoreML) and pyobjc. `[ui]` adds the tray.

## macOS (Homebrew)

A cask wrapping the pipx install plus the first-run permission prompts is the
intended distribution. Until published, install via pipx as above. On first
run, grant **Microphone**, **Input Monitoring**, and **Accessibility** in System
Settings → Privacy & Security (each optional — see `whisper-flow doctor`).

## Linux (AUR + systemd user service)

Install the package, then enable the daemon as a user service:

```bash
mkdir -p ~/.config/systemd/user
cp packaging/whisper-flow.service ~/.config/systemd/user/
systemctl --user enable --now whisper-flow.service
```

On Wayland, bind a compositor key to the CLI instead of relying on the global
hotkey (the reliable path):

```
# Hyprland example — hold-to-talk:
bind  = SUPER, D, exec, whisper-flow ptt-down
bindr = SUPER, D, exec, whisper-flow ptt-up
```

Install a text-injection tool for your session: `wtype` or `ydotool` (Wayland),
`xdotool` (X11). `whisper-flow doctor` reports which was detected.

## Windows (winget)

pipx install as above; a winget manifest wrapping it is planned. Global hotkey
and paste work via pynput out of the box.

## First run

```bash
ollama pull gemma3:4b      # the default cleanup model
whisper-flow doctor        # what's available on this machine
whisper-flow start         # run the daemon; press your hotkey and speak
```
