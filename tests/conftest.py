"""Shared fixtures, including a stdlib mock Ollama server.

The mock server lets us test the real HTTP client and the full cleanup path
(including timeouts and mid-flight failure) with no external Ollama process.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest


@dataclass
class MockOllama:
    """Controllable in-process Ollama stand-in."""

    host: str
    models: list[str] = field(default_factory=lambda: ["gemma3:4b", "llama3.2:latest"])
    # If set, returned verbatim as the /api/tags "models" list (to test parsing
    # of malformed entries). Otherwise built from `models`.
    raw_models: list[object] | None = None
    # Map an input transcript to the "cleaned" output the model should return.
    chat_response: Callable[[str], str] = lambda text: text.strip()
    chat_delay: float = 0.0
    fail_tags: bool = False
    fail_chat: bool = False
    requests: list[dict] = field(default_factory=list)


def _make_handler(state: MockOllama) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: object) -> None:  # silence
            pass

        def _send(self, code: int, payload: dict) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path == "/api/tags":
                if state.fail_tags:
                    self._send(500, {"error": "boom"})
                    return
                models = (
                    state.raw_models
                    if state.raw_models is not None
                    else [{"name": n} for n in state.models]
                )
                self._send(200, {"models": models})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length).decode("utf-8") if length else "{}"
            body = json.loads(raw)
            state.requests.append({"path": self.path, "body": body})
            if self.path == "/api/chat":
                if state.fail_chat:
                    self._send(500, {"error": "boom"})
                    return
                if state.chat_delay:
                    time.sleep(state.chat_delay)
                messages = body.get("messages", [])
                user_text = messages[-1]["content"] if messages else ""
                out = state.chat_response(user_text)
                self._send(
                    200,
                    {
                        "message": {"role": "assistant", "content": out},
                        "done": True,
                    },
                )
            else:
                self._send(404, {"error": "not found"})

    return Handler


@pytest.fixture
def mock_ollama() -> Iterator[MockOllama]:
    server = HTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    port = server.server_address[1]
    state = MockOllama(host=f"http://127.0.0.1:{port}")
    server.RequestHandlerClass = _make_handler(state)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
