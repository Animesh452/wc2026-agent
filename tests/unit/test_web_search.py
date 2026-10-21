import asyncio
import importlib
from types import SimpleNamespace

import pytest
from google.genai import errors

import gemini_client
import tools.web_search as web_search_module


def text_response(text: str):
    part = SimpleNamespace(text=text)
    return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[part]))])


def test_web_search_goes_through_retry_with_grounding(monkeypatch):
    calls = []

    async def fake_generate(contents, config):
        calls.append((contents, config))
        return text_response("Arsenal are top.")

    monkeypatch.setattr(web_search_module, "generate_with_retry", fake_generate)

    assert asyncio.run(web_search_module.web_search("premier league leader")) == "Arsenal are top."
    contents, config = calls[0]
    assert contents == "premier league leader"
    assert config.tools[0].google_search is not None


def test_web_search_returns_error_string_instead_of_raising(monkeypatch):
    async def failing_generate(contents, config):
        raise RuntimeError("quota exhausted")

    monkeypatch.setattr(web_search_module, "generate_with_retry", failing_generate)

    assert asyncio.run(web_search_module.web_search("q")) == "Search error: quota exhausted"


def test_head_to_head_awaits_web_search(monkeypatch):
    queries = []

    async def fake_web_search(query):
        queries.append(query)
        return "record"

    monkeypatch.setattr(web_search_module, "web_search", fake_web_search)

    assert asyncio.run(web_search_module.head_to_head("Brazil", "Argentina")) == "record"
    assert "Brazil" in queries[0] and "Argentina" in queries[0]


class FakeModels:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.models_used = []

    async def generate_content(self, model, contents, config):
        self.models_used.append(model)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_generate_with_retry_uses_model_and_retries_429(monkeypatch):
    busy = errors.APIError(429, {"error": {"code": 429, "message": "busy", "status": "RESOURCE_EXHAUSTED"}})
    models = FakeModels([busy, "ok"])
    monkeypatch.setattr(gemini_client, "client", SimpleNamespace(aio=SimpleNamespace(models=models)))
    monkeypatch.setattr(gemini_client, "MODEL", "test-model")

    async def no_sleep(seconds):
        pass

    monkeypatch.setattr(gemini_client.asyncio, "sleep", no_sleep)

    assert asyncio.run(gemini_client.generate_with_retry("q", None)) == "ok"
    assert models.models_used == ["test-model", "test-model"]


def test_generate_with_retry_does_not_retry_400(monkeypatch):
    bad = errors.APIError(400, {"error": {"code": 400, "message": "bad", "status": "INVALID_ARGUMENT"}})
    models = FakeModels([bad])
    monkeypatch.setattr(gemini_client, "client", SimpleNamespace(aio=SimpleNamespace(models=models)))

    with pytest.raises(errors.APIError):
        asyncio.run(gemini_client.generate_with_retry("q", None))
    assert len(models.models_used) == 1


def test_model_comes_from_gemini_model_env(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test-override")
    try:
        assert importlib.reload(gemini_client).MODEL == "gemini-test-override"
    finally:
        monkeypatch.undo()
        importlib.reload(gemini_client)
