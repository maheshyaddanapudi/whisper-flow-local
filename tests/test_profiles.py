"""Tests for per-app profile matching and loading."""

from __future__ import annotations

import pytest

from whisper_flow_local.profiles import (
    NO_PROFILE,
    ActiveProfile,
    Profile,
    ProfileError,
    load,
    match_profile,
)


def test_profile_matches_app() -> None:
    p = Profile(name="slack", app_pattern="slack")
    assert p.matches("Slack", "")
    assert not p.matches("Mail", "")


def test_profile_matches_title() -> None:
    p = Profile(name="gh", title_pattern=r"github\.com")
    assert p.matches("Firefox", "Pulls · github.com")
    assert not p.matches("Firefox", "example.com")


def test_profile_requires_both_when_both_given() -> None:
    p = Profile(name="x", app_pattern="firefox", title_pattern="gmail")
    assert p.matches("Firefox", "Gmail - inbox")
    assert not p.matches("Firefox", "github")  # title doesn't match


def test_profile_with_no_patterns_matches_nothing() -> None:
    assert not Profile(name="empty").matches("anything", "anything")


def test_match_profile_first_wins() -> None:
    profiles = [
        Profile(name="chat", app_pattern="slack", auto_submit=True),
        Profile(name="mail", app_pattern="mail", prompt_override="Be formal."),
    ]
    active = match_profile(profiles, "Slack")
    assert active.name == "chat"
    assert active.auto_submit is True


def test_match_profile_none_returns_no_profile() -> None:
    assert match_profile([Profile(name="x", app_pattern="slack")], "Terminal") is NO_PROFILE


def test_match_profile_carries_overrides() -> None:
    profiles = [Profile(name="term", app_pattern="term", cleanup=False)]
    active = match_profile(profiles, "iTerm")
    assert active == ActiveProfile(name="term", prompt_override="", cleanup=False, auto_submit=None)


# --- loading ------------------------------------------------------------------


def _write(tmp_path, text):
    p = tmp_path / "profiles.toml"
    p.write_text(text, encoding="utf-8")
    return p


def test_load_absent_is_empty() -> None:
    assert load(None) == []


def test_load_profiles(tmp_path) -> None:
    p = _write(
        tmp_path,
        """
        [[profile]]
        name = "slack"
        app = "slack"
        prompt = "Be casual."
        auto_submit = true

        [[profile]]
        name = "terminal"
        app = "term|iterm"
        cleanup = false
        """,
    )
    profiles = load(p)
    assert [x.name for x in profiles] == ["slack", "terminal"]
    assert profiles[0].auto_submit is True
    assert profiles[1].cleanup is False


def test_load_default_name(tmp_path) -> None:
    profiles = load(_write(tmp_path, "[[profile]]\napp = 'x'\n"))
    assert profiles[0].name == "profile-0"


def test_load_rejects_non_array(tmp_path) -> None:
    with pytest.raises(ProfileError, match="array of tables"):
        load(_write(tmp_path, "profile = 5"))


def test_load_rejects_non_table_entry(tmp_path) -> None:
    with pytest.raises(ProfileError, match="must be a table"):
        load(_write(tmp_path, "profile = [1, 2]"))


def test_load_rejects_bad_string_field(tmp_path) -> None:
    with pytest.raises(ProfileError, match="app must be a string"):
        load(_write(tmp_path, "[[profile]]\nname='x'\napp = 5\n"))


def test_load_rejects_bad_bool_field(tmp_path) -> None:
    with pytest.raises(ProfileError, match="cleanup must be"):
        load(_write(tmp_path, "[[profile]]\nname='x'\napp='a'\ncleanup = 'yes'\n"))


def test_load_rejects_invalid_toml(tmp_path) -> None:
    with pytest.raises(ProfileError, match="invalid TOML"):
        load(_write(tmp_path, "= = ="))
