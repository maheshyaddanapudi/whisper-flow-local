"""Translate raw hotkey press/release events into start/stop intents.

This is the hybrid tap-vs-hold logic (VoiceInk/Superwhisper trait): a single
hotkey where a quick *tap* toggles recording on/off and a *hold* acts as
push-to-talk (record while held). Kept pure and timestamp-driven so every mode
and edge is unit-tested without real keys or clocks.

The min-duration discard and the post-release grace period are applied by the
caller (controller/daemon) against the real audio, not here.
"""

from __future__ import annotations

from enum import Enum, StrEnum, auto


class Mode(StrEnum):
    HYBRID = "hybrid"
    TOGGLE = "toggle"
    PUSH_TO_TALK = "push_to_talk"
    CONTINUOUS = "continuous"


class Intent(Enum):
    NONE = auto()
    START = auto()
    STOP = auto()


class RecordingResolver:
    """Stateful resolver mapping press/release (with timestamps) to intents.

    ``hold_threshold_s`` is the tap/hold boundary. In continuous mode the hotkey
    behaves like toggle for starting/stopping the session; the auto-rearm loop
    itself lives in the VAD layer (Phase 3).
    """

    def __init__(self, mode: Mode, hold_threshold_s: float = 0.5) -> None:
        self.mode = mode
        self.hold_threshold_s = hold_threshold_s
        self._recording = False
        self._latched = False  # hybrid: recording was toggled on by a tap
        self._press_time: float | None = None
        self._pending_stop_tap = False  # hybrid: a press that may become a stop-tap

    @property
    def recording(self) -> bool:
        return self._recording

    def press(self, now: float) -> Intent:
        if self.mode in (Mode.TOGGLE, Mode.CONTINUOUS):
            return self._toggle()
        if self.mode == Mode.PUSH_TO_TALK:
            if not self._recording:
                self._recording = True
                return Intent.START
            return Intent.NONE
        # hybrid
        if not self._recording:
            self._recording = True
            self._latched = False
            self._press_time = now
            return Intent.START
        if self._latched:
            # Recording was latched on by a tap; this press may end it.
            self._pending_stop_tap = True
            self._press_time = now
        return Intent.NONE

    def release(self, now: float) -> Intent:
        if self.mode in (Mode.TOGGLE, Mode.CONTINUOUS):
            return Intent.NONE
        if self.mode == Mode.PUSH_TO_TALK:
            if self._recording:
                self._recording = False
                return Intent.STOP
            return Intent.NONE
        # hybrid
        if self._pending_stop_tap:
            # Second tap: stop regardless of how long it was held.
            self._reset()
            return Intent.STOP
        if self._press_time is None:  # pragma: no cover - defensive
            return Intent.NONE
        held = now - self._press_time
        if held >= self.hold_threshold_s:
            # Held long enough: this was push-to-talk; release stops it.
            self._reset()
            return Intent.STOP
        # Short tap: latch on and keep recording until the next tap.
        self._latched = True
        self._press_time = None
        return Intent.NONE

    def reset(self) -> None:
        """Force the resolver back to a clean idle state.

        Called by the controller whenever the pipeline returns to idle, so the
        resolver stays in sync even when start/stop was driven via IPC rather
        than the hotkey.
        """
        self._reset()

    def _toggle(self) -> Intent:
        if self._recording:
            self._recording = False
            return Intent.STOP
        self._recording = True
        return Intent.START

    def _reset(self) -> None:
        self._recording = False
        self._latched = False
        self._press_time = None
        self._pending_stop_tap = False
