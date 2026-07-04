"""Speech-to-text backend interface.

A thin, swappable seam so the pipeline is engine-agnostic (faster-whisper on
Windows/Linux, whisper.cpp Metal/CoreML on macOS, room for Parakeet/streaming
later). Only the interface lives here; real adapters are in sibling modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ..audio import AudioBuffer


@dataclass(frozen=True)
class Transcript:
    """Result of transcribing one utterance."""

    text: str
    language: str | None = None

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()


@runtime_checkable
class STTBackend(Protocol):
    """Transcribes audio to text. Implementations keep the model resident and
    may unload it after an idle period."""

    def transcribe(
        self,
        audio: AudioBuffer,
        *,
        language: str | None = None,
        initial_prompt: str | None = None,
    ) -> Transcript:
        """Transcribe ``audio`` to a :class:`Transcript`."""

    def unload(self) -> None:
        """Release the model from memory (called after the idle timeout)."""
