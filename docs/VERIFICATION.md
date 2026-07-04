# Verification log

What was actually run and observed at each phase, beyond unit tests. Where a
phase's exit criteria need hardware unavailable in the build environment (mic,
display, Ollama, macOS APIs), that is stated explicitly and the reproducible
checks for the target machine are listed.

Build/CI environment: headless Linux container, Python 3.11, no mic, no display,
no Ollama, no GPU.

---

## Phase 0 — Scaffold ✅

**Automated.** `pytest --cov` → 61 tests pass, **100% line+branch coverage** on
all Phase-0 modules (config, cli, deps, cleanup/ollama). `ruff check`,
`ruff format --check`, and `mypy` (strict) all clean.

**Manual, run in this environment:**
- `whisper-flow --version` → `whisper-flow-local 0.1.0`.
- `whisper-flow config init` → writes a commented `config.toml`; re-run without
  `--force` refuses; with `--force` overwrites. Verified.
- `whisper-flow config show` → prints the effective config as TOML.
- `whisper-flow gen-docs` → regenerates `docs/CONFIG.md` from the schema.
- `whisper-flow doctor` → environment report renders; correctly detects **no STT
  backend**, **Ollama not reachable**, clipboard fallback available, and reports
  `Mode available on this machine: not-ready` (accurate for this container).
- Ollama client + dependency report verified against the in-process mock Ollama
  server (`tests/conftest.py`), including reachable / unreachable / server-error
  / missing-model paths.

**Deferred to the target Mac (cannot verify here):**
- `doctor` output on macOS with Ollama running Gemma and the `[macos]` extra
  installed (expect whisper.cpp OK, Ollama OK with model present, `full` mode).

---

## Phase 1 — Core loop MVP ✅

**Automated.** 177 tests, **100% line+branch coverage** on all logic modules
(state machine, recording resolver, history, IPC protocol + socket transport,
injection chain + clipboard/copy-only, controller orchestration, builder,
daemon dispatch, hotkey parser, CLI). `ruff`, `ruff format --check`, and `mypy`
(strict, 30 files) all clean. Coverage-excluded modules are the thin device
adapters only (audio_capture, fasterwhisper, whispercpp, inject/system,
pynput_listener, build), justified in `tests/README.md`.

**Manual end-to-end (run in this environment)** — a real `Daemon` + real Unix
socket + real `whisper-flow` CLI, with fakes only at the physical seams
(mic/STT/clipboard/paste):
- `ptt-down` → state becomes `recording`.
- `ptt-up` → pipeline runs record → transcribe → **clipboard-paste injection**
  (backend `clipboard`), text delivered.
- **Clipboard snapshot/restore verified**: the user's prior clipboard
  (`USER-CLIPBOARD`) is intact after the paste; exactly one paste keystroke was
  sent; **no Enter** was sent (auto-submit off by default).
- `status` reports `idle`, `history_size: 1`, the last text.
- `paste-last` replays the dictation; `cancel` from idle is a clean `noop`.
- Single-instance guard, stale-socket reclaim, and handler-error reporting all
  verified over the real socket.

**Deferred to the target Mac (cannot verify here — no mic/display/Ollama):**
- Real microphone capture (sounddevice), real faster-whisper transcription
  latency (<1 s/sentence target), real global hotkey (pynput), and real
  clipboard/paste into a focused app. The seams are exercised with fakes; the
  adapters need the hardware. `whisper-flow start` then a hotkey press is the
  manual check on macOS.

## Phase 2 — Ollama cleanup (pending)
## Phase 3 — Dictation quality (pending)
## Phase 4 — Cross-platform hardening (pending)
