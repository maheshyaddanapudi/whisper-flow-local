# whisper-flow-local

Fully local, privacy-first dictation. Press a global hotkey, speak, and cleaned,
punctuated text appears at your cursor in any app — with **no cloud, no
telemetry**. Speech-to-text runs on a local Whisper-family model; an
Ollama-hosted LLM cleans up the transcript (removes fillers, fixes punctuation).
Audio stays in RAM and is discarded by default.

It's an original, MIT-licensed take on Wispr Flow / Superwhisper. Unlike Wispr
Flow — whose transcription [always happens in the cloud](docs/RESEARCH.md) — this
never sends your voice off the machine.

> **Status: feature-complete for v1, pending on-device verification.** All of the
> logic across Phases 0–4 is built and tested at 100% coverage: the daemon and
> pipeline state machine, the hotkey→record→transcribe→**Ollama cleanup**→inject
> loop, IPC/CLI control verbs, clipboard-paste injection with snapshot/restore,
> the LLM cleanup pass with raw-transcript fallback, the personal dictionary,
> two-layer VAD + continuous capture, cross-platform injection (incl. Wayland/X11
> detection), the `bench` command, macOS permission guidance, and packaging.
> The **device I/O paths** (real mic, global hotkey, whisper.cpp/faster-whisper
> transcription, paste into a focused app, tray) are wired and assembled but need
> a real desktop to verify — see [docs/VERIFICATION.md](docs/VERIFICATION.md) for
> the precise line between what's tested in CI and what to check on the machine.

## Install

Requires Python 3.11+. [Ollama](https://ollama.com) is used for the cleanup pass.

```bash
# Try it without installing (once published):
uvx whisper-flow-local doctor

# Or install with the desktop dictation extras:
pipx install "whisper-flow-local[dictation]"        # Windows / Linux
pipx install "whisper-flow-local[dictation,macos]"  # macOS (adds whisper.cpp Metal)
```

From source:

```bash
git clone https://github.com/maheshyaddanapudi/whisper-flow-local
cd whisper-flow-local
uv venv && . .venv/bin/activate
uv pip install -e ".[dev]"
```

## First run

```bash
# 1. See what your machine supports (STT backend, Ollama, injection, hotkeys):
whisper-flow doctor

# 2. Pull the default cleanup model:
ollama pull gemma3:4b

# 3. Write a config file you can edit:
whisper-flow config init

# 4. Run the daemon (foreground), then press your hotkey and speak:
whisper-flow start
```

### Driving the daemon

The daemon listens on a local socket, so you can trigger it from a hotkey
manager, a Wayland compositor keybind, or a script — not just the built-in
global hotkey:

```bash
whisper-flow toggle          # start, or stop-and-transcribe
whisper-flow ptt-down        # begin push-to-talk (bind to key press)
whisper-flow ptt-up          # end push-to-talk (bind to key release)
whisper-flow cancel          # abort the current dictation
whisper-flow status          # JSON: current state, history size, last text
whisper-flow paste-last      # re-paste the last dictation
whisper-flow paste-last-raw  # re-paste it without cleanup
whisper-flow --raw toggle    # dictate but skip LLM cleanup this time
whisper-flow dict add MySQL  # add a word to your personal dictionary
whisper-flow dict show       # list dictionary vocabulary
```

### Personal dictionary

A single TOML file (`~/.config/whisper-flow/dictionary.toml`) improves accuracy
two ways: **vocabulary hints** (proper nouns/jargon, seeded into the recognizer)
and **deterministic replacements** applied before the LLM — multi-word phrase
fixes, spoken punctuation ("comma" → `,`), and a word map where an empty value
deletes a word. Add vocab fast with `whisper-flow dict add <word>`.

### Cleanup (the Ollama pass)

After transcription, the text goes through a local LLM (default `gemma3:4b` via
Ollama) that removes filler words, fixes punctuation and capitalization, and
applies self-corrections — configurable per goal in `[cleanup]`. It's on by
default and **never blocks a dictation**: if Ollama is down, slow, or the model
"answers" instead of cleaning (caught by a length guard), the raw transcript is
injected instead. Skip it per-utterance with `--raw`, or disable it with
`cleanup.enabled = false`.

`doctor` tells you which mode you get: **full** (hotkey dictation with direct
text injection), **copy-only** (text placed on the clipboard — ideal for
locked-down corporate machines where you can't grant Accessibility), or
**not-ready** (install an STT backend).

### macOS permissions

On macOS the full experience needs three permissions in **System Settings →
Privacy & Security**: **Microphone**, **Input Monitoring** (global hotkey), and
**Accessibility** (paste into other apps). Each is optional — without
Accessibility the app degrades cleanly to copy-only mode. It never works around
these controls.

## Configuration

All settings live in one file (`~/.config/whisper-flow/config.toml`) generated
from a schema. Full reference: [docs/CONFIG.md](docs/CONFIG.md) (auto-generated —
regenerate with `whisper-flow gen-docs`).

## Privacy

- No cloud code paths. STT and cleanup both run on your machine.
- No telemetry, no analytics, no accounts.
- Audio is held in memory and discarded after transcription; history is opt-in.

## Development

```bash
uv pip install -e ".[dev]"
ruff check src tests && ruff format --check src tests
mypy
pytest --cov=whisper_flow_local --cov-branch --cov-report=term-missing
```

Design and rationale: [docs/PLAN.md](docs/PLAN.md),
[docs/TRAITS.md](docs/TRAITS.md), [docs/RESEARCH.md](docs/RESEARCH.md),
[docs/DECISIONS.md](docs/DECISIONS.md).

## License

MIT. We adopt design *traits* from prior art, never code.
