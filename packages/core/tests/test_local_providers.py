"""Unit tests for local Ollama provider request/response compatibility."""

import pytest

from core.embeddings import OllamaEmbeddingClient
from core.llm import OllamaClient


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeAsyncClient:
    requests = []
    response_payload = {}

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def post(self, url, json):
        self.__class__.requests.append({"url": url, "json": json})
        return FakeResponse(self.__class__.response_payload)


class FakeHttpx:
    AsyncClient = FakeAsyncClient


@pytest.fixture(autouse=True)
def reset_fake_httpx():
    FakeAsyncClient.requests = []
    FakeAsyncClient.response_payload = {}


@pytest.mark.asyncio
async def test_ollama_json_call_uses_structured_output_schema(monkeypatch):
    monkeypatch.setenv("KOMPONIST_LLM_MODEL", "qwen3.5:9b")
    FakeAsyncClient.response_payload = {
        "response": '{"is_relevant": true}',
        "prompt_eval_count": 12,
        "eval_count": 5
    }
    schema = {
        "type": "object",
        "properties": {"is_relevant": {"type": "boolean"}},
        "required": ["is_relevant"],
        "additionalProperties": False
    }
    client = OllamaClient(base_url="http://ollama.test")
    client._httpx = FakeHttpx

    result = await client.call_json(
        prompt="Classify this",
        system="Return a classification",
        schema=schema
    )

    assert result == {"is_relevant": True}
    request = FakeAsyncClient.requests[0]
    assert request["url"] == "http://ollama.test/api/generate"
    assert request["json"]["model"] == "qwen3.5:9b"
    assert request["json"]["format"] == schema
    assert request["json"]["think"] is False
    assert request["json"]["system"] == "Return a classification"
    assert request["json"]["options"]["temperature"] == 0.0


@pytest.mark.asyncio
async def test_ollama_embeddings_use_batch_embed_endpoint(monkeypatch):
    monkeypatch.setenv("KOMPONIST_EMBEDDING_MODEL", "qwen3-embedding:0.6b")
    FakeAsyncClient.response_payload = {
        "embeddings": [[0.0] * 1024, [1.0] * 1024]
    }
    client = OllamaEmbeddingClient(base_url="http://ollama.test")
    client._httpx = FakeHttpx

    embeddings = await client.embed_batch(["first", "second"])

    assert len(embeddings) == 2
    assert all(len(embedding) == 1024 for embedding in embeddings)
    request = FakeAsyncClient.requests[0]
    assert request["url"] == "http://ollama.test/api/embed"
    assert request["json"] == {
        "model": "qwen3-embedding:0.6b",
        "input": ["first", "second"],
        "dimensions": 1024
    }


@pytest.mark.asyncio
async def test_ollama_embeddings_reject_wrong_dimensions():
    FakeAsyncClient.response_payload = {"embeddings": [[0.0] * 768]}
    client = OllamaEmbeddingClient(base_url="http://ollama.test")
    client._httpx = FakeHttpx

    with pytest.raises(ValueError, match="returned 768 dimensions; expected 1024"):
        await client.embed("wrong-sized vector")
