"""Tests for the cleanup prompt builder, including the adversarial contract."""

from __future__ import annotations

import pytest

from whisper_flow_local.cleanup.prompts import (
    GUARDRAIL,
    INSTRUCTION_GUARDRAIL,
    CleanupGoals,
    build_instruction_message,
    build_instruction_prompt,
    build_system_prompt,
)


def test_all_goals_enabled_by_default() -> None:
    assert CleanupGoals().enabled() == [
        "punctuation",
        "grammar",
        "fillers",
        "stutters",
        "lists",
    ]


def test_goal_order_is_deterministic() -> None:
    # Disabling some keeps canonical order (not config/dict order).
    goals = CleanupGoals(punctuation=False, grammar=True, fillers=True, stutters=False, lists=True)
    assert goals.enabled() == ["grammar", "fillers", "lists"]


def test_prompt_contains_guardrail_and_goal_lines() -> None:
    prompt = build_system_prompt(CleanupGoals())
    assert GUARDRAIL in prompt
    assert "filler words" in prompt
    assert prompt.startswith(GUARDRAIL)


def test_prompt_with_no_goals_is_just_guardrail() -> None:
    prompt = build_system_prompt(CleanupGoals(False, False, False, False, False))
    assert prompt == GUARDRAIL


def test_override_replaces_everything() -> None:
    assert build_system_prompt(CleanupGoals(), override="  just do X  ") == "just do X"


def test_empty_override_uses_compiled() -> None:
    assert build_system_prompt(CleanupGoals(), override="   ") == build_system_prompt(
        CleanupGoals()
    )


# --- Adversarial contract: the prompt must forbid the ways a small model
# "helps" instead of cleaning. These assertions pin the contract so a future
# prompt edit can't silently drop a guardrail.


@pytest.mark.parametrize(
    "forbidden",
    ["answer questions", "summarize", "translate", "add or remove", "only the cleaned"],
)
def test_guardrail_forbids_transformation(forbidden: str) -> None:
    prompt = build_system_prompt(CleanupGoals()).lower()
    assert forbidden in GUARDRAIL.lower() or forbidden in prompt


@pytest.mark.parametrize(
    "goals",
    [
        CleanupGoals(),
        CleanupGoals(False, False, False, False, False),
        CleanupGoals(True, False, True, False, True),
    ],
)
def test_prompt_is_plain_text_no_xml(goals: CleanupGoals) -> None:
    # Small models misread XML/angle-bracket tags; the prompt must stay plain.
    prompt = build_system_prompt(goals)
    assert "<" not in prompt
    assert ">" not in prompt


def test_guardrail_always_present_for_every_goal_subset() -> None:
    # Every single-goal prompt still carries the full guardrail.
    for i in range(5):
        flags = [False] * 5
        flags[i] = True
        prompt = build_system_prompt(CleanupGoals(*flags))
        assert GUARDRAIL in prompt


# --- command/instruction mode prompts ----------------------------------------


def test_instruction_prompt_default() -> None:
    assert build_instruction_prompt() == INSTRUCTION_GUARDRAIL
    assert "output only" in INSTRUCTION_GUARDRAIL.lower()


def test_instruction_prompt_override() -> None:
    assert build_instruction_prompt("  do X  ") == "do X"


def test_instruction_message_pairs_instruction_and_text() -> None:
    msg = build_instruction_message("make it formal", "hey whats up")
    assert "Instruction: make it formal" in msg
    assert "Text:\nhey whats up" in msg


def test_instruction_prompt_is_plain_text() -> None:
    assert "<" not in INSTRUCTION_GUARDRAIL
    assert ">" not in INSTRUCTION_GUARDRAIL
