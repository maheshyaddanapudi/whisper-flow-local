"""macOS permission guidance.

The full experience needs three macOS permissions. Each is optional: without
them the app degrades cleanly (no Accessibility -> copy-only; no Input
Monitoring -> trigger via IPC/CLI). This module produces the guidance shown by
`doctor` on macOS. Reading the live grant *state* needs pyobjc on a real Mac and
is done there; the guidance text is pure and tested.
"""

from __future__ import annotations

# (permission, why it's needed, what happens without it)
MACOS_PERMISSIONS: tuple[tuple[str, str, str], ...] = (
    (
        "Microphone",
        "capture your voice",
        "dictation cannot record",
    ),
    (
        "Input Monitoring",
        "listen for the global hotkey",
        "trigger with `whisper-flow toggle` or a compositor keybind instead",
    ),
    (
        "Accessibility",
        "paste into the focused app",
        "falls back to copy-only (text on your clipboard; paste with Cmd+V)",
    ),
)


def describe(system: str) -> list[tuple[str, str, str]]:
    """Return the permission guidance rows for the platform ([] off macOS)."""
    if system != "Darwin":
        return []
    return list(MACOS_PERMISSIONS)


def render(system: str) -> str:
    """Human-readable permission guidance, or '' when not on macOS."""
    rows = describe(system)
    if not rows:
        return ""
    lines = [
        "macOS permissions (System Settings -> Privacy & Security):",
        "  Each is optional; the app degrades gracefully without it.",
    ]
    for name, why, without in rows:
        lines.append(f"  - {name}: to {why}. Without it: {without}.")
    return "\n".join(lines)
