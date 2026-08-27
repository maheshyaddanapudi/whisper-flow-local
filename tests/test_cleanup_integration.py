"""Integration: controller + real CleanupEngine + mock Ollama server."""

from __future__ import annotations

from fakes import FakeAudioSource, FakeInjector, FakeSTT
from whisper_flow_local.cleanup.engine import CleanupEngine
from whisper_flow_local.cleanup.prompts import CleanupGoals
from whisper_flow_local.controller import Controller, ControllerConfig, _Deps
from whisper_flow_local.history import History
from whisper_flow_local.inject.base import InjectionChain
from whisper_flow_local.notifier import StateNotifier
from whisper_flow_local.ui.overlay import OverlayController, OverlayView

RAW = "um so this is a fairly long dictated sentence that should be cleaned up now"


def _controller_with_cleanup(mock_ollama, injector: FakeInjector) -> Controller:
    engine = CleanupEngine(host=mock_ollama.host, model="gemma3:4b", goals=CleanupGoals())
    deps = _Deps(
        audio=FakeAudioSource(duration_s=1.0),
        stt=FakeSTT(RAW),
        injection=InjectionChain([injector]),
        history=History(size=5),
        cleanup=engine.clean,
    )
    return Controller(ControllerConfig(min_duration_s=0.15, cleanup_min_chars=50), deps)


def test_full_pipeline_with_cleanup(mock_ollama) -> None:
    mock_ollama.chat_response = lambda text: "This is a cleaned sentence."
    injector = FakeInjector("fake")
    ctl = _controller_with_cleanup(mock_ollama, injector)
    ctl.toggle()
    result = ctl.toggle()
    assert result.status == "injected"
    assert result.cleaned == "This is a cleaned sentence."
    assert injector.requests[0].text == "This is a cleaned sentence."


def test_ollama_down_midflight_injects_raw(mock_ollama) -> None:
    """Kill Ollama between recording and cleanup -> raw transcript still injected."""
    injector = FakeInjector("fake")
    ctl = _controller_with_cleanup(mock_ollama, injector)
    ctl.toggle()  # start recording
    mock_ollama.fail_chat = True  # Ollama dies mid-flight
    result = ctl.toggle()  # stop -> transcribe -> cleanup fails -> raw
    assert result.status == "injected"
    assert result.cleaned == ""
    assert injector.requests[0].text == RAW  # raw injected, nothing lost


def test_raw_intent_skips_cleanup(mock_ollama) -> None:
    """clean=False (second hotkey / --raw) bypasses the LLM entirely."""
    called: list[str] = []
    mock_ollama.chat_response = lambda text: called.append(text) or "CLEANED"
    injector = FakeInjector("fake")
    ctl = _controller_with_cleanup(mock_ollama, injector)
    ctl.ptt_down()
    result = ctl.ptt_up(clean=False)
    assert result.status == "injected"
    assert result.cleaned == ""
    assert injector.requests[0].text == RAW
    assert called == []  # Ollama never contacted


def test_overlay_streams_refinement_over_full_pipeline(mock_ollama) -> None:
    """Press → record → transcribe → stream cleanup into the overlay → inject → hide.

    Wires the live overlay exactly as ``build_daemon`` does: the engine streams
    tokens to ``OverlayController.on_token`` and the controller's state changes
    drive the widget through a StateNotifier.
    """
    mock_ollama.chat_response = lambda text: "This is a cleaned sentence."

    class Surface:
        def __init__(self) -> None:
            self.views: list[OverlayView] = []

        def render(self, view: OverlayView) -> None:
            self.views.append(view)

    surface = Surface()
    overlay = OverlayController(surface)
    engine = CleanupEngine(
        host=mock_ollama.host,
        model="gemma3:4b",
        goals=CleanupGoals(),
        on_token=overlay.on_token,
    )
    notifier = StateNotifier()
    notifier.register(overlay.on_state)
    injector = FakeInjector("fake")
    deps = _Deps(
        audio=FakeAudioSource(duration_s=1.0),
        stt=FakeSTT(RAW),
        injection=InjectionChain([injector]),
        history=History(size=5),
        cleanup=engine.clean,
        on_state_change=notifier,
        on_transcript=overlay.on_partial,
    )
    ctl = Controller(ControllerConfig(min_duration_s=0.15, cleanup_min_chars=50), deps)
    overlay.bind_stop(ctl.cancel)

    ctl.toggle()  # press: recording -> overlay shows
    assert surface.views[-1].visible is True
    result = ctl.toggle()  # release: transcribe -> stream cleanup -> inject -> idle

    assert result.status == "injected"
    assert injector.requests[0].text == "This is a cleaned sentence."
    # The transcript pane showed what was heard while the refinement streamed.
    during_cleaning = [v for v in surface.views if v.refined]
    assert all(v.transcript == RAW for v in during_cleaning)
    # The overlay saw the refinement stream token-by-token, then hid at idle.
    streamed = [v.refined for v in during_cleaning]
    assert streamed[-1] == "This is a cleaned sentence."
    assert len(streamed) >= 2  # arrived in pieces, not one shot
    assert surface.views[-1].visible is False


def test_short_utterance_skips_cleanup(mock_ollama) -> None:
    mock_ollama.chat_response = lambda text: "SHOULD NOT BE USED"
    injector = FakeInjector("fake")
    engine = CleanupEngine(host=mock_ollama.host, model="m", goals=CleanupGoals())
    deps = _Deps(
        audio=FakeAudioSource(duration_s=1.0),
        stt=FakeSTT("short one"),  # under 50 chars
        injection=InjectionChain([injector]),
        history=History(),
        cleanup=engine.clean,
    )
    ctl = Controller(ControllerConfig(min_duration_s=0.15, cleanup_min_chars=50), deps)
    ctl.toggle()
    result = ctl.toggle()
    assert result.status == "injected"
    assert result.cleaned == ""
    assert injector.requests[0].text == "short one"
    assert mock_ollama.requests == []  # gate skipped the call
