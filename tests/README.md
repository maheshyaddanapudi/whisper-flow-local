# Test policy

**Coverage target: 100% line + branch on pure-logic modules.** These have no
hardware or network side effects and are tested directly:

- `config.py` — schema, validation, load/dump, docs generation
- `daemon.py` state machine — transitions and abort paths
- `ipc.py` — request/response protocol framing
- `cleanup/prompts.py` — boolean-goals prompt builder
- `cleanup/ollama.py` — HTTP client (against a stdlib mock server)
- `dictionary/` — replacement engine + ordering
- `inject/` chain selection logic (against fake backends)
- `vad.py` endpointing logic
- `history.py`

**Hardware/network seams are tested against fakes, not real devices.** The mic,
global hotkeys, the system clipboard, the Ollama server and the STT models are
reached only through narrow interfaces (`AudioSource`, `HotkeyListener`,
`Injector`, `OllamaClient`, `STTBackend`). Tests supply in-memory fakes. The
thin real adapters that import `sounddevice`, `pynput`, `faster_whisper`, etc.
are excluded from the coverage denominator (see `pyproject.toml`), because
importing them requires physical devices absent in CI. Any excluded line must be
a trivial pass-through to the third-party library; logic lives on the testable
side of the seam.

**Adversarial cleanup suite:** `test_cleanup_contract.py` feeds transcripts that
tempt an LLM to answer questions, summarize, or drop content, and asserts the
prompt/guard contract holds ("clean, never transform meaning").

Run: `pytest --cov=whisper_flow_local --cov-branch --cov-report=term-missing`
