# Implementation plan: whisper-flow-local

A local Wispr Flow clone: global-hotkey dictation that types polished text into any
app, with all processing on-device — Whisper-family STT + an Ollama-hosted LLM for the
cleanup/formatting pass. Grounded in the findings in [RESEARCH.md](RESEARCH.md).

## Goals

- Hold (or toggle) a global hotkey → speak → release → cleaned, punctuated text appears
  at the cursor in the focused app.
- 100% offline. No audio, transcript, or context ever leaves the machine.
- End-to-end latency target: **≤ 1.5 s** from key release to injected text on mid-range
  hardware (Wispr Flow's cloud pipeline achieves ~700 ms; local clones prove ~1–1.5 s
  feels fine).
- Cleanup stage on **Ollama** with two modes: *cleanup* (fillers, punctuation,
  capitalization, self-corrections) and *instruction* (user-directed transforms).

## Non-goals (v1)

- Streaming transcription while still speaking (hardest gap vs Wispr Flow; revisit in
  Phase 5 via two-tier models or parakeet.cpp streaming).
- Mobile, screenshots-based context awareness, cloud fallback of any kind.

## Stack decision

**Python 3.11+** single package with pluggable backends. Rationale: the entire pipeline
is proven in pure Python (WhisperWriter, Murmur); fastest iteration; every needed
library has first-class Python bindings. A Rust/Tauri rewrite (à la Handy) is a
possible v2 once the pipeline is settled.

| Concern | Choice | Alternative kept pluggable |
|---|---|---|
| Audio capture | `sounddevice` (PortAudio), 16 kHz mono | — |
| VAD | `silero-vad` (also faster-whisper's `vad_filter`) | webrtcvad |
| STT | `faster-whisper` `small.en` (CUDA/CPU) | `pywhispercpp` (whisper.cpp, Metal/CoreML) on macOS; Parakeet later |
| Cleanup LLM | Ollama HTTP API (`/api/chat`), default `qwen2.5:7b` | `llama3.2:3b` / `gemma3:4b` on weak hardware |
| Hotkeys | `pynput` | compositor keybind + CLI trigger on Wayland |
| Text injection | clipboard-paste with clipboard restore | keystroke simulation; per-OS fallback chain |
| Tray/status | `pystray` + minimal overlay | none (CLI mode) |
| Config | `config.yaml` + personal dictionary files | — |

## Architecture

Pipeline state machine (borrowed from Hyprvoice):
`idle → recording → transcribing → cleaning (optional) → injecting → idle`

```
whisper_flow_local/
├── app.py               # orchestrator: state machine, wiring, tray
├── config.py            # YAML config load/validate, defaults
├── hotkeys.py           # pynput listener: hold-to-talk & toggle modes
├── audio.py             # sounddevice capture ring buffer, 16 kHz mono
├── vad.py               # silero-vad: auto-stop on silence (configurable, ~2 s)
├── stt/
│   ├── base.py          # TranscriberBackend protocol
│   ├── fasterwhisper.py # default backend (vad_filter, initial_prompt w/ dictionary)
│   └── whispercpp.py    # macOS/Metal backend (Phase 4)
├── cleanup/
│   ├── ollama.py        # /api/chat client, keep_alive, timeout→raw-text fallback
│   ├── prompts.py       # cleanup & instruction system prompts, per-app profiles
│   └── replace.py       # personal dictionary: literal pairs + regex rules
├── inject/
│   ├── base.py          # Injector protocol + fallback-chain runner
│   ├── clipboard.py     # paste w/ save & restore of prior clipboard
│   ├── keystrokes.py    # pynput typing fallback
│   └── linux.py         # xdotool (X11) / wtype→ydotool (Wayland) chain
└── ui/
    └── tray.py          # status: idle / listening / processing
```

Key design rules learned from prior art:

- **LLM failure must never eat a dictation**: on Ollama timeout/error, inject the raw
  transcript. Cleanup is an enhancement, not a gate.
- **Skip cleanup for short utterances** (< ~50 chars, configurable) — latency guard
  proven by local-whisper.
- **Personal dictionary feeds both stages**: keywords go into Whisper's
  `initial_prompt` *and* the LLM system prompt; literal/regex replacements run after.
- **Clipboard restore always**: never clobber what the user had copied.
- **Warm starts**: preload the STT model at launch; use Ollama `keep_alive` so the
  cleanup model stays resident.

### Cleanup prompt (v1 sketch)

```
System: You clean up dictated speech. Fix punctuation, capitalization, and obvious
homophone errors. Remove filler words (um, uh, like, you know). Apply the speaker's
self-corrections ("no wait, make that X" → X). Format numbered/bulleted lists when
dictated. NEVER add, answer, summarize, or omit content. Output only the cleaned text.
User: <raw transcript>
```

Temperature 0, no streaming needed (we inject once at the end).

## Phases

**Phase 0 — Scaffold** ✅-able immediately
Package layout above, `pyproject.toml`, `config.yaml` defaults, README quickstart
(install Ollama, `ollama pull qwen2.5:7b`, model auto-download for STT).

**Phase 1 — Core loop (MVP)**
Hold-hotkey → record → faster-whisper → clipboard-paste inject. No LLM yet.
Exit criterion: dictate into any text field on the dev machine, < 1 s for a sentence.

**Phase 2 — Ollama cleanup**
`cleanup/` module: cleanup mode, short-text skip, timeout fallback, keep_alive,
before/after logging (local only). Exit criterion: fillers/punctuation fixed, E2E
≤ 1.5 s for a 10-second utterance on target hardware.

**Phase 3 — Robustness & UX**
Toggle mode + VAD auto-stop; tray status; personal dictionary (replace rules +
initial_prompt keywords); config hot-reload; graceful device/permission errors.

**Phase 4 — Cross-platform hardening**
Injection fallback chains per OS (X11/Wayland/macOS permissions docs); whisper.cpp
backend for Apple Silicon; packaging (pipx / PyInstaller).

**Phase 5 — Wispr-parity extras (optional)**
Instruction mode ("make this formal") on selected text; per-app tone profiles via
active-window detection; two-tier live preview (tiny model streaming, small.en final);
Parakeet backend for English speed.

## Risks

| Risk | Mitigation |
|---|---|
| Small LLM rewrites meaning or answers instead of cleaning | Strict system prompt, temperature 0, "output only the text", test suite of adversarial transcripts; fallback to raw text |
| Wayland global hotkeys/injection are fragmented | Documented compositor-keybind escape hatch + wtype/ydotool/clipboard chain |
| Latency on CPU-only machines | `small.en`/`base.en` INT8 (8–12× real-time on CPU), 3b-class cleanup model, or cleanup off |
| Whisper hallucinates on silence | Silero VAD filter on by default |
| macOS permissions (mic + accessibility) | First-run checklist in README + explicit permission checks with clear errors |
