"""Ollama client over the stdlib.

Phase 0 uses :func:`list_models` / :func:`probe` for the first-run dependency
report. Phase 2 adds the chat-based cleanup call. Using ``urllib`` (rather than
httpx) keeps the core dependency-free and makes the client trivial to test
against a stdlib ``http.server`` fixture.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class OllamaStatus:
    """Result of probing a local Ollama server."""

    reachable: bool
    host: str
    models: tuple[str, ...] = ()
    error: str | None = None


def list_models(host: str, *, timeout: float = 3.0) -> list[str]:
    """Return model names from ``GET /api/tags``.

    Raises :class:`OSError`/:class:`urllib.error.URLError` on connection issues;
    callers that want a non-throwing check should use :func:`probe`.
    """
    url = host.rstrip("/") + "/api/tags"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    models = payload.get("models", []) if isinstance(payload, dict) else []
    names: list[str] = []
    for entry in models:
        if isinstance(entry, dict) and isinstance(entry.get("name"), str):
            names.append(entry["name"])
    return names


def probe(host: str, *, timeout: float = 3.0) -> OllamaStatus:
    """Non-throwing reachability + model-list check for the dependency report."""
    try:
        names = list_models(host, timeout=timeout)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return OllamaStatus(reachable=False, host=host, error=str(exc))
    return OllamaStatus(reachable=True, host=host, models=tuple(names))


def has_model(status: OllamaStatus, model: str) -> bool:
    """True if ``model`` (with or without an explicit ``:latest`` tag) is present."""
    if not status.reachable:
        return False
    wanted = {model, model + ":latest"}
    if ":" not in model:
        wanted.add(model + ":latest")
    return any(name in wanted or name.split(":")[0] == model for name in status.models)


class OllamaError(RuntimeError):
    """Raised when a chat request to Ollama fails or times out."""


def chat(
    host: str,
    model: str,
    system: str,
    user: str,
    *,
    keep_alive: str = "30m",
    timeout: float = 8.0,
    temperature: float = 0.0,
) -> str:
    """Non-streaming ``POST /api/chat`` returning the assistant's text.

    Raises :class:`OllamaError` on any transport, HTTP, or decode failure (the
    caller falls back to the raw transcript — cleanup never gates).
    """
    url = host.rstrip("/") + "/api/chat"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "keep_alive": keep_alive,
        "options": {"temperature": temperature},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise OllamaError(f"ollama chat failed: {exc}") from exc
    message = body.get("message") if isinstance(body, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str):
        raise OllamaError("ollama chat returned no message content")
    return content


def chat_stream(
    host: str,
    model: str,
    system: str,
    user: str,
    on_token: Callable[[str], None],
    *,
    keep_alive: str = "30m",
    timeout: float = 8.0,
    temperature: float = 0.0,
) -> str:
    """Streaming ``POST /api/chat``: calls ``on_token`` per chunk, returns the full text.

    Ollama streams newline-delimited JSON, each line carrying a ``message.content``
    fragment. Raises :class:`OllamaError` on any transport/decode failure.
    """
    url = host.rstrip("/") + "/api/chat"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": True,
        "keep_alive": keep_alive,
        "options": {"temperature": temperature},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    parts: list[str] = []
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8").strip()
                if not line:
                    continue
                obj = json.loads(line)
                token = obj.get("message", {}).get("content", "") if isinstance(obj, dict) else ""
                if token:
                    parts.append(token)
                    on_token(token)
                if isinstance(obj, dict) and obj.get("done"):
                    break
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise OllamaError(f"ollama stream failed: {exc}") from exc
    return "".join(parts)
