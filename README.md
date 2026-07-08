# whisper-flow-local

Fully local, privacy-first dictation. Press a global hotkey, speak, and cleaned,
punctuated text appears at your cursor in any app — with **no cloud, no
telemetry**. Speech-to-text runs on a local Whisper-family model; an
Ollama-hosted LLM cleans up the transcript (removes fillers, fixes punctuation).
Audio stays in RAM and is discarded by default.

It's an original, MIT-licensed take on Wispr Flow / Superwhisper. Unlike Wispr
Flow — whose transcription [always happens in the cloud](docs/RESEARCH.md) — this
never sends your voice off the machine.

> **Status: all six phases (0–5) built and tested at 100% coverage.** The full
> hotkey→record→transcribe→**Ollama cleanup**→inject loop, IPC/CLI, injection
> with snapshot/restore, personal dictionary, two-layer VAD, cross-platform
> injection, packaging — plus the Phase 5 differentiators: command/instruction
> mode, per-app tone profiles, transparency log, correction-learning (explicit
> and from-your-last-fix), the menu-bar tray, the streaming-preview coordinator,
> and a **live overlay widget** that shows the transcript and streams the LLM
> cleanup token-by-token while it runs. What remains is **device I/O only** —
> real mic, global hotkey, model inference, paste into a focused app, and the
> tray/overlay/sound *rendering* — which needs a real desktop to verify (the
> logic behind each is tested with fakes). See
> [docs/VERIFICATION.md](docs/VERIFICATION.md) for the exact CI-vs-device line.
> The one intentionally-unbuilt item is silent edit-watching (privacy-hostile);
> `correct --last` is the safe equivalent.

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
whisper-flow --command ptt-up      # command mode: transform the selected text
whisper-flow correct "my sequel" MySQL  # teach a correction (auto-applied after)
whisper-flow log             # show exactly what was sent to the local LLM
```

### Command mode (voice-edit selected text)

Select some text, hold a hotkey bound to `whisper-flow --command ptt-up`, and
say an instruction — "make this formal", "turn into bullet points", "fix the
grammar". The local LLM transforms the selection in place. If nothing's selected
or the model fails, your text is left untouched.

### It learns your corrections

When STT keeps mishearing a term, teach it once:
`whisper-flow correct "my sequel" "MySQL"`. That fix is applied deterministically
to every future dictation — the on-device version of "never the same mistake
twice". Per-app **profiles** (`profiles.toml`) additionally switch tone by app
(casual for Slack, formal for Mail, raw for terminals), and `whisper-flow log`
shows exactly what was sent to the LLM.

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

### Live overlay

When you press the hotkey, a small always-on-top widget appears near the bottom
of the screen. It shows what you said, then streams the LLM's cleanup
**token-by-token** while it refines — so you watch the text tidy itself in real
time — and disappears once the result is inserted. The **Stop** button aborts:
while recording it discards the take; while refining it drops the LLM stream
and injects the raw transcript immediately. It's on by default; turn it off
with `ui.overlay = false`. The window is a plain overlay the running daemon
shows and hides — not a separate app. If tkinter is missing (Homebrew Python:
`brew install python-tk`) the daemon warns and continues without it — the UI
never blocks dictation, and `whisper-flow doctor` reports the gap.

To see the widget on a new machine before setting anything else up:

```bash
python scripts/overlay_demo.py   # scripted data; no mic or Ollama needed
```

### macOS permissions

On macOS the full experience needs three permissions in **System Settings →
Privacy & Security**: **Microphone**, **Input Monitoring** (global hotkey), and
**Accessibility** (paste into other apps). Each is optional — without
Accessibility the app degrades cleanly to copy-only mode. It never works around
these controls.

## Configuration

All settings live in one file (`~/.config/whisper-flow/config.toml`) generated
from a schema. Full reference: [docs/CONFIG.md](docs/CONFIG.md) (auto-generated —
regenerate with `whisper-flow gen-docs`). For example, to point cleanup at a
different Ollama model:

```toml
[cleanup]
model = "gemma2:27b"    # must match a name from `ollama list`
```

**Environment overrides.** Any option can be overridden by an environment
variable named `WHISPER_FLOW_<SECTION>_<NAME>`, which wins over the file and the
default — handy for per-shell tweaks, containers, or secrets:

```bash
WHISPER_FLOW_CLEANUP_MODEL=gemma2:27b whisper-flow start
WHISPER_FLOW_CLEANUP_ENABLED=false whisper-flow toggle   # dictate without cleanup
```

Precedence is **env var > config file > default**. `whisper-flow doctor` reflects
the effective values, so it'll tell you if an env-overridden model isn't pulled.

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
