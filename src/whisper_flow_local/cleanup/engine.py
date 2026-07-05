"""The cleanup engine: raw transcript -> cleaned text via a local Ollama model.

This is the ``CleanupFn`` the controller calls. Contract:
- Return the cleaned text on success.
- Return ``""`` on any failure/timeout, which tells the controller to inject the
  **raw** transcript. Cleanup is an enhancement, never a gate.

The length gate (skip cleanup for very short utterances) lives in the controller
so it also governs when the CLEANING state is entered; the engine focuses on the
Ollama call. A ``chat`` seam is injected for tests.
"""

from __future__ import annotations

from collections.abc import Callable

from .ollama import OllamaError
from .ollama import chat as _default_chat
from .prompts import (
    CleanupGoals,
    build_instruction_message,
    build_instruction_prompt,
    build_system_prompt,
)

ChatFn = Callable[..., str]


class CleanupEngine:
    def __init__(
        self,
        *,
        host: str,
        model: str,
        goals: CleanupGoals,
        prompt_override: str = "",
        instruction_override: str = "",
        keep_alive: str = "30m",
        timeout: float = 8.0,
        max_growth_ratio: float = 2.5,
        chat: ChatFn = _default_chat,
    ) -> None:
        self._host = host
        self._model = model
        self._system = build_system_prompt(goals, prompt_override)
        self._instruction_system = build_instruction_prompt(instruction_override)
        self._keep_alive = keep_alive
        self._timeout = timeout
        self._max_growth_ratio = max_growth_ratio
        self._chat = chat

    @property
    def system_prompt(self) -> str:
        return self._system

    @property
    def instruction_prompt(self) -> str:
        return self._instruction_system

    def clean(self, raw: str) -> str:
        """Return cleaned text, or ``""`` to signal "fall back to raw"."""
        try:
            out = self._chat(
                self._host,
                self._model,
                self._system,
                raw,
                keep_alive=self._keep_alive,
                timeout=self._timeout,
            )
        except OllamaError:
            return ""
        cleaned = out.strip()
        if not self._plausibly_cleaned(raw, cleaned):
            # The model answered/expanded instead of cleaning; trust the raw text.
            return ""
        return cleaned

    def instruct(self, instruction: str, text: str) -> str:
        """Command mode: transform ``text`` per a spoken ``instruction``.

        Returns the transformed text, or ``""`` on failure (caller leaves the
        selection unchanged). Unlike cleanup there is no growth guard —
        instructions like "expand this" legitimately lengthen the text.
        """
        if not text.strip():
            return ""
        try:
            out = self._chat(
                self._host,
                self._model,
                self._instruction_system,
                build_instruction_message(instruction, text),
                keep_alive=self._keep_alive,
                timeout=self._timeout,
            )
        except OllamaError:
            return ""
        return out.strip()

    def _plausibly_cleaned(self, raw: str, cleaned: str) -> bool:
        """Reject output that grew far beyond the input (answer/expansion).

        Cleanup should preserve meaning; heavy shrink is legitimate (filler
        removal), but large *growth* means the model added content. A small
        additive allowance lets short inputs gain punctuation/capitalization.
        """
        if not cleaned:
            return False
        allowance = 40  # chars, so "ok" -> "Okay." never trips the guard
        return len(cleaned) <= len(raw) * self._max_growth_ratio + allowance
