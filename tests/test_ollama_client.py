"""Tests for the stdlib Ollama client, using the mock server fixture."""

from __future__ import annotations

import pytest

from whisper_flow_local.cleanup.ollama import (
    OllamaError,
    OllamaStatus,
    chat_stream,
    has_model,
    list_models,
    probe,
)


def test_list_models(mock_ollama) -> None:
    names = list_models(mock_ollama.host)
    assert names == ["gemma3:4b", "llama3.2:latest"]


def test_probe_reachable(mock_ollama) -> None:
    status = probe(mock_ollama.host)
    assert status.reachable is True
    assert "gemma3:4b" in status.models
    assert status.error is None


def test_probe_unreachable() -> None:
    status = probe("http://127.0.0.1:1", timeout=0.5)
    assert status.reachable is False
    assert status.error is not None
    assert status.models == ()


def test_probe_server_error(mock_ollama) -> None:
    mock_ollama.fail_tags = True
    status = probe(mock_ollama.host)
    assert status.reachable is False


def test_has_model_variants() -> None:
    status = OllamaStatus(reachable=True, host="h", models=("gemma3:4b", "llama3.2:latest"))
    assert has_model(status, "gemma3:4b")
    assert has_model(status, "gemma3")  # bare name matches tagged
    assert has_model(status, "llama3.2")  # matches :latest
    assert not has_model(status, "qwen2.5")


def test_has_model_unreachable() -> None:
    assert not has_model(OllamaStatus(reachable=False, host="h"), "gemma3:4b")


def test_list_models_ignores_malformed_entries(mock_ollama) -> None:
    mock_ollama.models = []
    assert list_models(mock_ollama.host) == []


def test_list_models_raises_on_bad_host() -> None:
    with pytest.raises(OSError):
        list_models("http://127.0.0.1:1", timeout=0.5)


def test_list_models_filters_malformed_entries(mock_ollama) -> None:
    mock_ollama.raw_models = [
        {"name": "good:latest"},
        {"no_name": 1},  # dict without a name
        "just-a-string",  # not a dict
        {"name": 123},  # name not a string
    ]
    assert list_models(mock_ollama.host) == ["good:latest"]


# --- Streaming chat ----------------------------------------------------------


def test_chat_stream_emits_tokens_and_returns_full(mock_ollama) -> None:
    mock_ollama.chat_response = lambda text: "Cleaned up sentence."
    tokens: list[str] = []
    out = chat_stream(mock_ollama.host, "gemma3:4b", "system", "raw", tokens.append, timeout=2.0)
    # Each space-split chunk arrives via on_token; the return is the full text.
    assert out == "Cleaned up sentence."
    assert "".join(tokens) == "Cleaned up sentence."
    assert len(tokens) >= 2  # streamed in pieces, not one shot
    assert mock_ollama.requests[-1]["body"]["stream"] is True


def test_chat_stream_server_error_raises(mock_ollama) -> None:
    mock_ollama.fail_chat = True
    with pytest.raises(OllamaError, match="stream failed"):
        chat_stream(mock_ollama.host, "m", "s", "u", lambda _t: None, timeout=2.0)


def test_chat_stream_unreachable_raises() -> None:
    with pytest.raises(OllamaError):
        chat_stream("http://127.0.0.1:1", "m", "s", "u", lambda _t: None, timeout=0.5)


def test_chat_stream_should_abort_raises_promptly(mock_ollama) -> None:
    # Abort requested before the first chunk is consumed -> OllamaError, and
    # on_token never fires (the overlay's Stop control mid-refinement).
    mock_ollama.chat_response = lambda text: "many words that would stream slowly"
    tokens: list[str] = []
    with pytest.raises(OllamaError, match="aborted"):
        chat_stream(
            mock_ollama.host,
            "m",
            "s",
            "u",
            tokens.append,
            timeout=2.0,
            should_abort=lambda: True,
        )
    assert tokens == []


def test_chat_stream_handles_blank_lines_and_eof_end(mock_ollama) -> None:
    # A stream that emits a blank keep-alive line and ends via EOF (no done
    # marker) must still reconstruct the full text without hanging.
    mock_ollama.chat_response = lambda text: "Two words"
    mock_ollama.stream_eof_no_done = True
    tokens: list[str] = []
    out = chat_stream(mock_ollama.host, "m", "s", "u", tokens.append, timeout=2.0)
    assert out == "Two words"
    assert "".join(tokens) == "Two words"
