"""whisper.cpp STT adapter for Apple Silicon (Metal/CoreML).

Fully implemented and wired in Phase 4 (macOS hardening). Declared here so the
backend selector and packaging can reference it; instantiating it before Phase 4
raises with a clear message rather than importing a half-built path.
"""

from __future__ import annotations

from ..audio import AudioBuffer
from .base import Transcript


class WhisperCppBackend:
    def __init__(self, model: str = "small.en") -> None:  # pragma: no cover - Phase 4
        self._model_name = model
        raise NotImplementedError(
            "whisper.cpp backend lands in Phase 4; set stt.backend='faster_whisper' for now"
        )

    def transcribe(  # pragma: no cover - Phase 4
        self,
        audio: AudioBuffer,
        *,
        language: str | None = None,
        initial_prompt: str | None = None,
    ) -> Transcript:
        raise NotImplementedError

    def unload(self) -> None:  # pragma: no cover - Phase 4
        pass
