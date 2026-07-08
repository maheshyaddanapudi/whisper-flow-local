# Verification log

What was actually run and observed at each phase, beyond unit tests. Where a
phase's exit criteria need hardware unavailable in the build environment (mic,
display, Ollama, macOS APIs), that is stated explicitly and the reproducible
checks for the target machine are listed.

Build/CI environment: headless Linux container, Python 3.11, no mic, no display,
no Ollama, no GPU.

## Phase status (the honest summary)

The plan (`docs/PLAN.md`) has **six phases, 0–5**.

| Phase | Scope | Status |
| --- | --- | --- |
| 0 | Scaffold | ✅ complete |
| 1 | Core loop (hotkey→record→STT→inject) | ✅ complete (device I/O pending on-device) |
| 2 | Ollama cleanup | ✅ complete (real-model latency pending on-device) |
| 3 | Dictation quality (dictionary, VAD) | ✅ logic complete; tray/streaming deferred |
| 4 | Cross-platform hardening | ✅ logic + assembly complete; device I/O pending |
| 5 | Differentiators (command mode, per-app tone, etc.) | 🟢 all 6 built (logic); live-IO/rendering on device |

"Complete" means logic at 100% coverage + assembled. Beyond that, the
device-I/O paths have now been run **for real against virtual devices** (see
"Real-device verification session" below): real STT models (both backends),
real pynput hotkey on X11, real clipboard/keystroke injection into a live
focused app, real PortAudio capture from a virtual mic, the real tkinter
overlay under Xvfb, and a robot-user E2E chaining all of it through the real
daemon. What still needs the physical Mac is the macOS-specific layer only
(pbcopy/cmd+v, aqua window style, Metal speed, permission prompts, tray) and a
physical microphone.

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

---

## Phase 5 — Differentiators 🟢 all 6 built (logic complete)

**Automated.** 444 tests, **100% line+branch coverage**; ruff + strict mypy clean.

**Built and tested (with end-to-end demos against the real mock Ollama where
applicable):**
- **Command / instruction mode** — select text, hold the hotkey, speak an
  instruction ("make this formal"), and the LLM transforms the selection in
  place. `whisper-flow --command ptt-up`. Verified E2E.
- **Per-app tone/formatting profiles** — frontmost app at record-start forces
  cleanup on/off, swaps the cleanup prompt, or overrides auto-submit per app.
- **Transparency log** — in-memory record of exactly what was sent to/returned
  from the LLM; `whisper-flow log`.
- **Correction learning** — both explicit (`correct "misheard" "right"`) and
  from-the-last-dictation (`correct --last "the fixed text"`, which word-diffs
  and learns the substitutions). Verified E2E.
- **Tray menu-bar + status icon + audio cues** — pure menu structure, action
  dispatch, state→icon badge, and cue mapping all tested; pystray/Pillow/sound
  rendering is the thin device seam.
- **Streaming partial-preview coordinator** — the two-tier logic (fast-model
  partials, deduped + error-swallowed, reset between utterances) is tested;
  feeding it live growing audio and rendering the overlay are the device seam.
- **Live overlay widget + streaming refinement** — on the hotkey press the
  daemon enters `recording` and the overlay coordinator (`ui/overlay.py`) shows
  the widget, mirrors the transcript (`on_transcript` seam, fired after STT and
  again after dictionary replacements), then streams the LLM's cleanup
  **token-by-token** (`cleanup.chat_stream` → `CleanupEngine.on_token`) while
  `cleaning`, and hides on `idle`. The **Stop control** aborts: while recording
  it cancels/discards; while refining it aborts the in-flight stream
  (`engine.abort()` → `should_abort` polled between chunks) and the raw
  transcript is injected immediately — refinement never holds the text hostage.
  All tested over a fake surface and a streaming mock Ollama (token emission,
  blank-line/EOF handling, mid-flight failure → raw, abort → raw, stale-abort
  reset).

**Pre-production bug hunt (found + fixed before any desktop run):** an
adversarial re-review of the overlay path caught six defects that unit tests
could not see because they lived in or around the coverage-omitted seams:
(1) the Tk mainloop was never run by the daemon (widget would never draw);
(2) `render()` touched Tk from pipeline threads (unsafe; now a thread-safe
queue drained by a Tk-side pump); (3) nothing fed the transcript pane in the
production wiring (now the `on_transcript` seam); (4) Stop couldn't abort an
in-flight stream (now `engine.abort()`); (5) a failing tray/overlay start
killed the whole daemon (now dropped with a warning — UI never gates
dictation); (6) `doctor` didn't check tkinter (now a `UI: overlay` row with
the `brew install python-tk` hint).

**Manual end-to-end (run here, under Xvfb — a real display server):** the
coverage-omitted `ui/overlay_window.py` was executed for real with tkinter
8.6: window construction, the cross-thread queue pump, show/hide, the Stop
button dispatch, and clean teardown. Then a **full real `Daemon.run()`**
(signal handlers, overlay owning the main thread, real Unix-socket IPC, real
`CleanupEngine` streaming from the mock Ollama) drove a complete dictation —
`toggle` → recording → transcript shown → refinement streamed token-by-token
into the real window → cleaned text injected → SIGTERM shutdown, exit 0. A
screenshot of the widget mid-refinement was captured. The permanent
`tests/test_overlay_window_real.py` re-runs the real-window lifecycle wherever
a display exists (the macOS CI leg runs real Tk) and asserts the graceful
degrade contract where none does. `scripts/overlay_demo.py` shows the widget
with scripted data on any machine — run it first on a new desktop.

---

## Real-device verification session (virtual devices, this container)

The challenge "are you sure you can't verify the device seams before I do?"
turned out to be right: with virtual devices (Xvfb, a PulseAudio null-sink
mic, espeak-synthesized speech, xdotool key events), every non-macOS adapter
was executed **for real**. Scripts committed under `scripts/verify_linux/`.

**All green:**
- **Real STT, both backends.** `FasterWhisperBackend` (tiny.en, CPU int8):
  model downloaded from HF, real inference, warm 1.3 s for 6.4 s audio,
  deterministic at temperature 0. `WhisperCppBackend` (pywhispercpp): same
  audio, correct transcript — this is the exact adapter macOS uses (there with
  Metal). `whisper-flow bench --audio …` rendered a real benchmark table.
- **Real global hotkey.** `PynputHotkeyListener` caught a genuine X11
  ctrl+shift+space press AND release fired by xdotool.
- **Real injection into a real app.** The production chain from
  `_build_injectors` (which correctly auto-detected X11 and selected xdotool)
  pasted into a live, focused tkinter editor via the real clipboard
  (xclip) + real pynput ctrl+v: text landed, the user's prior clipboard was
  restored, **no Enter was sent**. The xdotool keystroke injector verified too.
- **Real audio capture.** `SoundDeviceSource` (PortAudio) recorded 6.8 s from
  a PulseAudio virtual mic while the speech WAV played into it — real stream
  callback, real frame concatenation, device-substring resolution — and real
  Whisper transcribed the captured audio correctly.
- **Robot-user E2E.** All of the above chained: xdotool holds the hotkey →
  real pynput → real Daemon + Unix-socket IPC → speech "recorded" → real
  faster-whisper (which genuinely misheard "noon" as "new") → the **real
  dictionary replacement fixed the real mishearing** → cleanup streamed 16
  tokens over HTTP → real clipboard-paste into the focused editor →
  clipboard restored. `status` over the real socket confirmed idle +
  history=1 with the cleaned text.
- **`doctor` on this machine** reports every row correctly, including the new
  tkinter row flagging this venv's missing tkinter with the brew hint.

**Production bug found by this session (fixed):** the pynput adapter ran the
entire pipeline on pynput's own callback thread. On macOS the OS *disables an
event tap whose callback blocks* (~1 s) — the hotkey would have died after the
first dictation — and pasting keystrokes from inside the blocked listener
thread can deadlock X11 (observed: the robot E2E hung). Fix:
`dispatch.SerialDispatcher` (tested) — callbacks now capture the event
timestamp and hand the handler to a worker thread, preserving press/release
order; a handler error can never kill the input listener.

**Observation, not a bug:** the hotkey's own keystroke reaches the focused app
(the space in ctrl+shift+space inserted a leading space in the victim editor).
Pick a hotkey chord the target apps ignore, or accept the artifact; suppressing
global keys system-wide is deliberately out of scope.

**Could not verify here (environment network policy blocks the downloads):**
a real Ollama server — `ollama.com` and GitHub release binaries return 403
through the proxy. The client speaks Ollama's documented `/api/chat` NDJSON
protocol and is exercised against a protocol-faithful mock (streaming,
blank-line keep-alives, EOF-without-done, mid-flight failure, abort).

**What genuinely remains for the Mac (macOS-specific by nature):**
- macOS adapters: pbcopy/pbpaste clipboard, cmd+v paste into a macOS app, the
  aqua borderless "help" window style, whisper.cpp **Metal** speed, macOS
  permission prompts (mic / Input Monitoring / Accessibility), menu-bar tray.
- A physical microphone and real human speech.
- **Fully automatic edit-watching** (infer corrections by silently monitoring
  everything you retype) is deliberately **not** built: it is keylogger-shaped
  and privacy-hostile. `correct --last` is the safe, explicit equivalent.
