"""Tests for the VAD/continuous capture orchestration."""

from __future__ import annotations

from whisper_flow_local.capture import VadCapture
from whisper_flow_local.vad import Endpointer


class FakeController:
    def __init__(self) -> None:
        self.events: list[str] = []

    def ptt_down(self) -> None:
        self.events.append("down")

    def ptt_up(self) -> None:
        self.events.append("up")

    def cancel(self) -> None:
        self.events.append("cancel")


def _chunks(seq):
    it = iter(seq)

    def poll():
        return next(it, None)

    return poll


def test_record_once_endpoint() -> None:
    ctl = FakeController()
    ep = Endpointer(silence_threshold=0.1, silence_duration_s=0.4)
    # speech, then silence long enough to endpoint
    poll = _chunks([(0.5, 0.2), (0.0, 0.2), (0.0, 0.2), (0.0, 0.2)])
    cap = VadCapture(ctl, poll, ep)
    assert cap.record_once() == "endpoint"
    assert ctl.events == ["down", "up"]


def test_record_once_stream_ended() -> None:
    ctl = FakeController()
    ep = Endpointer()
    poll = _chunks([(0.5, 0.2)])  # one chunk then None
    cap = VadCapture(ctl, poll, ep)
    assert cap.record_once() == "ended"
    assert ctl.events == ["down", "up"]


def test_record_once_cancelled() -> None:
    ctl = FakeController()
    ep = Endpointer()
    cancel = {"v": False}
    poll = _chunks([(0.5, 0.2), (0.5, 0.2)])
    cap = VadCapture(ctl, poll, ep, should_cancel=lambda: cancel["v"])
    # flip cancel after first observe by using a mutable via should_cancel
    calls = {"n": 0}

    def should_cancel():
        calls["n"] += 1
        return calls["n"] > 1  # cancel on the second loop check

    cap = VadCapture(ctl, poll, ep, should_cancel=should_cancel)
    assert cap.record_once() == "cancelled"
    assert ctl.events == ["down", "cancel"]


def test_run_continuous_multiple_utterances() -> None:
    ctl = FakeController()
    ep = Endpointer(silence_threshold=0.1, silence_duration_s=0.2)
    # two endpointed utterances, then cancel
    poll = _chunks(
        [
            (0.5, 0.2),
            (0.0, 0.2),
            (0.0, 0.2),  # utterance 1 -> endpoint
            (0.5, 0.2),
            (0.0, 0.2),
            (0.0, 0.2),  # utterance 2 -> endpoint
        ]
    )
    stops = {"n": 0}

    def should_cancel():
        stops["n"] += 1
        return stops["n"] > 40  # never during, so it runs until stream ends

    cap = VadCapture(ctl, poll, ep, should_cancel=should_cancel)
    count = cap.run_continuous()
    assert count >= 2
    assert ctl.events.count("down") >= 2


def test_run_continuous_stops_on_cancel() -> None:
    ctl = FakeController()
    ep = Endpointer()
    cap = VadCapture(ctl, _chunks([]), ep, should_cancel=lambda: True)
    assert cap.run_continuous() == 0
    assert ctl.events == []  # cancelled before starting


def test_run_continuous_breaks_on_midutterance_cancel() -> None:
    ctl = FakeController()
    ep = Endpointer()
    # cancel fires on the 2nd check: enters the loop, record_once returns
    # "cancelled" (no increment), then run_continuous breaks.
    checks = {"n": 0}

    def should_cancel():
        checks["n"] += 1
        return checks["n"] >= 2

    cap = VadCapture(ctl, _chunks([(0.5, 0.2)]), ep, should_cancel=should_cancel)
    assert cap.run_continuous() == 0  # cancelled, not counted
    assert "cancel" in ctl.events
