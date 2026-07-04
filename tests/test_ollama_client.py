"""Tests for the stdlib Ollama client, using the mock server fixture."""

from __future__ import annotations

import pytest

from whisper_flow_local.cleanup.ollama import OllamaStatus, has_model, list_models, probe


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
