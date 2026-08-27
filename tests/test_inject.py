"""Tests for injection: chain, prepare_text rules, clipboard, copy-only."""

from __future__ import annotations

import pytest

from fakes import FakeClipboard, FakeInjector
from whisper_flow_local.inject.base import (
    AllInjectorsFailed,
    InjectionChain,
    InjectRequest,
    prepare_text,
)
from whisper_flow_local.inject.clipboard import ClipboardInjector
from whisper_flow_local.inject.copyonly import CopyOnlyInjector


def test_prepare_text_defaults_no_enter() -> None:
    p = prepare_text(InjectRequest(text="hi"))
    assert p.text == "hi"
    assert p.send_enter is False


def test_prepare_text_trailing_space_and_autosubmit() -> None:
    p = prepare_text(InjectRequest(text="hi", trailing_space=True, auto_submit=True))
    assert p.text == "hi "
    assert p.send_enter is True


def test_chain_uses_first_available_success() -> None:
    a = FakeInjector("a", ok=True)
    b = FakeInjector("b", ok=True)
    chain = InjectionChain([a, b])
    assert chain.inject(InjectRequest(text="x")) == "a"
    assert len(a.requests) == 1
    assert len(b.requests) == 0


def test_chain_skips_unavailable_and_failed() -> None:
    unavailable = FakeInjector("u", avail=False)
    failing = FakeInjector("f", ok=False)
    good = FakeInjector("g", ok=True)
    chain = InjectionChain([unavailable, failing, good])
    assert chain.inject(InjectRequest(text="x")) == "g"
    assert len(unavailable.requests) == 0  # never tried
    assert len(failing.requests) == 1


def test_chain_all_fail_raises() -> None:
    chain = InjectionChain([FakeInjector("f", ok=False)])
    with pytest.raises(AllInjectorsFailed):
        chain.inject(InjectRequest(text="x"))


def test_chain_backends_property_is_copy() -> None:
    a = FakeInjector("a")
    chain = InjectionChain([a])
    got = chain.backends
    got.clear()
    assert len(chain.backends) == 1  # internal list not mutated


def test_copyonly_sets_clipboard() -> None:
    cb = FakeClipboard()
    inj = CopyOnlyInjector(cb)
    assert inj.available()
    assert inj.inject(InjectRequest(text="hello")) is True
    assert cb.get_text() == "hello"


def test_copyonly_empty_text_fails() -> None:
    assert CopyOnlyInjector(FakeClipboard()).inject(InjectRequest(text="")) is False


def test_copyonly_set_failure_returns_false() -> None:
    cb = FakeClipboard()
    cb.fail_set = True
    assert CopyOnlyInjector(cb).inject(InjectRequest(text="hi")) is False


def _instant_injector(cb: FakeClipboard, paste_calls: list, **kw) -> ClipboardInjector:
    return ClipboardInjector(
        cb,
        paste=lambda enter: paste_calls.append(enter),
        clock=lambda: 0.0,
        sleep=lambda _s: None,
        restore_delay_s=0.0,
        **kw,
    )


def test_clipboard_injects_and_restores() -> None:
    cb = FakeClipboard(initial="ORIGINAL")
    pastes: list[bool] = []
    inj = _instant_injector(cb, pastes)
    assert inj.inject(InjectRequest(text="dictated")) is True
    assert pastes == [False]  # pasted, no enter
    assert cb.get_text() == "ORIGINAL"  # snapshot restored
    # our text was on the clipboard at paste time
    assert "dictated" in cb.sets


def test_clipboard_autosubmit_sends_enter() -> None:
    cb = FakeClipboard()
    pastes: list[bool] = []
    inj = _instant_injector(cb, pastes)
    inj.inject(InjectRequest(text="dictated", auto_submit=True))
    assert pastes == [True]


def test_clipboard_empty_text_fails() -> None:
    assert _instant_injector(FakeClipboard(), []).inject(InjectRequest(text="")) is False


def test_clipboard_read_failure_falls_through() -> None:
    cb = FakeClipboard()
    cb.fail_get = True
    assert _instant_injector(cb, []).inject(InjectRequest(text="hi")) is False


def test_clipboard_set_failure_restores_and_fails() -> None:
    cb = FakeClipboard(initial="ORIG")
    cb.fail_set = True
    inj = _instant_injector(cb, [])
    assert inj.inject(InjectRequest(text="hi")) is False


def test_clipboard_set_not_confirmed_times_out() -> None:
    # A clipboard whose set silently does nothing: wait loop must time out.
    class StuckClipboard(FakeClipboard):
        def set_text(self, text: str) -> None:
            pass  # never actually stores

    times = iter([0.0, 0.5, 1.0, 3.0])
    cb = StuckClipboard(initial="ORIG")
    inj = ClipboardInjector(
        cb,
        paste=lambda enter: None,
        clock=lambda: next(times),
        sleep=lambda _s: None,
        timeout_s=2.0,
        restore_delay_s=0.0,
    )
    assert inj.inject(InjectRequest(text="hi")) is False


def test_clipboard_availability_hook() -> None:
    inj = _instant_injector(FakeClipboard(), [], available=lambda: False)
    assert inj.available() is False


def test_clipboard_restore_delay_sleeps() -> None:
    cb = FakeClipboard(initial="ORIG")
    slept: list[float] = []
    inj = ClipboardInjector(
        cb,
        paste=lambda enter: None,
        clock=lambda: 0.0,
        sleep=lambda s: slept.append(s),
        restore_delay_s=0.05,
    )
    assert inj.inject(InjectRequest(text="hi")) is True
    assert 0.05 in slept
