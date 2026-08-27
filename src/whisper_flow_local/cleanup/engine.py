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
from .ollama import chat_stream as _default_chat_stream
from .prompts import (
    CleanupGoals,
    build_instruction_message,
    build_instruction_prompt,
    build_system_prompt,
)

ChatFn = Callable[..., str]
StreamChatFn = Callable[..., str]
# (kind, system, user, output) recorded for the transparency log.
RecordFn = Callable[[str, str, str, str], None]
# A single streamed token, for the live overlay.
TokenFn = Callable[[str], None]


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
        chat_stream: StreamChatFn = _default_chat_stream,
        record: RecordFn | None = None,
        on_token: TokenFn | None = None,
    ) -> None:
        self._host = host
        self._model = model
        self._system = build_system_prompt(goals, prompt_override)
        self._instruction_system = build_instruction_prompt(instruction_override)
        self._keep_alive = keep_alive
        self._timeout = timeout
        self._max_growth_ratio = max_growth_ratio
        self._chat = chat
        self._chat_stream = chat_stream
        # Transparency: called with (kind, system, user, output) after each call.
        self._record = record or (lambda *_a: None)
        # Live overlay: when set, completions stream token-by-token.
        self._on_token = on_token
        # Set by abort() (the overlay's Stop control) to drop an in-flight stream.
        self._aborted = False

    def abort(self) -> None:
        """Abort the current streaming completion (safe from any thread).

        The stream check between chunks raises, ``clean()`` catches it and
        returns ``""``, and the controller injects the raw transcript — so Stop
        during refinement means "give me the raw text now". The flag resets at
        the start of the next completion.
        """
        self._aborted = True

    @property
    def system_prompt(self) -> str:
        return self._system

    @property
    def instruction_prompt(self) -> str:
        return self._instruction_system

    def _complete(self, system: str, user: str) -> str:
        """Run one completion, streaming token-by-token when an overlay is attached.

        Both paths raise :class:`OllamaError` on failure and return the full
        assistant text; the only difference is whether ``on_token`` fires as the
        model produces the text (for the live overlay).
        """
        self._aborted = False  # a stale Stop must not kill this fresh completion
        if self._on_token is not None:
            return self._chat_stream(
                self._host,
                self._model,
                system,
                user,
                self._on_token,
                keep_alive=self._keep_alive,
                timeout=self._timeout,
                should_abort=lambda: self._aborted,
            )
        return self._chat(
            self._host,
            self._model,
            system,
            user,
            keep_alive=self._keep_alive,
            timeout=self._timeout,
        )

    def clean(self, raw: str, system_override: str = "") -> str:
        """Return cleaned text, or ``""`` to signal "fall back to raw".

        ``system_override`` (from a per-app profile) replaces the default
        cleanup prompt for this call only.
        """
        system = system_override.strip() or self._system
        try:
            out = self._complete(system, raw)
        except OllamaError:
            return ""
        self._record("cleanup", system, raw, out)
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
        message = build_instruction_message(instruction, text)
        try:
            out = self._complete(self._instruction_system, message)
        except OllamaError:
            return ""
        self._record("command", self._instruction_system, message, out)
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
