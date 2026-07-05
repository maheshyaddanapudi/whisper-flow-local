"""Tests for audio-cue mapping and notify-hook wiring."""

from __future__ import annotations

from whisper_flow_local.ui.cues import CUES, make_cue_hooks


def test_cues_cover_start_and_stop() -> None:
    assert "start" in CUES
    assert "stop" in CUES


def test_make_cue_hooks_plays_distinct_cues() -> None:
    played: list[str] = []
    hooks = make_cue_hooks(played.append)
    assert set(hooks) == {"start", "stop"}
    hooks["start"]()
    hooks["stop"]()
    assert played == [CUES["start"], CUES["stop"]]
    assert played[0] != played[1]  # start and stop sound different
