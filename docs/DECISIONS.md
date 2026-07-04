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
