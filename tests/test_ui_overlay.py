"""Tests for the live overlay coordinator (pure logic over a fake surface)."""

from __future__ import annotations

from whisper_flow_local.pipeline_state import State
from whisper_flow_local.ui.overlay import OverlayController, OverlayView


class FakeSurface:
    """Records every view the coordinator renders."""

    def __init__(self) -> None:
        self.views: list[OverlayView] = []

    def render(self, view: OverlayView) -> None:
        self.views.append(view)

    @property
    def last(self) -> OverlayView:
        return self.views[-1]


def test_recording_shows_and_resets() -> None:
    surface = FakeSurface()
    ctl = OverlayController(surface)
    ctl.on_state(State.RECORDING)
    assert surface.last.visible is True
    assert surface.last.status == "Recording"
    assert surface.last.color == "#e53935"
    assert surface.last.transcript == ""
    assert surface.last.refined == ""


def test_partial_transcript_updates_view() -> None:
    surface = FakeSurface()
    ctl = OverlayController(surface)
    ctl.on_state(State.RECORDING)
    ctl.on_partial("hello wor")
    ctl.on_partial("hello world")
    assert surface.last.transcript == "hello world"
    assert surface.last.visible is True


def test_cleaning_streams_refinement_tokens() -> None:
    surface = FakeSurface()
    ctl = OverlayController(surface)
    ctl.on_state(State.RECORDING)
    ctl.on_partial("um hello world")
    ctl.on_state(State.CLEANING)
    # Entering cleaning clears any stale refinement but keeps the transcript.
    assert surface.last.refined == ""
    assert surface.last.transcript == "um hello world"
    ctl.on_token("Hello ")
    ctl.on_token("world.")
    assert surface.last.refined == "Hello world."
    assert surface.last.status == "Cleaning up"


def test_idle_hides_and_clears() -> None:
    surface = FakeSurface()
    ctl = OverlayController(surface)
    ctl.on_state(State.RECORDING)
    ctl.on_partial("something")
    ctl.on_state(State.IDLE)
    assert surface.last.visible is False
    assert surface.last.transcript == ""
    assert surface.last.refined == ""


def test_transcribing_and_injecting_keep_widget_visible() -> None:
    surface = FakeSurface()
    ctl = OverlayController(surface)
    ctl.on_state(State.RECORDING)
    ctl.on_state(State.TRANSCRIBING)
    assert surface.last.visible is True
    assert surface.last.status == "Transcribing"
    ctl.on_state(State.INJECTING)
    assert surface.last.visible is True
    assert surface.last.status == "Inserting"


def test_stop_control_invokes_bound_callback() -> None:
    surface = FakeSurface()
    stopped: list[int] = []
    ctl = OverlayController(surface, on_stop=lambda: stopped.append(1))
    ctl.request_stop()
    assert stopped == [1]


def test_stop_control_without_callback_is_noop() -> None:
    ctl = OverlayController(FakeSurface())
    ctl.request_stop()  # no on_stop bound -> must not raise


def test_bind_stop_wires_callback_after_construction() -> None:
    surface = FakeSurface()
    stopped: list[int] = []
    ctl = OverlayController(surface)
    ctl.bind_stop(lambda: stopped.append(1))
    ctl.request_stop()
    assert stopped == [1]


def test_full_lifecycle_streams_then_hides() -> None:
    surface = FakeSurface()
    ctl = OverlayController(surface)
    ctl.on_state(State.RECORDING)
    ctl.on_partial("um so like the meeting is at noon")
    ctl.on_state(State.TRANSCRIBING)
    ctl.on_state(State.CLEANING)
    for tok in ["The ", "meeting ", "is ", "at ", "noon."]:
        ctl.on_token(tok)
    ctl.on_state(State.INJECTING)
    assert surface.last.refined == "The meeting is at noon."
    ctl.on_state(State.IDLE)
    assert surface.last.visible is False
