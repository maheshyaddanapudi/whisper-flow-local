"""VAD-driven and continuous capture orchestration.

Marries the pure :class:`~whisper_flow_local.vad.Endpointer` (layer 1 of the
two-layer VAD) to the controller's start/stop, so recording auto-stops on a run
of silence and — in continuous mode — auto-rearms for the next utterance until
cancelled.

Kept as pure orchestration over injected seams (a level poller, a clock, a
cancel check), so it is fully tested with fakes. The real daemon supplies a
poller backed by live microphone RMS from ``SoundDeviceSource``.
"""

from __future__ import annotations

from collections.abc import Callable

from .vad import Endpointer

# poll() -> (rms_level, elapsed_seconds) for the latest chunk, or None when the
# audio stream has ended.
LevelPoll = Callable[[], tuple[float, float] | None]


class VadCapture:
    """Drives one or many VAD-endpointed dictations through a controller."""

    def __init__(
        self,
        controller: object,  # duck-typed: needs ptt_down()/ptt_up()
        poll: LevelPoll,
        endpointer: Endpointer,
        *,
        should_cancel: Callable[[], bool] = lambda: False,
        sleep: Callable[[float], None] = lambda _s: None,
        poll_interval_s: float = 0.05,
    ) -> None:
        self._controller = controller
        self._poll = poll
        self._endpointer = endpointer
        self._should_cancel = should_cancel
        self._sleep = sleep
        self._poll_interval_s = poll_interval_s

    def record_once(self) -> str:
        """Record until silence endpoint (or cancel / stream end), then process.

        Returns "cancelled", "ended" (stream stopped), or "endpoint".
        """
        self._controller.ptt_down()  # type: ignore[attr-defined]
        self._endpointer.reset()
        outcome = "ended"
        while True:
            if self._should_cancel():
                outcome = "cancelled"
                break
            chunk = self._poll()
            if chunk is None:
                outcome = "ended"
                break
            level, elapsed = chunk
            if self._endpointer.observe(level, elapsed):
                outcome = "endpoint"
                break
            self._sleep(self._poll_interval_s)
        if outcome == "cancelled":
            self._controller.cancel()  # type: ignore[attr-defined]
        else:
            self._controller.ptt_up()  # type: ignore[attr-defined]
        return outcome

    def run_continuous(self) -> int:
        """Auto-rearm after each utterance until cancelled or the stream ends.

        Returns the number of utterances recorded.
        """
        count = 0
        while not self._should_cancel():
            outcome = self.record_once()
            if outcome == "endpoint":
                count += 1
                continue
            if outcome == "ended":
                count += 1
            break
        return count
