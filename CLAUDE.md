# CLAUDE.md — orientation for Claude Code sessions in this repo

Living notes for anyone (human or Claude) picking up this project. Kept current
as work proceeds. If you change something structural, update this file.

## What this is

`whisper-flow-local` — a fully local, privacy-first dictation app (an original
take on Wispr Flow / Superwhisper). Press a global hotkey, speak, and cleaned,
punctuated text is inserted at your cursor in any app. **No cloud, no telemetry**:
speech-to-text runs on a local Whisper-family model, and an Ollama-hosted LLM
does the cleanup. Audio stays in RAM and is discarded by default. License: MIT.

## Read these first

- `README.md` — install, first run, CLI commands.
- `docs/PLAN.md` — architecture + module map + phase plan.
- `docs/VERIFICATION.md` — **the honest ledger**: what's tested in CI vs what
  needs a real desktop. Read before trusting any "it works".
- `docs/DECISIONS.md` — dated rationale for every non-obvious choice.
- `docs/RESEARCH.md` / `docs/TRAITS.md` — why the design is what it is (verified
  findings on Wispr Flow + a 256-trait prior-art matrix).
- `docs/CONFIG.md` — generated settings reference (don't hand-edit; run
  `whisper-flow gen-docs`).

## Dev setup

```bash
uv venv && . .venv/bin/activate
uv pip install -e ".[dev]"
```

Hardware extras are optional and only needed to actually dictate (not to test):
`.[dictation]` (numpy/sounddevice/faster-whisper/pynput/webrtcvad),
`.[macos]` (pywhispercpp + pyobjc), `.[ui]` (pystray/Pillow).

## The gate (must stay green)

```bash
ruff check src tests
ruff format --check src tests
mypy
pytest --cov=whisper_flow_local --cov-branch --cov-report=term-missing --cov-fail-under=100
```

CI (`.github/workflows/ci.yml`) runs exactly this on Linux + macOS, py3.11/3.12.
**Coverage is gated at 100%.** ~300 tests today.

## Testing policy (important)

- **100% line+branch coverage on all pure-logic modules**, tested directly.
- **Hardware/network seams are tested against in-memory fakes, never real
  devices.** The mic, hotkeys, clipboard, Ollama, and STT models are reached
  only through narrow interfaces (`AudioSource`, `HotkeyListener`, `Injector`,
  STT backend, an Ollama chat seam). Tests inject fakes; see `tests/fakes.py`
  and the mock Ollama server in `tests/conftest.py`.
- The thin *real* adapters that import device libraries are excluded from the
  coverage denominator (see `[tool.coverage.run] omit` in `pyproject.toml`) with
  justification in `tests/README.md`. Keep logic on the tested side of each seam;
  keep the adapter a trivial pass-through.
- When adding a feature: put the decisions in a pure module + tests, and only the
  device call in an omitted adapter. Never drop coverage below 100%.

## Architecture in one breath

Long-lived daemon owns the models and runs an explicit state machine
(`idle → recording → transcribing → cleaning → injecting`, abort from any state).
A Unix-socket IPC layer exposes verbs (`toggle`, `ptt-down/up`, `cancel`,
`status`, `paste-last[-raw]`) that the `whisper-flow` CLI and Wayland/hotkey
managers drive. `controller.py` orchestrates the pipeline over interfaces;
`build.py` (omitted from coverage) wires the real hardware adapters.

Key rules: cleanup never gates (Ollama down → inject raw); replacements run
before the LLM; clipboard is snapshotted/restored around paste; never press Enter
unless auto-submit is on; copy-only is the always-available injection floor.

Entry points to read code: `cli.py` → `daemon.py` → `controller.py`.

## Config

One schema in `config.py` is the single source of truth (defaults, validation,
docs, CLI help). File: `~/.config/whisper-flow/config.toml`. Any option is
overridable by `WHISPER_FLOW_<SECTION>_<NAME>` (env > file > default). The Ollama
model is `cleanup.model`.

## Running it (needs a real desktop + Ollama)

```bash
ollama pull gemma3:4b
whisper-flow doctor     # self-diagnosis: STT/Ollama/injection/hotkey/permissions
whisper-flow config init
whisper-flow start      # daemon; press the hotkey and speak
```

`doctor` is the troubleshooting entry point — it reports the exact
degradation level (full / copy-only / manual / not-ready) and what's missing.

### macOS permissions (System Settings → Privacy & Security)

Microphone, Input Monitoring (global hotkey), Accessibility (paste into focused
app). Each optional; without Accessibility it degrades to copy-only. Never work
around these — grant them or accept the degraded mode.

## Status (keep this section current)

- **The plan has SIX phases (0–5).** Phases **0–4 are complete**; **Phase 5 is in
  progress** (partially built). Do not describe the project as "all phases done".
- Phases 0–4 + env-var overrides done. ~300 tests, 100% coverage, gate green,
  wheel builds.
- **Verified in CI/headless:** all logic, plus a full assembly of the real
  `build_daemon` with physical devices faked, and the cleanup pass against a real
  mock Ollama HTTP server (incl. kill-mid-flight → raw fallback).
- **NOT yet verified on real hardware (needs a Mac/desktop):** real microphone
  capture, real global hotkey (pynput), real STT latency (faster-whisper /
  whisper.cpp), real paste into a focused app. These are standard libraries doing
  standard things, but "watched it work on a Mac" is still pending.
- **Not built (deliberately deferred):**
  - Menu-bar tray icon + overlay + audio cues (the status *logic* is done and
    tested in `ui/status.py`; only the rendering seam is pending).
  - The streaming mic-RMS → VAD capture wiring and continuous auto-rearm loop
    (the `Endpointer` and `VadCapture` logic are done/tested; the live mic feed
    is the pending seam).
  - Phase 5 differentiators: per-app tone profiles, voice-editing of selected
    text ("make this formal"), correction-learning, streaming partial preview.
  - Mobile (Wispr Flow has iOS/Android; this is desktop-only: macOS/Windows/Linux).

## Gotchas

- Don't put backticks in `git commit -m "..."` bodies — bash command-substitutes
  them. Use `git commit -F <file>` or a heredoc.
- Branch for this work: `claude/whisperflow-local-ollama-egint4`.
- No PR has been opened (do so only when asked).
