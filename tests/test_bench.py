"""Tests for the benchmark orchestration and table formatting."""

from __future__ import annotations

from whisper_flow_local.stt.bench import BenchResult, format_table, run_bench


def test_run_bench_sorts_fastest_first() -> None:
    times = {"slow": 3.0, "fast": 0.5, "mid": 1.5}
    results = run_bench(["slow", "fast", "mid"], lambda m: times[m])
    assert [r.model for r in results] == ["fast", "mid", "slow"]
    assert all(r.ok for r in results)


def test_run_bench_failures_sort_last() -> None:
    def timer(model: str) -> float:
        if model == "broken":
            raise RuntimeError("cannot load")
        return 1.0

    results = run_bench(["broken", "good"], timer)
    assert results[0].model == "good"
    assert results[-1].model == "broken"
    assert results[-1].ok is False
    assert "cannot load" in results[-1].error


def test_format_table_ok_rows() -> None:
    results = [BenchResult("fast", 0.5, ok=True), BenchResult("slow", 2.0, ok=True)]
    table = format_table(results, audio_seconds=10.0)
    assert "fast" in table
    assert "20.0x" in table  # 10s / 0.5s
    assert "Recommended (fastest working): fast" in table


def test_format_table_failed_row() -> None:
    results = [BenchResult("broken", 0.0, ok=False, error="boom")]
    table = format_table(results, audio_seconds=5.0)
    assert "FAILED: boom" in table
    assert "Recommended" not in table  # nothing worked


def test_format_table_zero_time_guard() -> None:
    table = format_table([BenchResult("m", 0.0, ok=True)], audio_seconds=5.0)
    assert "-" in table  # xRT shown as - when time is 0


def test_format_table_empty() -> None:
    assert format_table([], 1.0) == "no models to benchmark"
