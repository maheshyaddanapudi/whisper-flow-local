"""Audio capture interface and buffer.

The pipeline needs only a narrow contract: start capturing, stop and hand back a
buffer. The buffer knows its duration, which is all the pure logic (min-duration
discard, safety cap) needs. The real ``sounddevice`` adapter is a thin seam,
imported lazily so the core stays dependency-free and importable anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class AudioBuffer:
    """Captured mono audio. ``data`` is a numpy float32 array in real use, or a
    plain sequence in tests; only its length and the sample rate matter here."""

    data: Any
    sample_rate: int

    @property
    def num_samples(self) -> int:
        return len(self.data)

    @property
    def duration_s(self) -> float:
        if self.sample_rate <= 0:  # pragma: no cover - guarded by config choices
            return 0.0
        return self.num_samples / self.sample_rate

    @property
    def is_empty(self) -> bool:
        return self.num_samples == 0


@runtime_checkable
class AudioSource(Protocol):
    """Something that can capture microphone audio on demand."""

    def start(self) -> None:
        """Begin capturing into an internal buffer."""

    def stop(self) -> AudioBuffer:
        """Stop capturing and return everything captured since ``start``."""

    @property
    def is_recording(self) -> bool:
        """Whether capture is currently active."""
