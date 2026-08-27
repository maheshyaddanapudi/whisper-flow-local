"""Local IPC: a Unix-domain socket carrying newline-delimited JSON verbs.

This is how the ``whisper-flow`` CLI (and compositor keybindings on Wayland,
launchers, scripts) drive a running daemon: ``toggle``, ``ptt-down``,
``ptt-up``, ``cancel``, ``status``, ``paste-last``, ``paste-last-raw``. Solving
hotkeys, scripting and Wayland in one stroke (hyprvoice trait).

Single-instance ownership is enforced by the socket itself: a second daemon
cannot bind the same path (never by killing processes by name). The wire
protocol is pure and fully tested; the socket transport is tested over a real
loopback socket.
"""

from __future__ import annotations

import contextlib
import json
import os
import socket
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

Dispatch = Callable[[str, dict[str, Any]], dict[str, Any]]

VERBS = frozenset(
    {"toggle", "ptt-down", "ptt-up", "cancel", "status", "paste-last", "paste-last-raw", "ping"}
)


class IPCError(RuntimeError):
    """IPC transport or protocol error."""


@dataclass(frozen=True)
class Request:
    verb: str
    args: dict[str, Any]


def encode_request(verb: str, args: dict[str, Any] | None = None) -> bytes:
    return (json.dumps({"verb": verb, "args": args or {}}) + "\n").encode("utf-8")


def decode_request(line: bytes) -> Request:
    try:
        obj = json.loads(line.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise IPCError(f"bad request: {exc}") from exc
    if not isinstance(obj, dict) or "verb" not in obj:
        raise IPCError("request missing 'verb'")
    args = obj.get("args", {})
    if not isinstance(args, dict):
        raise IPCError("'args' must be an object")
    return Request(verb=str(obj["verb"]), args=args)


def encode_response(
    ok: bool, data: dict[str, Any] | None = None, error: str | None = None
) -> bytes:
    payload: dict[str, Any] = {"ok": ok}
    if data is not None:
        payload["data"] = data
    if error is not None:
        payload["error"] = error
    return (json.dumps(payload) + "\n").encode("utf-8")


def decode_response(line: bytes) -> dict[str, Any]:
    try:
        obj = json.loads(line.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise IPCError(f"bad response: {exc}") from exc
    if not isinstance(obj, dict) or "ok" not in obj:
        raise IPCError("malformed response")
    return obj


def default_socket_path() -> Path:
    """Runtime socket path (``$XDG_RUNTIME_DIR`` or a temp dir fallback)."""
    base = os.environ.get("XDG_RUNTIME_DIR")
    root = Path(base) if base else Path(os.environ.get("TMPDIR", "/tmp"))
    return root / "whisper-flow.sock"


def _recv_line(conn: socket.socket, limit: int = 1 << 20) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = conn.recv(4096)
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if b"\n" in chunk or total > limit:
            break
    return b"".join(chunks).split(b"\n", 1)[0]


class IPCServer:
    """Threaded Unix-socket server dispatching verbs to a handler."""

    def __init__(self, path: Path, dispatch: Dispatch) -> None:
        self._path = path
        self._dispatch = dispatch
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    @property
    def path(self) -> Path:
        return self._path

    def start(self) -> None:
        """Bind and serve. Raises IPCError if another daemon owns the socket."""
        if self._is_live():
            raise IPCError(f"another instance is already listening on {self._path}")
        # Stale socket file from a crashed daemon: safe to remove.
        with contextlib.suppress(FileNotFoundError):
            self._path.unlink()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(str(self._path))
        sock.listen(8)
        sock.settimeout(0.2)
        self._sock = sock
        self._stop.clear()
        self._thread = threading.Thread(target=self._serve, name="ipc-server", daemon=True)
        self._thread.start()

    def _is_live(self) -> bool:
        """True if a responsive daemon already owns the socket path."""
        if not self._path.exists():
            return False
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        probe.settimeout(0.2)
        try:
            probe.connect(str(self._path))
        except OSError:
            return False
        finally:
            probe.close()
        return True

    def _serve(self) -> None:
        assert self._sock is not None
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except TimeoutError:
                continue
            except OSError:  # pragma: no cover - socket closed during shutdown
                break
            with conn:
                self._handle(conn)

    def _handle(self, conn: socket.socket) -> None:
        line = _recv_line(conn)
        if not line:
            return
        try:
            req = decode_request(line)
            data = self._dispatch(req.verb, req.args)
            conn.sendall(encode_response(True, data=data))
        except Exception as exc:
            conn.sendall(encode_response(False, error=str(exc)))

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        if self._sock is not None:
            self._sock.close()
            self._sock = None
        with contextlib.suppress(FileNotFoundError):
            self._path.unlink()


def send(
    path: Path, verb: str, args: dict[str, Any] | None = None, *, timeout: float = 5.0
) -> dict[str, Any]:
    """Client: send one verb to the daemon and return the decoded response."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect(str(path))
    except OSError as exc:
        raise IPCError(f"daemon not running (no socket at {path}): {exc}") from exc
    try:
        sock.sendall(encode_request(verb, args))
        line = _recv_line(sock)
    except OSError as exc:
        raise IPCError(f"IPC transport error: {exc}") from exc
    finally:
        sock.close()
    if not line:
        raise IPCError("empty response from daemon")
    return decode_response(line)
