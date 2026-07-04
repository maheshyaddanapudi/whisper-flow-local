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

## Phase 1 — Core loop MVP (pending)
## Phase 2 — Ollama cleanup (pending)
## Phase 3 — Dictation quality (pending)
## Phase 4 — Cross-platform hardening (pending)
