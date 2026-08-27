"""Streaming partial-transcript preview coordinator.

Two-tier previewing: while you're still speaking, a *fast* (tiny) STT model
transcribes the audio-so-far to show a live partial; when you stop, the accurate
model produces the final text. This coordinator owns the *logic* — transcribe
the partial, emit it only when it changed, and reset between utterances — over
injected seams, so it's fully tested. Feeding it growing live-audio buffers and
rendering the preview overlay are the pending hardware seams.
"""

from __future__ import annotations

from collections.abc import Callable

from ..audio import AudioBuffer

# Transcribe a (partial) buffer to text — backed by a tiny/fast model in real use.
PreviewTranscribe = Callable[[AudioBuffer], str]
# Show the current partial preview to the user (overlay in real use).
OnPreview = Callable[[str], None]


class StreamingPreview:
    """Emits deduplicated partial-transcript previews during recording."""

    def __init__(self, transcribe: PreviewTranscribe, on_preview: OnPreview) -> None:
        self._transcribe = transcribe
        self._on_preview = on_preview
        self._last = ""

    def update(self, audio: AudioBuffer) -> str:
        """Transcribe the audio-so-far; emit the preview if it changed.

        Errors in the fast model are swallowed — a missing preview must never
        affect the real dictation. Returns the current partial text.
        """
        try:
            text = self._transcribe(audio).strip()
        except Exception:
            return self._last
        if text and text != self._last:
            self._last = text
            self._on_preview(text)
        return self._last

    def reset(self) -> None:
        """Clear state between utterances (and hide the overlay)."""
        self._last = ""
        self._on_preview("")
