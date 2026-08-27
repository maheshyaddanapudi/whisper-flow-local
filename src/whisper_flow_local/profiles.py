"""Per-app tone/formatting profiles.

Detect the frontmost app at record-START (fixing the "capture context after STT"
bug where the window may have changed) and apply per-app overrides: a different
cleanup prompt (casual for chat, formal for email), cleanup on/off (terminals
and code editors want raw text, not prettified punctuation), and auto-submit
(press Enter in chat apps).

The matching logic is pure and fully tested; detecting the frontmost app is a
thin OS seam supplied by the daemon.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path


class ProfileError(ValueError):
    """Raised when a profiles file is malformed."""


@dataclass(frozen=True)
class Profile:
    """One app-matching rule and the overrides it applies."""

    name: str
    app_pattern: str = ""  # regex matched (case-insensitive) against the app name
    title_pattern: str = ""  # optional regex against the window title
    prompt_override: str = ""  # per-app cleanup system prompt ('' = default)
    cleanup: bool | None = None  # force cleanup on/off for this app
    auto_submit: bool | None = None  # press Enter after inject for this app

    def matches(self, app: str, title: str) -> bool:
        if self.app_pattern and not re.search(self.app_pattern, app, re.IGNORECASE):
            return False
        if self.title_pattern and not re.search(self.title_pattern, title, re.IGNORECASE):
            return False
        # A rule with neither pattern matches nothing (avoids an accidental
        # catch-all); at least one pattern must be present and satisfied.
        return bool(self.app_pattern or self.title_pattern)


@dataclass(frozen=True)
class ActiveProfile:
    """Resolved per-dictation overrides (all optional)."""

    name: str = ""
    prompt_override: str = ""
    cleanup: bool | None = None
    auto_submit: bool | None = None


NO_PROFILE = ActiveProfile()


def match_profile(profiles: list[Profile], app: str, title: str = "") -> ActiveProfile:
    """First profile whose patterns match, as an :class:`ActiveProfile`."""
    for profile in profiles:
        if profile.matches(app, title):
            return ActiveProfile(
                name=profile.name,
                prompt_override=profile.prompt_override,
                cleanup=profile.cleanup,
                auto_submit=profile.auto_submit,
            )
    return NO_PROFILE


def _bool_or_none(value: object, where: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ProfileError(f"{where} must be true or false")
    return value


def load(path: Path | None) -> list[Profile]:
    """Load profiles from TOML (empty list if absent)."""
    if path is None or not path.exists():
        return []
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ProfileError(f"{path}: invalid TOML: {exc}") from exc
    entries = raw.get("profile", [])
    if not isinstance(entries, list):
        raise ProfileError("[[profile]] must be an array of tables")
    profiles: list[Profile] = []
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ProfileError(f"profile #{i} must be a table")
        name = entry.get("name", f"profile-{i}")
        for key in ("app", "title", "prompt"):
            if key in entry and not isinstance(entry[key], str):
                raise ProfileError(f"profile '{name}': {key} must be a string")
        profiles.append(
            Profile(
                name=str(name),
                app_pattern=str(entry.get("app", "")),
                title_pattern=str(entry.get("title", "")),
                prompt_override=str(entry.get("prompt", "")),
                cleanup=_bool_or_none(entry.get("cleanup"), f"profile '{name}': cleanup"),
                auto_submit=_bool_or_none(
                    entry.get("auto_submit"), f"profile '{name}': auto_submit"
                ),
            )
        )
    return profiles
