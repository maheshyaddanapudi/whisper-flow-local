"""Tests for the serial dispatcher that keeps pipelines off input threads."""

from __future__ import annotations

import threading
import time

from whisper_flow_local.dispatch import SerialDispatcher


def test_runs_tasks_in_order_on_worker_thread() -> None:
    d = SerialDispatcher()
    d.start()
    ran: list[tuple[str, str]] = []
    caller = threading.current_thread().name
    assert d.submit(lambda: ran.append(("a", threading.current_thread().name)))
    assert d.submit(lambda: ran.append(("b", threading.current_thread().name)))
    d.stop()
    assert [name for name, _ in ran] == ["a", "b"]  # order preserved
    assert all(thread != caller for _, thread in ran)  # not on the caller's thread


def test_submit_before_start_is_dropped() -> None:
    d = SerialDispatcher()
    assert d.submit(lambda: None) is False


def test_submit_after_stop_is_dropped() -> None:
    d = SerialDispatcher()
    d.start()
    d.stop()
    assert d.submit(lambda: None) is False


def test_task_error_does_not_kill_the_worker() -> None:
    d = SerialDispatcher()
    d.start()
    ran: list[str] = []

    def boom() -> None:
        raise RuntimeError("pipeline failed")

    d.submit(boom)
    d.submit(lambda: ran.append("still alive"))
    d.stop()
    assert ran == ["still alive"]


def test_start_twice_is_idempotent_and_stop_twice_safe() -> None:
    d = SerialDispatcher()
    d.start()
    d.start()
    ran: list[int] = []
    d.submit(lambda: ran.append(1))
    d.stop()
    d.stop()  # second stop is a no-op
    assert ran == [1]


def test_slow_task_does_not_block_submission() -> None:
    """submit() returns immediately — the input callback must never wait."""
    d = SerialDispatcher()
    d.start()
    release = threading.Event()
    d.submit(release.wait)  # a "pipeline" that takes a while
    t0 = time.monotonic()
    assert d.submit(lambda: None)  # queued instantly behind the slow task
    assert time.monotonic() - t0 < 0.5
    release.set()
    d.stop()
