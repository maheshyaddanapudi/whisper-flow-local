"""Transparency log — see exactly what was sent to the local LLM.

A verifiable-privacy feature (Superwhisper's "what was sent" trait, taken
further): every LLM call records its system prompt, the user message, and the
returned output, so the user can audit precisely what left the STT stage and
went to Ollama — all on-device, in memory, never persisted. Pure logic, tested.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class LlmCall:
    kind: str  # "cleanup" | "command"
    system: str  # the system prompt that was sent
    user: str  # the user message that was sent
    output: str  # what the model returned


class TransparencyLog:
    """Bounded, most-recent-first record of LLM calls (in memory only)."""

    def __init__(self, size: int = 20) -> None:
        self._size = size
        self._calls: deque[LlmCall] = deque(maxlen=size if size > 0 else None)

    def record(self, kind: str, system: str, user: str, output: str) -> None:
        if self._size == 0:
            return
        self._calls.appendleft(LlmCall(kind=kind, system=system, user=user, output=output))

    def recent(self, n: int | None = None) -> list[LlmCall]:
        calls = list(self._calls)
        return calls[:n] if n is not None else calls

    def __len__(self) -> int:
        return len(self._calls)

    def clear(self) -> None:
        self._calls.clear()
