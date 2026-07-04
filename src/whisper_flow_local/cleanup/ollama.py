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
