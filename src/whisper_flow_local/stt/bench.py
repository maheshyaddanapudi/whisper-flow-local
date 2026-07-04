"""On-device model benchmark (`whisper-flow bench`).

Times each installed model on the user's own hardware against a sample clip and
prints a table sorted fastest-first — so model choice is grounded in measured
latency, not guesswork (hyprvoice's test-models trait). The *timing* is a thin
seam (it loads a real STT backend); the orchestration and table formatting are
pure and tested.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

# timer(model) -> wall-clock seconds to transcribe the sample; raises on failure.
Timer = Callable[[str], float]


@dataclass(frozen=True)
class BenchResult:
    model: str
    seconds: float
    ok: bool
    error: str = ""


def run_bench(models: list[str], timer: Timer) -> list[BenchResult]:
    """Time each model, returning results sorted fastest-first (failures last)."""
    results: list[BenchResult] = []
    for model in models:
        try:
            seconds = timer(model)
        except Exception as exc:
            results.append(BenchResult(model, 0.0, ok=False, error=str(exc)))
            continue
        results.append(BenchResult(model, seconds, ok=True))
    return sorted(results, key=lambda r: (not r.ok, r.seconds))


def format_table(results: list[BenchResult], audio_seconds: float) -> str:
    """Render a fixed-width results table with a real-time factor column."""
    if not results:
        return "no models to benchmark"
    width = max(len(r.model) for r in results)
    lines = [f"  {'model'.ljust(width)}   {'time':>8}   {'xRT':>7}   status"]
    for r in results:
        if r.ok:
            xrt = f"{audio_seconds / r.seconds:.1f}x" if r.seconds > 0 else "-"
            lines.append(f"  {r.model.ljust(width)}   {r.seconds:7.2f}s   {xrt:>7}   ok")
        else:
            lines.append(f"  {r.model.ljust(width)}   {'-':>8}   {'-':>7}   FAILED: {r.error}")
    fastest = next((r for r in results if r.ok), None)
    if fastest is not None:
        lines.append("")
        lines.append(f"  Recommended (fastest working): {fastest.model}")
    return "\n".join(lines)
