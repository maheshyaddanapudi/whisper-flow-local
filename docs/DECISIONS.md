# Engineering decisions log

One dated entry per non-obvious decision, especially where the design docs left
an open question and a short research pass resolved it. Format: question →
findings → choice → sources.

---

## 2026-07-04 — HTTP client for Ollama: stdlib urllib, not httpx

**Question.** PLAN.md/TRAITS.md call for an Ollama client (`/api/tags`,
`/api/chat`). Use a third-party HTTP library (httpx/requests) or the stdlib?

**Findings.** The Ollama REST API is plain JSON over HTTP on localhost. Both
endpoints we need are simple: a GET returning a model list and a POST that
returns a single JSON object (with `stream: false`). `urllib.request` handles
both, including a per-call timeout. Avoiding httpx keeps the *core* package
dependency-free, which is a stated goal (installs anywhere, testable without the
hardware extras). The client is trivially testable against a stdlib
`http.server` fixture (see `tests/conftest.py::mock_ollama`).

**Choice.** stdlib `urllib` in `cleanup/ollama.py`. Non-streaming requests
(`stream=false`) so a single `json.loads` suffices. If streaming partials are
needed later (Phase 5), revisit — `urllib` can stream line-delimited JSON too.

**Sources.** Ollama API docs (`/api/tags`, `/api/chat`) at
https://github.com/ollama/ollama/blob/main/docs/api.md (verify `keep_alive` and
`options.temperature` fields at implementation time in Phase 2).

---

## 2026-07-04 — TOML: read with stdlib tomllib, write with a tiny local serializer

**Question.** Config is TOML. `tomllib` (3.11+) reads TOML but cannot write it;
do we add `tomli-w`?

**Findings.** Our writer only needs to emit scalars, strings and flat string
lists grouped under `[section]` headers, plus `#` comments carrying each
option's description. That is a few lines. Adding a dependency purely to write a
format we already fully control is not worth it for the core package.

**Choice.** Read via `tomllib`; write via `config.dumps()` (local). Kept simple:
strings escaped for `"` and `\`, lists rendered as inline arrays. Revisit only
if nested tables or multiline strings become config values (none planned).

**Sources.** CPython `tomllib` docs (read-only by design).

---

## 2026-07-04 — Coverage policy: 100% on logic, fakes at hardware seams

**Question.** The bar is "100% line coverage target on pure-logic modules;
fakes/mocks for hardware seams." How is that enforced without shipping fake
device drivers?

**Findings.** The pieces that touch real devices (mic via `sounddevice`,
hotkeys via `pynput`, clipboard, STT model load, Ollama socket) are reached only
through narrow interfaces. Logic lives on the testable side; the thin real
adapters are the only untested code and are excluded from the coverage
denominator with a documented rationale (`tests/README.md`). CI runs
`--cov-fail-under=100` so regressions in covered modules fail the build.

**Choice.** Interfaces + in-memory fakes for every seam; real adapters kept
trivial (pure pass-through) and coverage-excluded with justification. The Ollama
client is the exception — it *is* tested end to end against a stdlib mock
server, since HTTP is easy to fake faithfully.

**Sources.** Prior-art pitfall (TRAITS.md): schema/behavior drift and untested
monolith cores. This keeps backend seams clean and swappable.

---

## 2026-07-04 — IPC transport: AF_UNIX socket now, Windows deferred to Phase 4

**Question.** The daemon needs local IPC (CLI verbs, Wayland compositor binds).
Unix socket, TCP loopback, or named pipe?

**Findings.** On macOS/Linux (the Phase 1–3 targets) `AF_UNIX` stream sockets
are ideal: filesystem-scoped, single-instance ownership for free (a second bind
fails), no port allocation. Windows 10+ has partial `AF_UNIX` support but it is
inconsistent across Python builds. Rather than ship a half-working Windows path
now, Phase 1 commits to `AF_UNIX`; the transport is isolated in `ipc.py` behind
`send()`/`IPCServer` so a Windows named-pipe/TCP backend slots in at Phase 4
without touching callers.

**Choice.** `AF_UNIX` + newline-delimited JSON. Single instance enforced by
socket ownership (never by killing processes by name — a BlahST pitfall).

**Sources.** CPython `socket` docs (AF_UNIX availability notes).

---

## 2026-07-04 — Trigger concurrency: one RLock; the toggle "busy" guard is defensive

**Question.** Hotkey and IPC threads both drive the controller. How to prevent
overlapping pipeline runs, and is the `toggle()` "busy" branch reachable?

**Findings.** A single `RLock` serializes every trigger. Because the lock is
held for the whole pipeline run, the only *resting* states another thread can
observe are `idle` and `recording`; the transient states
(`transcribing`/`cleaning`/`injecting`) exist only while the lock is held. So
`toggle()`'s "busy" guard (state is transient) is effectively unreachable via
normal calls — it is defensive. It is unit-tested by driving the state machine
directly, and documented as defensive rather than removed (cheap insurance if
the locking model ever changes).

**Choice.** One `RLock`; `status()` reads state lock-free so it stays
responsive; keep the defensive busy guard with a test.

---

## 2026-07-04 — Clipboard restore: verify the set, bound the restore

**Question.** TRAITS.md says avoid blind sleeps in the paste path and clipboard
restore races. How far can we go?

**Findings.** We *can* verify the clipboard actually holds our text before
sending the paste keystroke (poll with timeout, no blind pre-paste sleep) — this
prevents pasting stale content, the important correctness bug. Restoring the
user's prior clipboard *after* paste genuinely races the target app consuming
the paste, and there is no portable way to observe consumption. So we bound it:
a small, configurable `restore_delay` (injected sleep, a no-op in tests) then
restore. Verified-set is the guarantee; bounded-restore is best-effort and
documented.

**Choice.** Poll-verify before paste; bounded, configurable restore delay after.
Both seams (clipboard, paste, clock, sleep) injected for 100% test coverage.

---

## 2026-07-04 — Cleanup safety: prompt guardrail + output growth guard

**Question.** The cleanup LLM must "clean, never transform meaning". A strict
prompt helps, but small models sometimes still answer a dictated question or
expand the text. Can we defend beyond the prompt without hurting real cleanup?

**Findings.** The dangerous failure is *growth*: the model answers/expands, so
the output is much longer than the input. Legitimate cleanup mostly *shrinks*
(filler removal) or stays similar length — so a lower bound on length would
wrongly reject heavy-filler dictations, but an **upper bound on growth** is
safe. If cleaned length exceeds `max_growth_ratio × len(raw) + allowance`, we
treat it as "the model didn't clean, it responded" and fall back to raw. A small
additive allowance (40 chars) lets short inputs gain punctuation/capitalization
without tripping the guard.

**Choice.** Two layers: (1) the always-present plain-text guardrail in the
system prompt (no XML — small models misread tags); (2) an output growth guard
in the engine (`cleanup.max_growth_ratio`, default 2.5). Deliberately *no* lower
bound — shrink from filler removal is expected and kept. Both are covered by the
adversarial test suite.

**Sources.** TRAITS.md pitfalls (XML prompts misread by small models; "never
transform meaning" contract). API shape from the Ollama `/api/chat` docs.

---

## 2026-07-04 — Raw-vs-cleaned intent: a `clean` flag, not a second pipeline

**Question.** TRAITS.md wants a second hotkey for "raw transcribe" vs
"transcribe + cleanup" (Handy). How to model it without duplicating the pipeline?

**Findings.** The only difference is whether the cleanup stage runs. Threading a
`clean: bool` through the trigger methods (`toggle`/`ptt_up` →
`_stop_and_process`) keeps one pipeline. The daemon exposes it as an IPC arg
(`{"clean": false}`) and the CLI as `--raw`, so a second physical hotkey (bound
to a compositor key or hotkey manager) invokes `whisper-flow --raw ptt-up`. Real
dual-hotkey wiring in-process lands with the real hotkey backend (Phase 4).

**Choice.** `clean` flag on triggers; `--raw` CLI flag; IPC `clean` arg. Default
is clean=true (cleanup is the headline feature).

---

## 2026-07-04 — Dictionary: layered replacement order and where it runs

**Question.** How to order the deterministic replacement layers, and where in
the pipeline do they run relative to the LLM?

**Findings.** nerd-dictation's ordering is the proven one: multi-word phrase
fixes first (so "my sequel" → "MySQL" before any word-level rule touches
"sequel"), then spoken punctuation (consuming the leading space so "hello comma"
→ "hello,"), then the single-word map (empty value = delete a filler). Phrases
must be applied longest-first so "cube it all" beats "cube". These are
*deterministic* fixes for recognition errors and dictated punctuation, so they
must run **before** the LLM cleanup (and their result is what we keep in
history) — otherwise a flaky model could undo them.

**Choice.** ReplacementEngine applies phrases (longest-first) → punctuation →
words → space-tidy, in the controller's `replace` seam, before `cleanup`. Vocab
hints are capped at 20 for `initial_prompt` (overloading degrades STT — a
documented Superwhisper failure).

---

## 2026-07-04 — VAD is two layers; only the endpointer is pure logic

**Question.** "Two-layer VAD default-on" — what is testable now vs hardware?

**Findings.** Layer 1 (end-of-utterance detection for auto-stop/continuous) is a
pure RMS-energy + silence-duration decision — unit-tested in `vad.py`. Layer 2
(scrubbing captured audio to prevent silence hallucinations) is faster-whisper's
built-in Silero `vad_filter=True`, set in the STT adapter. The *streaming* that
feeds layer 1 with live mic levels, and the continuous auto-rearm loop, are
daemon-thread integration over the real audio device — deferred to Phase 4 with
the rest of the hardware wiring, since they can't be meaningfully tested without
a mic. The logic they orchestrate is complete and tested.

**Choice.** Ship and test the endpointer + Silero flag now; wire the streaming
capture/continuous loop in Phase 4 alongside the real `SoundDeviceSource`.

---

## 2026-07-04 — Linux injection: detect at startup, prefer CLI tool, clipboard floor

**Question.** Linux text injection is fragmented (X11 vs Wayland, multiple
tools). How to choose without hard-failing?

**Findings.** Session type is read from `XDG_SESSION_TYPE` / `WAYLAND_DISPLAY` /
`DISPLAY`. Wayland prefers `wtype` then `ydotool`; X11 uses `xdotool`. The
detected tool is inserted into the chain under the "keystrokes" slot so it beats
pynput where present, and the copy-only floor always remains — so even with no
tool installed, a dictation lands on the clipboard. Detection runs at startup so
`doctor` reports the active backend (avoiding the "silent external-binary zoo"
pitfall). The selection/detection logic is pure and tested; only the subprocess
call is a seam.

**Choice.** `detect_session_type` → `select_tool` → `CommandInjector` (thin),
with clipboard/copy-only always behind it.

---

## 2026-07-04 — What Phase 4 verifies in CI vs on the Mac

**Question.** Phase 4 is mostly device I/O. What can honestly be claimed green
from a headless Linux container?

**Findings.** Everything except the actual hardware calls: the real
`build_daemon` assembles the whole graph (config → STT selection → injector
chain with Linux detection → controller → IPC → hotkey-listener construction)
and, with the three physical devices (mic, STT model, clipboard) faked, drives a
full dictation over the real socket. `bench`, Linux tool detection, permission
guidance, and the capture loop are unit-tested. What genuinely cannot be
exercised here — mic capture, model inference latency, a real global hotkey,
pasting into a focused app, tray rendering — is listed explicitly in
VERIFICATION.md with the exact commands to run on macOS.

**Choice.** Claim "logic + assembly verified; device I/O pending on-device",
never "done". The coverage gate (`--cov-fail-under=100`) plus the fakes-at-seams
policy make that split precise rather than hand-wavy.
