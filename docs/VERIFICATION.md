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

## Phase 2 — Ollama cleanup ✅

**Automated.** 218 tests, **100% line+branch coverage** on all logic including
the new `cleanup/` package (prompt builder, Ollama chat client, engine). `ruff`,
`ruff format --check`, `mypy` (strict, 32 files) clean. The Ollama chat client
is tested end to end against the in-process mock server (success, server error,
unreachable, missing-content).

**Adversarial cleanup suite** (`test_cleanup_prompts.py`, `test_cleanup_engine.py`):
- The compiled system prompt always carries the guardrail forbidding
  answering/summarizing/translating/adding/removing, for every goal subset and
  is plain-text (no XML angle brackets) — pinned so a future edit can't silently
  drop a guard.
- Adversarial transcripts ("what is two plus two", "summarize…", "translate…",
  "ignore previous instructions…") fed to a mock model that "answers" at length:
  the **growth guard** rejects the expansion and the engine falls back to raw;
  the guardrail prompt is confirmed sent regardless.
- Legitimate heavy shrink (filler removal) is preserved; short inputs may gain
  punctuation within the additive allowance.

**Manual end-to-end (run here)** — real `Daemon` + real IPC + real `CleanupEngine`
talking to a **real (mock) Ollama HTTP server**:
- Cleanup ON: raw `"um so this is like … you know"` → injected
  `"This is the cleaned, punctuated sentence."` (LLM output).
- **Ollama killed mid-flight** (`fail_chat` between record and cleanup): the raw
  transcript is injected — nothing lost. Meets the exit criterion.
- `--raw` flag / `clean=false`: LLM bypassed entirely even with Ollama up
  (verified zero requests reached the server).

**Deferred to the target Mac:** real gemma3:4b latency (exit criterion E2E
≤1.5 s for a 10 s utterance) needs a real Ollama + model; the pipeline wiring,
gating, fallback and prompt contract are all verified here.

## Phase 3 — Dictation quality ✅ (logic) / partially deferred to Phase 4 (rendering)

**Automated.** 260 tests, **100% line+branch coverage** on all logic. `ruff`,
`ruff format --check`, `mypy` (strict, 35 files) clean.

**Delivered and tested (logic):**
- **Personal dictionary** (`dictionary/replacements.py`): TOML load/dump with
  validation, capped vocabulary → Whisper `initial_prompt`, and the layered
  deterministic replacement engine (phrases longest-first → spoken-punctuation
  with leading-space cleanup → word map where `""` deletes), plus space tidying.
  Wired to run **before** the LLM (verified in the controller test) so fixes are
  reliable regardless of cleanup.
- **Quick-add**: `whisper-flow dict add <word>` / `dict show`, dedup + file
  create; tested end to end.
- **Two-layer VAD — layer 1** (`vad.py`): RMS + silence-duration endpointer,
  fully tested (needs speech before firing; resets on new speech; boundary
  cases). Layer 2 (Silero `vad_filter`) is already set in the faster-whisper
  adapter.
- **UI status mapping** (`ui/status.py`): the three visually-distinct states
  (recording/transcribing/cleaning) defined once, tested.
- New config: `[vad]`, `[dictionary]`.

**Deferred to Phase 4 (needs real audio/hardware to wire and verify):**
- The streaming capture loop that feeds live mic RMS to the endpointer for
  auto-stop, and the continuous auto-rearm loop, are daemon-thread integration
  over the real `SoundDeviceSource` — built and verified with the Phase 4
  hardware. The endpointer logic they depend on is done and tested here.
- Tray icon + overlay rendering (pystray/Pillow) and audio cues are thin device
  adapters; the state→badge logic they render is tested here.

## Phase 4 — Cross-platform hardening ✅ (logic + assembly) / device paths deferred to the Mac

**Automated.** 295 tests, **100% line+branch coverage** on all logic. `ruff`,
`ruff format --check`, `mypy` (strict, 39 files) clean.

**Delivered and tested (logic):**
- **VAD/continuous capture loop** (`capture.py`): `record_once` (endpoint /
  stream-end / cancel) and `run_continuous` auto-rearm — the piece deferred from
  Phase 3 — fully tested with fakes + the real `Endpointer`.
- **Model benchmark** (`stt/bench.py`, `whisper-flow bench`): orchestration
  (sort fastest-first, failures last) and table (xRT column, recommendation)
  tested; the CLI command tested with a real WAV + a fake timer.
- **Linux injection** (`inject/linux.py`): session-type detection (Wayland/X11),
  tool preference/selection, and the command injector (argv per tool, Enter
  handling, failure) — all tested with fakes.
- **macOS permission guidance** (`permissions.py`) surfaced in `doctor` on
  Darwin — tested (incl. the `doctor` Darwin path via monkeypatch).
- **whisper.cpp backend** (`stt/whispercpp.py`) implemented for Apple Silicon.
- **Daemon hotkey-listener lifecycle**: start/stop wired and tested with a fake
  listener.

**Manual end-to-end (run here):** the **real `build_daemon`** assembled the full
app (config → STT → injection chain incl. Linux tool detection → controller →
IPC → hotkey-listener construction) with only the physical devices faked, and
drove a dictation over the real socket: `ptt-down` → `recording`, `ptt-up` →
`injected`, history updated. The detected injector chain was
`[clipboard, keystrokes, copy_only]`. `bench` rendered a sorted table with a
recommendation.

**Deferred to the target Mac (needs the hardware):** real microphone capture,
real whisper.cpp/faster-whisper transcription latency, real global hotkey via
pynput, real clipboard paste into a focused app, and the tray/overlay/cues
rendering. The manual check on macOS is: `pipx install
'whisper-flow-local[dictation,macos]'`, `ollama pull gemma3:4b`, grant the three
permissions, `whisper-flow start`, then press the hotkey and speak. Every seam
these exercise is covered by fakes; only the device I/O itself is unverified in
CI.
