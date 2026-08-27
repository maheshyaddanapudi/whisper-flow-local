"""Frontmost-app detection (thin per-OS seam).

Returns ``(app_name, window_title)`` for the currently focused app so the
profile matcher can pick a per-app profile at record-start. Each OS path imports
its native library lazily; on failure it returns empty strings (no profile
matches, so behavior falls back to the global config). Verified on the target
machines, not in CI — the matching logic in ``profiles.py`` is what's tested.
"""

from __future__ import annotations

import platform


def detect() -> tuple[str, str]:
    """Best-effort (app_name, window_title); ("", "") if unavailable."""
    system = platform.system()
    try:
        if system == "Darwin":
            return _detect_macos()
        if system == "Windows":
            return _detect_windows()
        if system == "Linux":
            return _detect_linux()
    except Exception:
        return ("", "")
    return ("", "")


def _detect_macos() -> tuple[str, str]:  # pragma: no cover - macOS seam
    from AppKit import NSWorkspace

    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    name = str(app.localizedName()) if app is not None else ""
    return (name, "")


def _detect_windows() -> tuple[str, str]:  # pragma: no cover - Windows seam
    import ctypes

    user32 = ctypes.windll.user32  # type: ignore[attr-defined]  # Windows-only
    hwnd = user32.GetForegroundWindow()
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return ("", buf.value)


def _detect_linux() -> tuple[str, str]:  # pragma: no cover - Linux seam
    import shutil
    import subprocess

    if not shutil.which("xdotool"):
        return ("", "")
    title = subprocess.run(
        ["xdotool", "getactivewindow", "getwindowname"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    return ("", title)
