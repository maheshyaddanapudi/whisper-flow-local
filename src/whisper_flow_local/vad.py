"""Voice-activity endpointing — the cheap first layer of the two-layer VAD.

This decides *when a spoken utterance has ended* (a run of silence long enough
to stop recording) for continuous / VAD-driven modes. It is deliberately cheap
(RMS energy over short chunks) and pure. The second layer — Silero ``vad_filter``
that scrubs the captured audio before transcription to prevent silence
hallucinations — lives in the faster-whisper adapter.

Both layers default on; half the prior-art field ships no VAD at all.
"""

from __future__ import annotations

import math
from collections.abc import Sequence


def rms(samples: Sequence[float]) -> float:
    """Root-mean-square energy of a chunk of normalized samples."""
    if not samples:
        return 0.0
    return math.sqrt(sum(s * s for s in samples) / len(samples))


class Endpointer:
    """Detects end-of-utterance from a run of silence after speech.

    Feed successive chunks via :meth:`observe`. It only reports an endpoint once
    speech has been seen, so leading silence never triggers a premature stop.
    """

    def __init__(self, *, silence_threshold: float = 0.01, silence_duration_s: float = 0.9) -> None:
        self._threshold = silence_threshold
        self._silence_duration_s = silence_duration_s
        self._has_speech = False
        self._silent_accum_s = 0.0

    @property
    def has_speech(self) -> bool:
        return self._has_speech

    def observe(self, level: float, duration_s: float) -> bool:
        """Feed one chunk's RMS ``level`` and its ``duration_s``.

        Returns True when an end-of-utterance has been detected.
        """
        if level >= self._threshold:
            self._has_speech = True
            self._silent_accum_s = 0.0
            return False
        if self._has_speech:
            self._silent_accum_s += duration_s
            if self._silent_accum_s >= self._silence_duration_s:
                return True
        return False

    def reset(self) -> None:
        self._has_speech = False
        self._silent_accum_s = 0.0
