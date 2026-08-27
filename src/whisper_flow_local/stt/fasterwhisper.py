"""faster-whisper STT adapter (thin seam over the library).

Default backend on Windows/Linux. VAD filter on and ``condition_on_previous_text``
off by design (verified findings: silence hallucinations and cross-utterance
hallucination propagation are the two big Whisper failure modes). Imported
lazily so the core never requires the library.
"""

from __future__ import annotations

from typing import Any

from ..audio import AudioBuffer
from .base import Transcript


class FasterWhisperBackend:
    def __init__(
        self,
        model: str = "small.en",
        *,
        device: str = "auto",
        compute_type: str = "int8",
        vad_filter: bool = True,
    ) -> None:
        self._model_name = model
        self._device = device
        self._compute_type = compute_type
        self._vad_filter = vad_filter
        self._model: Any = None

    def _ensure_model(self) -> Any:
        if self._model is None:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                self._model_name, device=self._device, compute_type=self._compute_type
            )
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
        segments, info = model.transcribe(
            samples,
            language=language,
            initial_prompt=initial_prompt,
            temperature=0.0,
            vad_filter=self._vad_filter,
            condition_on_previous_text=False,
        )
        text = "".join(segment.text for segment in segments)
        return Transcript(text=text.strip(), language=getattr(info, "language", None))

    def unload(self) -> None:
        self._model = None
