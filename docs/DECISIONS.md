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
