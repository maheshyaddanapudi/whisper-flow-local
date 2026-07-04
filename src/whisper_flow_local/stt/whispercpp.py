"""whisper.cpp STT adapter for Apple Silicon (Metal/CoreML) — thin seam.

Default backend on macOS, where it is dramatically faster than CPU-only
faster-whisper (the verified benchmark gap is ~35x on Apple Silicon). Uses
``pywhispercpp``, imported lazily so the core never requires it. Verified on the
target Mac, not in CI.
"""

from __future__ import annotations

from typing import Any

from ..audio import AudioBuffer
from .base import Transcript


class WhisperCppBackend:
    def __init__(self, model: str = "small.en") -> None:
        self._model_name = model
        self._model: Any = None

    def _ensure_model(self) -> Any:
        if self._model is None:
            from pywhispercpp.model import Model

            self._model = Model(self._model_name)
        return self._model

    def transcribe(
        self,
        audio: AudioBuffer,
        *,
        language: str | None = None,
        initial_prompt: str | None = None,
    ) -> Transcript:
        import numpy as np

        model = self._ensure_model()
        samples = np.asarray(audio.data, dtype=np.float32)
        kwargs: dict[str, Any] = {}
        if language and language != "auto":
            kwargs["language"] = language
        if initial_prompt:
            kwargs["initial_prompt"] = initial_prompt
        segments = model.transcribe(samples, **kwargs)
        text = "".join(getattr(seg, "text", "") for seg in segments)
        return Transcript(text=text.strip(), language=language)

    def unload(self) -> None:
        self._model = None
