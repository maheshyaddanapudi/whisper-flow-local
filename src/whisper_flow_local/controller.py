"""The dictation controller: orchestration over the pipeline state machine.

Ties together recording intents, audio capture, STT, optional cleanup and
injection — all through interfaces, so this logic is tested end to end with
fakes. The real daemon supplies real hardware adapters and the threading; this
class contains the decisions.

Concurrency: a single lock serializes triggers so two hotkeys/IPC calls cannot
overlap a pipeline run. ``status`` reads the state without the lock so it is
always responsive.
"""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .audio import AudioSource
from .history import History
from .inject.base import AllInjectorsFailed, InjectionChain, InjectRequest
from .pipeline_state import State, StateMachine
from .recording import Intent, Mode, RecordingResolver
from .stt.base import STTBackend

# Cleanup seam: raw transcript -> cleaned transcript. None disables it (Phase 1).
CleanupFn = Callable[[str], str]
# Replacement seam: applies deterministic dictionary fixes to the transcript.
ReplaceFn = Callable[[str], str]


@dataclass
class DictationResult:
    status: str  # injected | discarded_short | empty | busy | started | noop | error
    raw: str = ""
    cleaned: str = ""
    backend: str | None = None
    reason: str | None = None

    @property
    def text(self) -> str:
        return self.cleaned or self.raw


@dataclass
class ControllerConfig:
    mode: Mode = Mode.HYBRID
    hold_threshold_s: float = 0.5
    min_duration_s: float = 0.15
    language: str | None = None
    initial_prompt: str | None = None
    auto_submit: bool = False
    trailing_space: bool = False
    cleanup_min_chars: int = 50


@dataclass
class _Deps:
    audio: AudioSource
    stt: STTBackend
    injection: InjectionChain
    history: History
    cleanup: CleanupFn | None = None
    replace: ReplaceFn | None = None
    on_state_change: Callable[[State], None] = lambda _s: None
    notify: dict[str, Callable[[], None]] = field(default_factory=dict)


class Controller:
    def __init__(self, config: ControllerConfig, deps: _Deps) -> None:
        self._cfg = config
        self._d = deps
        self._sm = StateMachine()
        self._resolver = RecordingResolver(config.mode, config.hold_threshold_s)
        self._history = deps.history
        self._lock = threading.RLock()

    # --- introspection ----------------------------------------------------
    @property
    def state(self) -> State:
        return self._sm.state

    def status(self) -> dict[str, Any]:
        last = self._history.last
        return {
            "state": self._sm.state.value,
            "recording": self._sm.state == State.RECORDING,
            "history_size": len(self._history),
            "last_text": last.text if last else "",
        }

    # --- hotkey path ------------------------------------------------------
    def on_hotkey_press(self, now: float) -> DictationResult:
        with self._lock:
            return self._apply_intent(self._resolver.press(now))

    def on_hotkey_release(self, now: float) -> DictationResult:
        with self._lock:
            return self._apply_intent(self._resolver.release(now))

    # --- IPC/scripting path ----------------------------------------------
    def toggle(self, *, clean: bool = True) -> DictationResult:
        with self._lock:
            if self._sm.state == State.IDLE:
                return self._start()
            if self._sm.state == State.RECORDING:
                return self._stop_and_process(clean=clean)
            return DictationResult(status="busy", reason=self._sm.state.value)

    def ptt_down(self) -> DictationResult:
        with self._lock:
            if self._sm.state == State.IDLE:
                return self._start()
            return DictationResult(status="busy", reason=self._sm.state.value)

    def ptt_up(self, *, clean: bool = True) -> DictationResult:
        with self._lock:
            if self._sm.state == State.RECORDING:
                return self._stop_and_process(clean=clean)
            return DictationResult(status="noop")

    def cancel(self) -> DictationResult:
        with self._lock:
            was_recording = self._sm.state == State.RECORDING
            if was_recording:
                # Stop the mic but throw the audio away.
                with contextlib.suppress(Exception):
                    self._d.audio.stop()
            aborted = self._sm.cancel()
            self._to_idle()
            return DictationResult(status="cancelled" if aborted else "noop")

    def paste_last(self, *, raw: bool = False) -> DictationResult:
        with self._lock:
            if self._sm.state != State.IDLE:
                return DictationResult(status="busy", reason=self._sm.state.value)
            last = self._history.last
            if last is None:
                return DictationResult(status="noop", reason="no history")
            text = last.raw if raw else last.text
            # Out-of-band replay: inject directly without a pipeline run.
            try:
                backend = self._do_inject(text)
            except AllInjectorsFailed as exc:
                return DictationResult(status="error", reason=str(exc))
            return DictationResult(
                status="injected", raw=last.raw, cleaned=last.cleaned, backend=backend
            )

    # --- pipeline ---------------------------------------------------------
    def _apply_intent(self, intent: Intent, *, clean: bool = True) -> DictationResult:
        if intent == Intent.START and self._sm.state == State.IDLE:
            return self._start()
        if intent == Intent.STOP and self._sm.state == State.RECORDING:
            return self._stop_and_process(clean=clean)
        return DictationResult(status="noop")

    def _start(self) -> DictationResult:
        self._sm.to(State.RECORDING)
        self._d.on_state_change(State.RECORDING)
        self._fire("start")
        self._d.audio.start()
        return DictationResult(status="started")

    def _stop_and_process(self, *, clean: bool = True) -> DictationResult:
        buffer = self._d.audio.stop()
        self._fire("stop")
        if buffer.duration_s < self._cfg.min_duration_s:
            self._sm.to(State.IDLE)
            self._to_idle()
            return DictationResult(status="discarded_short")

        self._sm.to(State.TRANSCRIBING)
        self._d.on_state_change(State.TRANSCRIBING)
        try:
            transcript = self._d.stt.transcribe(
                buffer,
                language=self._cfg.language,
                initial_prompt=self._cfg.initial_prompt,
            )
        except Exception as exc:
            self._sm.reset()
            self._to_idle()
            return DictationResult(status="error", reason=f"stt: {exc}")

        raw = transcript.text.strip()
        # Deterministic dictionary replacements run BEFORE the LLM so they are
        # reliable regardless of cleanup; the corrected text is what we keep.
        if self._d.replace is not None and raw:
            raw = self._d.replace(raw).strip()
        if not raw:
            self._sm.to(State.IDLE)
            self._to_idle()
            return DictationResult(status="empty")

        cleaned = self._run_cleanup(raw) if clean else ""
        return self._finish_inject(cleaned or raw, raw, cleaned)

    def _run_cleanup(self, raw: str) -> str:
        if self._d.cleanup is None or len(raw) < self._cfg.cleanup_min_chars:
            return ""
        self._sm.to(State.CLEANING)
        self._d.on_state_change(State.CLEANING)
        self._fire("cleaning")
        try:
            return self._d.cleanup(raw)
        except Exception:
            return ""

    def _finish_inject(self, text: str, raw: str, cleaned: str) -> DictationResult:
        """Inject a freshly-produced dictation, updating state and history."""
        self._sm.to(State.INJECTING)  # legal from TRANSCRIBING or CLEANING
        self._d.on_state_change(State.INJECTING)
        self._fire("injecting")
        try:
            backend = self._do_inject(text)
        except AllInjectorsFailed as exc:
            self._sm.reset()
            self._to_idle()
            return DictationResult(status="error", raw=raw, cleaned=cleaned, reason=str(exc))
        self._history.add(raw, cleaned)
        self._sm.to(State.IDLE)
        self._to_idle()
        return DictationResult(status="injected", raw=raw, cleaned=cleaned, backend=backend)

    def _do_inject(self, text: str) -> str:
        """Run the injection chain; return the backend used or raise."""
        req = InjectRequest(
            text=text,
            auto_submit=self._cfg.auto_submit,
            trailing_space=self._cfg.trailing_space,
        )
        return self._d.injection.inject(req)

    def _to_idle(self) -> None:
        self._resolver.reset()
        self._d.on_state_change(State.IDLE)
        self._fire("idle")

    def _fire(self, event: str) -> None:
        cb = self._d.notify.get(event)
        if cb is not None:
            cb()
