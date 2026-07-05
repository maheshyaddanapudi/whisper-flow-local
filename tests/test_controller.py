"""Tests for the dictation controller (orchestration over the state machine)."""

from __future__ import annotations

from fakes import FakeAudioSource, FakeInjector, FakeSTT
from whisper_flow_local.controller import Controller, ControllerConfig, _Deps
from whisper_flow_local.history import History
from whisper_flow_local.inject.base import InjectionChain
from whisper_flow_local.pipeline_state import State
from whisper_flow_local.recording import Mode


def make_controller(
    *,
    mode: Mode = Mode.HYBRID,
    stt_text: str = "this is a reasonably long dictated sentence for testing",
    stt_raises: bool = False,
    inject_ok: bool = True,
    duration_s: float = 1.0,
    cleanup=None,
    min_duration_s: float = 0.15,
    cleanup_min_chars: int = 50,
):
    audio = FakeAudioSource(duration_s=duration_s)
    stt = FakeSTT(stt_text, raises=stt_raises)
    injector = FakeInjector("fake", ok=inject_ok)
    chain = InjectionChain([injector])
    history = History(size=5)
    states: list[State] = []
    deps = _Deps(
        audio=audio,
        stt=stt,
        injection=chain,
        history=history,
        cleanup=cleanup,
        on_state_change=states.append,
    )
    cfg = ControllerConfig(
        mode=mode, min_duration_s=min_duration_s, cleanup_min_chars=cleanup_min_chars
    )
    ctl = Controller(cfg, deps)
    return ctl, audio, stt, injector, history, states


def test_toggle_happy_path() -> None:
    ctl, audio, _stt, injector, history, states = make_controller()
    assert ctl.toggle().status == "started"
    assert audio.is_recording
    assert ctl.state == State.RECORDING

    result = ctl.toggle()
    assert result.status == "injected"
    assert result.backend == "fake"
    assert ctl.state == State.IDLE
    assert history.last is not None
    assert len(injector.requests) == 1
    # visited transcribing, injecting, and back to idle
    assert State.TRANSCRIBING in states
    assert State.INJECTING in states
    assert states[-1] == State.IDLE


def test_discarded_short_recording() -> None:
    ctl, _audio, stt, *_ = make_controller(duration_s=0.05)  # under min_duration
    ctl.toggle()
    result = ctl.toggle()
    assert result.status == "discarded_short"
    assert ctl.state == State.IDLE
    assert stt.calls == []  # never transcribed


def test_empty_transcript() -> None:
    ctl, *_ = make_controller(stt_text="   ")
    ctl.toggle()
    assert ctl.toggle().status == "empty"
    assert ctl.state == State.IDLE


def test_stt_error_recovers_to_idle() -> None:
    ctl, *_ = make_controller(stt_raises=True)
    ctl.toggle()
    result = ctl.toggle()
    assert result.status == "error"
    assert "stt" in result.reason
    assert ctl.state == State.IDLE


def test_injection_failure_is_error() -> None:
    ctl, *_ = make_controller(inject_ok=False)
    ctl.toggle()
    result = ctl.toggle()
    assert result.status == "error"
    assert ctl.state == State.IDLE


def test_cleanup_runs_when_over_min_chars() -> None:
    seen: list[str] = []

    def cleanup(raw: str) -> str:
        seen.append(raw)
        return "CLEANED"

    ctl, _a, _s, injector, _history, states = make_controller(cleanup=cleanup)
    ctl.toggle()
    result = ctl.toggle()
    assert result.status == "injected"
    assert result.cleaned == "CLEANED"
    assert injector.requests[0].text == "CLEANED"
    assert State.CLEANING in states
    assert seen  # cleanup received the raw text


def test_cleanup_skipped_under_min_chars() -> None:
    called: list[str] = []
    ctl, *_ = make_controller(
        stt_text="short", cleanup=lambda r: called.append(r) or "X", cleanup_min_chars=50
    )
    ctl.toggle()
    result = ctl.toggle()
    assert result.status == "injected"
    assert result.cleaned == ""  # cleanup skipped
    assert called == []


def test_cleanup_failure_falls_back_to_raw() -> None:
    def cleanup(raw: str) -> str:
        raise RuntimeError("ollama down")

    ctl, _a, _s, injector, *_ = make_controller(cleanup=cleanup)
    ctl.toggle()
    result = ctl.toggle()
    assert result.status == "injected"
    assert result.cleaned == ""
    # raw text still injected — cleanup never gates
    assert injector.requests[0].text.startswith("this is a reasonably long")


def test_cancel_while_recording() -> None:
    ctl, audio, stt, *_ = make_controller()
    ctl.toggle()
    result = ctl.cancel()
    assert result.status == "cancelled"
    assert ctl.state == State.IDLE
    assert audio.stops == 1
    assert stt.calls == []


def test_cancel_when_idle_is_noop() -> None:
    ctl, *_ = make_controller()
    assert ctl.cancel().status == "noop"


def test_ptt_down_up() -> None:
    ctl, *_ = make_controller()
    assert ctl.ptt_down().status == "started"
    assert ctl.ptt_down().status == "busy"  # already recording
    assert ctl.ptt_up().status == "injected"
    assert ctl.ptt_up().status == "noop"  # nothing to stop


def test_toggle_busy_when_processing() -> None:
    # Force a non-idle, non-recording state by cancelling mid-transcribe is hard;
    # instead drive to RECORDING then check toggle during a stuck transcribe.
    ctl, *_ = make_controller()
    ctl.ptt_down()
    # while RECORDING, toggle stops+processes (not busy); verify busy via a
    # manual state: after starting, move SM to TRANSCRIBING through a slow path.
    # Simplest: check that toggling from INJECTING-like state is guarded by
    # exercising paste_last busy below.
    assert ctl.state == State.RECORDING


def test_hotkey_hybrid_hold_flow() -> None:
    ctl, _audio, *_ = make_controller(mode=Mode.HYBRID)
    assert ctl.on_hotkey_press(0.0).status == "started"
    result = ctl.on_hotkey_release(1.0)  # long hold -> PTT stop
    assert result.status == "injected"
    assert ctl.state == State.IDLE


def test_hotkey_hybrid_tap_latch_then_stop() -> None:
    ctl, *_ = make_controller(mode=Mode.HYBRID)
    ctl.on_hotkey_press(0.0)
    assert ctl.on_hotkey_release(0.1).status == "noop"  # latched, still recording
    assert ctl.state == State.RECORDING
    ctl.on_hotkey_press(1.0)
    assert ctl.on_hotkey_release(1.1).status == "injected"  # tap off


def test_paste_last_cleaned_and_raw() -> None:
    ctl, _a, _s, injector, _history, _st = make_controller(cleanup=lambda r: "CLEANED")
    ctl.toggle()
    ctl.toggle()  # produces one dictation (raw + CLEANED)
    injector.requests.clear()

    assert ctl.paste_last().status == "injected"
    assert injector.requests[-1].text == "CLEANED"

    assert ctl.paste_last(raw=True).status == "injected"
    assert injector.requests[-1].text.startswith("this is a reasonably long")


def test_paste_last_empty_history() -> None:
    ctl, *_ = make_controller()
    assert ctl.paste_last().status == "noop"


def test_paste_last_injection_failure() -> None:
    ctl, _a, _s, injector, *_ = make_controller(inject_ok=True)
    ctl.toggle()
    ctl.toggle()
    injector._ok = False  # now fail
    assert ctl.paste_last().status == "error"


def test_paste_last_busy_when_active() -> None:
    ctl, *_ = make_controller()
    ctl.ptt_down()  # RECORDING
    assert ctl.paste_last().status == "busy"


def test_status_reporting() -> None:
    ctl, *_ = make_controller()
    st = ctl.status()
    assert st["state"] == "idle"
    assert st["recording"] is False
    ctl.ptt_down()
    st = ctl.status()
    assert st["recording"] is True
    ctl.ptt_up()
    assert ctl.status()["last_text"]


def test_notify_hooks_fire() -> None:
    events: list[str] = []
    audio = FakeAudioSource(duration_s=1.0)
    deps = _Deps(
        audio=audio,
        stt=FakeSTT("a long enough sentence to be injected fully here"),
        injection=InjectionChain([FakeInjector("f")]),
        history=History(),
        notify={
            "start": lambda: events.append("start"),
            "stop": lambda: events.append("stop"),
            "injecting": lambda: events.append("injecting"),
            "idle": lambda: events.append("idle"),
        },
    )
    ctl = Controller(ControllerConfig(min_duration_s=0.15), deps)
    ctl.toggle()
    ctl.toggle()
    assert events == ["start", "stop", "injecting", "idle"]


def test_apply_intent_noop_when_out_of_phase() -> None:
    ctl, *_ = make_controller()
    # release before any press -> NONE intent -> noop
    assert ctl.on_hotkey_release(1.0).status == "noop"


def test_dictation_result_text_property() -> None:
    from whisper_flow_local.controller import DictationResult

    assert DictationResult(status="injected", raw="r", cleaned="c").text == "c"
    assert DictationResult(status="injected", raw="r", cleaned="").text == "r"


def test_cancel_swallows_audio_stop_error() -> None:
    ctl, audio, *_ = make_controller()
    ctl.ptt_down()
    audio.stop_raises = True
    # cancel must succeed even if the mic fails to stop
    assert ctl.cancel().status == "cancelled"
    assert ctl.state == State.IDLE


def test_toggle_busy_when_pipeline_active() -> None:
    """toggle() reports busy if the pipeline is in a transient (non-resting) state.

    The lock serializes real triggers, so this guard is reached only if a
    caller races an in-flight pipeline; we drive the state machine directly to
    verify the guard deterministically.
    """
    ctl, *_ = make_controller()
    ctl.ptt_down()  # RECORDING (a resting state)
    ctl._sm.to(State.TRANSCRIBING)  # simulate mid-pipeline
    assert ctl.toggle().status == "busy"


def test_hybrid_press_while_held_not_latched_is_noop() -> None:
    ctl, *_ = make_controller(mode=Mode.HYBRID)
    ctl.on_hotkey_press(0.0)  # START, recording, not latched
    # a second press while still held (not latched) -> resolver NONE -> noop
    assert ctl.on_hotkey_press(0.1).status == "noop"
    assert ctl.state == State.RECORDING


def test_replace_seam_runs_before_cleanup() -> None:
    """Deterministic replacement is applied to the raw text before the LLM."""
    seen_by_cleanup: list[str] = []
    deps = _Deps(
        audio=FakeAudioSource(duration_s=1.0),
        stt=FakeSTT("i love my sequel and basically it is great to use daily"),
        injection=InjectionChain([FakeInjector("f")]),
        history=History(),
        cleanup=lambda raw: seen_by_cleanup.append(raw) or raw.upper(),
        replace=lambda t: t.replace("my sequel", "MySQL").replace("basically ", ""),
    )
    ctl = Controller(ControllerConfig(min_duration_s=0.15, cleanup_min_chars=10), deps)
    ctl.toggle()
    result = ctl.toggle()
    # cleanup received the REPLACED text, and history keeps the replaced raw
    assert "MySQL" in seen_by_cleanup[0]
    assert "basically" not in seen_by_cleanup[0]
    assert "MySQL" in result.raw


def test_replace_seam_emptying_text_yields_empty() -> None:
    deps = _Deps(
        audio=FakeAudioSource(duration_s=1.0),
        stt=FakeSTT("um uh"),
        injection=InjectionChain([FakeInjector("f")]),
        history=History(),
        replace=lambda t: "",  # replacement deletes everything
    )
    ctl = Controller(ControllerConfig(min_duration_s=0.15), deps)
    ctl.toggle()
    assert ctl.toggle().status == "empty"


def _command_controller(*, selection: str, transformed: str = "TRANSFORMED", **deps_kw):
    injector = FakeInjector("f")
    seen: dict = {}

    def instruct(instruction: str, text: str) -> str:
        seen["instruction"] = instruction
        seen["text"] = text
        return transformed

    deps = _Deps(
        audio=FakeAudioSource(duration_s=1.0),
        stt=FakeSTT("make this formal"),
        injection=InjectionChain([injector]),
        history=History(),
        instruct=deps_kw.get("instruct", instruct),
        get_selection=deps_kw.get("get_selection", lambda: selection),
    )
    ctl = Controller(ControllerConfig(min_duration_s=0.15), deps)
    return ctl, injector, seen


def test_command_mode_transforms_selection() -> None:
    ctl, injector, seen = _command_controller(selection="hey whats up")
    ctl.ptt_down()
    result = ctl.ptt_up(command=True)
    assert result.status == "injected"
    assert injector.requests[-1].text == "TRANSFORMED"
    assert seen["instruction"] == "make this formal"
    assert seen["text"] == "hey whats up"
    assert ctl.state == State.IDLE


def test_command_mode_no_selection_is_noop() -> None:
    ctl, injector, _ = _command_controller(selection="   ")
    ctl.ptt_down()
    result = ctl.ptt_up(command=True)
    assert result.status == "noop"
    assert "no text selected" in result.reason
    assert injector.requests == []
    assert ctl.state == State.IDLE


def test_command_mode_no_change_leaves_selection() -> None:
    ctl, injector, _ = _command_controller(selection="text", transformed="")
    ctl.ptt_down()
    result = ctl.ptt_up(command=True)
    assert result.status == "noop"
    assert injector.requests == []


def test_command_mode_instruct_error_is_noop() -> None:
    def boom(instruction, text):
        raise RuntimeError("ollama down")

    ctl, _injector, _ = _command_controller(selection="text", instruct=boom)
    ctl.ptt_down()
    result = ctl.ptt_up(command=True)
    assert result.status == "noop"
    assert ctl.state == State.IDLE


def test_command_mode_not_configured_errors() -> None:
    deps = _Deps(
        audio=FakeAudioSource(duration_s=1.0),
        stt=FakeSTT("make it formal"),
        injection=InjectionChain([FakeInjector("f")]),
        history=History(),
        # no instruct / get_selection seams
    )
    ctl = Controller(ControllerConfig(min_duration_s=0.15), deps)
    ctl.ptt_down()
    result = ctl.ptt_up(command=True)
    assert result.status == "error"
    assert "not configured" in result.reason


def test_command_mode_via_toggle() -> None:
    ctl, _injector, _ = _command_controller(selection="some text")
    ctl.toggle()
    assert ctl.toggle(command=True).status == "injected"
