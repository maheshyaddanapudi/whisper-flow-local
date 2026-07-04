"""Tests for IPC: wire protocol (pure) and socket transport (loopback)."""

from __future__ import annotations

import pytest

from whisper_flow_local import ipc
from whisper_flow_local.ipc import (
    IPCError,
    IPCServer,
    decode_request,
    decode_response,
    encode_request,
    encode_response,
    send,
)


def test_request_roundtrip() -> None:
    line = encode_request("toggle", {"x": 1})
    req = decode_request(line)
    assert req.verb == "toggle"
    assert req.args == {"x": 1}


def test_request_defaults_empty_args() -> None:
    req = decode_request(encode_request("status"))
    assert req.args == {}


def test_response_roundtrip_ok() -> None:
    obj = decode_response(encode_response(True, data={"state": "idle"}))
    assert obj["ok"] is True
    assert obj["data"]["state"] == "idle"


def test_response_roundtrip_error() -> None:
    obj = decode_response(encode_response(False, error="nope"))
    assert obj["ok"] is False
    assert obj["error"] == "nope"


@pytest.mark.parametrize("bad", [b"not json", b'{"noverb": 1}', b'{"verb":"x","args":5}'])
def test_decode_request_rejects_malformed(bad: bytes) -> None:
    with pytest.raises(IPCError):
        decode_request(bad)


@pytest.mark.parametrize("bad", [b"not json", b'{"nook": 1}'])
def test_decode_response_rejects_malformed(bad: bytes) -> None:
    with pytest.raises(IPCError):
        decode_response(bad)


def test_default_socket_path_uses_runtime_dir(monkeypatch) -> None:
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/run/user/1000")
    assert ipc.default_socket_path() == ipc.Path("/run/user/1000/whisper-flow.sock")


def test_default_socket_path_fallback(monkeypatch) -> None:
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setenv("TMPDIR", "/tmp")
    assert ipc.default_socket_path().name == "whisper-flow.sock"


def test_server_client_roundtrip(tmp_path) -> None:
    calls: list = []

    def dispatch(verb: str, args: dict) -> dict:
        calls.append((verb, args))
        return {"echo": verb, "args": args}

    sock = tmp_path / "wf.sock"
    server = IPCServer(sock, dispatch)
    server.start()
    try:
        resp = send(sock, "toggle", {"a": 1})
        assert resp["ok"] is True
        assert resp["data"]["echo"] == "toggle"
        assert calls == [("toggle", {"a": 1})]
    finally:
        server.stop()


def test_server_reports_handler_error(tmp_path) -> None:
    def dispatch(verb: str, args: dict) -> dict:
        raise ValueError("kaboom")

    sock = tmp_path / "wf.sock"
    server = IPCServer(sock, dispatch)
    server.start()
    try:
        resp = send(sock, "toggle")
        assert resp["ok"] is False
        assert "kaboom" in resp["error"]
    finally:
        server.stop()


def test_send_to_missing_daemon_raises(tmp_path) -> None:
    with pytest.raises(IPCError, match="daemon not running"):
        send(tmp_path / "absent.sock", "status")


def test_single_instance_second_start_refused(tmp_path) -> None:
    sock = tmp_path / "wf.sock"
    a = IPCServer(sock, lambda v, a: {})
    a.start()
    try:
        b = IPCServer(sock, lambda v, a: {})
        with pytest.raises(IPCError, match="already listening"):
            b.start()
    finally:
        a.stop()


def test_stale_socket_file_is_reclaimed(tmp_path) -> None:
    sock = tmp_path / "wf.sock"
    sock.write_bytes(b"")  # leftover file, nothing listening
    server = IPCServer(sock, lambda v, a: {"ok": 1})
    server.start()  # should reclaim the stale path
    try:
        assert send(sock, "ping")["ok"] is True
    finally:
        server.stop()


def test_server_path_property(tmp_path) -> None:
    sock = tmp_path / "wf.sock"
    assert IPCServer(sock, lambda v, a: {}).path == sock


def test_large_request_spans_multiple_reads(tmp_path) -> None:
    # A payload bigger than one recv() chunk exercises the read loop.
    sock = tmp_path / "wf.sock"
    server = IPCServer(sock, lambda v, a: {"got": len(a.get("pad", ""))})
    server.start()
    try:
        resp = send(sock, "toggle", {"pad": "x" * 5000})
        assert resp["ok"] is True
        assert resp["data"]["got"] == 5000
    finally:
        server.stop()


def test_send_empty_response_raises(tmp_path) -> None:
    import socket
    import threading

    sock_path = tmp_path / "wf.sock"
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(str(sock_path))
    srv.listen(1)

    def accept_and_close() -> None:
        conn, _ = srv.accept()
        conn.recv(4096)  # consume the request, then close without responding
        conn.close()

    t = threading.Thread(target=accept_and_close, daemon=True)
    t.start()
    try:
        with pytest.raises(IPCError, match="empty response"):
            send(sock_path, "status")
    finally:
        t.join(timeout=2)
        srv.close()


def test_send_transport_error_wrapped(tmp_path, monkeypatch) -> None:
    # A socket that connects but fails on sendall -> wrapped as IPCError.
    class BrokenSocket:
        def settimeout(self, _t) -> None: ...
        def connect(self, _addr) -> None: ...
        def sendall(self, _data) -> None:
            raise ConnectionResetError("peer reset")

        def close(self) -> None: ...

    monkeypatch.setattr(ipc.socket, "socket", lambda *a, **k: BrokenSocket())
    with pytest.raises(IPCError, match="transport error"):
        send(tmp_path / "any.sock", "status")


def test_stop_before_start_is_safe(tmp_path) -> None:
    # No thread, no socket, no file: stop() must handle all-None gracefully.
    server = IPCServer(tmp_path / "never.sock", lambda v, a: {})
    server.stop()


def test_stop_tolerates_missing_socket_file(tmp_path) -> None:
    sock = tmp_path / "wf.sock"
    server = IPCServer(sock, lambda v, a: {})
    server.start()
    sock.unlink()  # remove the socket file out from under stop()
    server.stop()  # must not raise (FileNotFoundError swallowed)
