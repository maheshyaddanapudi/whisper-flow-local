# Implementation plan: whisper-flow-local

An **original**, fully local Wispr Flow-style dictation app: global-hotkey dictation
that types polished text into any app, all processing on-device — Whisper-family STT +
an Ollama-hosted LLM cleanup pass. Every design choice below is grounded in the
verified findings ([RESEARCH.md](RESEARCH.md)) and the 256-trait prior-art matrix
([TRAITS.md](TRAITS.md)).

**Build-our-own stance.** We adopt *traits* from prior art, never code. This keeps the
design free to combine the best of twelve projects and keeps us license-clean of the
GPL-3 ones (VoiceInk, WhisperWriter, nerd-dictation). Our license: MIT.

## Goals

- Tap-or-hold a global hotkey → speak → release → cleaned, punctuated text appears at
  the cursor in the focused app.
- 100% local, verifiably: no cloud code paths, zero telemetry, audio in RAM and
  discarded by default. (Verified: Wispr Flow cannot offer this — transcription always
  happens in their cloud.)
- Latency ≤ 1.5 s from key release on mid-range hardware (Wispr's verified cloud budget
  is ~700 ms; local prior art proves ~1–1.5 s feels fine). On strong hardware (e.g.
  Apple Silicon M3 + whisper.cpp Metal + a warm 4B Ollama model) expect ~1 s or less.
- Ollama cleanup **first-class and on by default** — the gap no existing project fills.

## Non-goals (v1)

Streaming-while-speaking preview, screen-content capture, correction-learning loop,
voice editing of selected text — all deliberately Phase 5+ (they're our differentiation
roadmap, not MVP).

## Stack

**Python 3.11+** daemon + thin CLI. The full pipeline is proven in pure Python
(WhisperWriter, Murmur); fastest iteration; every dependency has first-class bindings.

| Concern | Choice | Notes |
|---|---|---|
| Audio | `sounddevice`, 16 kHz mono ring buffer | RAM-only by default; 5-min safety cap |
| VAD | webrtcvad/RMS endpointing + Silero (`vad_filter=True`) | two layers, default-on |
| STT | `STTBackend` interface: **faster-whisper** default; **pywhispercpp** (Metal/CoreML) on macOS | temperature 0, `condition_on_previous_text=False`; model resident with unload timeout |
| Cleanup | Ollama `/api/chat`, default **gemma3:4b**-class, `keep_alive` | warn below ~3B; user's installed models listed via `/api/tags` |
| Hotkeys | pluggable: pynput default, evdev (Linux), Quartz tap (macOS bare modifiers) | plus IPC verbs for compositor binds |
| Injection | `Injector` chain: clipboard-paste (snapshot/restore, layout-aware) → char-typing → copy-only | never simulates Enter unless Auto-Submit opted in |
| UI | `pystray` tray + tiny overlay (3 states) + audio cues | headless `--no-ui` mode |
| Config | schema-driven TOML at `~/.config/whisper-flow/` | schema generates CLI help, settings UI, docs |

## Architecture

Daemon with an explicit state machine (abort paths from every state):

```
idle → recording → transcribing → cleaning (optional) → injecting → idle
```

```
whisper_flow_local/
├── daemon.py          # state machine, single-instance socket, orchestration
├── ipc.py             # Unix-socket/named-pipe verbs: toggle|ptt-down|ptt-up|cancel|
│                      #   status|paste-last|paste-last-raw ; `whisper-flow` CLI wraps it
├── config.py          # one schema module: type/default/options/description per setting
├── hotkeys/           # pynput | evdev | quartz backends; hybrid tap/hold semantics
├── audio.py           # ring buffer, device picker, cues, media auto-pause (optional)
├── vad.py             # endpointing layer + Silero scrub
├── stt/               # base.py, fasterwhisper.py, whispercpp.py, bench.py
├── cleanup/           # ollama.py, prompts.py (boolean goals→prompt), gate (50 chars)
├── dictionary/        # vocab hints (≤20 → initial_prompt) + layered replacements
├── inject/            # base chain runner, clipboard.py, keystrokes.py, linux.py
├── profiles.py        # per-app match rules → prompt/replacements/injection overrides
├── history.py         # last-N dictations (raw + cleaned), re-paste; opt-in persistence
└── ui/                # tray, overlay, notifications
```

Key rules (each traceable to TRAITS.md):

- **Cleanup is never a gate**: Ollama timeout/error → inject the raw transcript.
- **Skip cleanup under ~50 chars** (configurable).
- **Deterministic replacements run before the LLM**, so dictionary fixes are reliable.
- **Raw and cleaned are both kept**; separate paste-last-raw / paste-last-enhanced.
- **Clipboard is always snapshotted and restored**; paste keycode resolved from the
  active keyboard layout; no blind sleeps — verify clipboard ownership before firing.
- **Never press Enter** unless the user opts into Auto-Submit.
- **Record-start app detection** (not after STT) drives per-app profiles; terminals and
  editors get no-auto-capitalization.
- **Models stay warm**: STT resident in the daemon with configurable unload; Ollama
  `keep_alive` pinned.

### Cleanup prompt (compiled from boolean goals)

Goals (each a config toggle): punctuation, grammar, filler removal, stutter/self-
correction collapse, list formatting. Compiled into a short plain-text prompt — no XML
tags (small models misread them):

```
You clean up dictated speech. Fix punctuation and capitalization. Remove filler
words (um, uh, like, you know). Apply self-corrections ("no wait, X" → X). Format
dictated lists. Never add, answer, summarize, or omit content. Output only the
cleaned text.
```

Temperature 0. User-overridable template with `${output}` placeholder; per-app profiles
may swap the prompt (casual for chat, formal for email).

## Locked-down machines (e.g. corporate MDM)

First-class **copy-only mode**: the pipeline ends at the clipboard (no Accessibility
permission needed on macOS; user pastes with Cmd+V), and the tray/menu icon can start
recording if even Input Monitoring is restricted. The injector chain's final fallback is
this mode, and the first-run dependency report says exactly which level the machine
supports. No workarounds of corporate controls — degrade gracefully instead.

## Phases

**Phase 0 — Scaffold.** Package layout, schema-driven config, `pyproject.toml`, README
quickstart (`uvx whisper-flow-local`; auto-download small STT model; detect Ollama and
list installed models). First-run dependency report.

**Phase 1 — Core loop (MVP).** Daemon + state machine + IPC verbs; hybrid hotkey
(tap-toggle / hold-PTT, 0.5 s discriminator, ~150 ms discard, release grace);
record → faster-whisper → clipboard-paste inject with snapshot/restore.
*Exit: dictate into any app; <1 s for a sentence; cancel works from every state.*

**Phase 2 — Ollama cleanup.** Boolean-goals prompt builder; 50-char gate; timeout →
raw fallback; keep_alive; raw+cleaned history with paste-last-raw/enhanced; second
hotkey for raw-vs-cleaned intent.
*Exit: fillers/punctuation fixed; E2E ≤1.5 s for a 10 s utterance; unplugging Ollama
mid-flight still injects raw text.*

**Phase 3 — Dictation quality.** Two-layer VAD default-on; continuous mode
(auto-rearm); dictionary (vocab hints + layered replacements + quick-add hotkey);
tray + overlay + cues; recent-dictations re-paste.

**Phase 4 — Cross-platform hardening.** whisper.cpp Metal/CoreML backend for Apple
Silicon; injection chains per OS (X11 xdotool / Wayland wtype→ydotool→clipboard) with
startup detection; macOS permissions onboarding (Microphone, Input Monitoring,
Accessibility — each optional with graceful degradation); packaging (pipx/brew/AUR +
systemd user unit/winget); `whisper-flow bench` model benchmark.

**Phase 5 — Differentiators (the unclaimed gaps).** Per-app tone profiles
(cross-platform — nobody has this); voice editing of selected text ("make this formal");
correction learning (accepted edits → vocabulary/replacements/few-shot examples);
streaming tiny-model preview; transparency log (exactly what was sent to the LLM);
verified injection (focus check, buffer-on-focus-loss).

## Risks

| Risk | Mitigation |
|---|---|
| Small LLM rewrites meaning / answers instead of cleaning | Strict short prompt, temp 0, adversarial transcript test suite, raw-text fallback, both versions kept |
| Wayland fragmentation (hotkeys + injection) | IPC verbs for compositor binds; detected fallback chain; copy-only floor |
| Corporate MDM blocks Accessibility/Input Monitoring | Copy-only mode is first-class, not a hack; ask IT, never bypass |
| CPU-only machines | small.en INT8 (8–12× real-time on CPU), 3–4B cleanup model, or cleanup off |
| Whisper silence hallucinations | Silero VAD default-on + min-duration discard |
| Non-QWERTY layouts garbled by char-typing | Layout-aware keycode resolution; clipboard-paste primary |
| Scope creep (the prior-art disease) | Phases 0–4 ship nothing but the dictation loop; Phase 5 gated on core being solid |
