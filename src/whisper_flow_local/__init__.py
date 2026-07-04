"""whisper-flow-local: fully local, privacy-first dictation.

Global hotkey -> local Whisper STT -> Ollama LLM cleanup -> text in any app.
No cloud, no telemetry; audio stays in RAM and is discarded by default.
"""

from __future__ import annotations

__version__ = "0.1.0"
__all__ = ["__version__"]
