"""Offline contract tests for OpenAI and mock AI clients."""

import math
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from core.embeddings import (
    EMBEDDING_DIMENSIONS,
    MockEmbeddingClient,
    OpenAIEmbeddingClient,
    get_embedding_client,
)
from core.llm import MockLLMClient, OpenAIClient, get_llm_client
from pipelines.contracts import CLASSIFICATION_SCHEMA, FACT_EXTRACTION_SCHEMA


TEST_SCHEMA = {
    "title": "test_items",
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {"type": "string"},
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


class FakeResponses:
    def __init__(self, output_text='{"items": []}'):
        self.output_text = output_text
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            id="resp_test",
            status="completed",
            output_text=self.output_text,
            output=[],
            usage=SimpleNamespace(input_tokens=12, output_tokens=4),
        )


class FakeEmbeddings:
    def __init__(self):
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        inputs = kwargs["input"] if isinstance(kwargs["input"], list) else [kwargs["input"]]
        data = [
            SimpleNamespace(index=index, embedding=[float(index)] * EMBEDDING_DIMENSIONS)
            for index, _text in reversed(list(enumerate(inputs)))
        ]
        return SimpleNamespace(data=data)


class OpenAIClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_responses_api_receives_strict_schema(self):
        responses = FakeResponses()
        fake_client = SimpleNamespace(responses=responses)
        client = OpenAIClient(api_key="test", client=fake_client)

        result = await client.call_json(
            prompt="Extract items",
            system="Return structured data.",
            schema=TEST_SCHEMA,
            max_tokens=200,
        )

        self.assertEqual(result, {"items": []})
        self.assertEqual(responses.kwargs["max_output_tokens"], 200)
        self.assertFalse(responses.kwargs["store"])
        self.assertNotIn("temperature", responses.kwargs)
        self.assertEqual(responses.kwargs["text"]["format"]["type"], "json_schema")
        self.assertTrue(responses.kwargs["text"]["format"]["strict"])
        self.assertEqual(responses.kwargs["text"]["format"]["schema"], TEST_SCHEMA)

    async def test_legacy_model_keeps_temperature(self):
        responses = FakeResponses(output_text="OK")
        client = OpenAIClient(
            api_key="test", client=SimpleNamespace(responses=responses)
        )

        await client.call("Hello", model="gpt-4.1", temperature=0.25)

        self.assertEqual(responses.kwargs["temperature"], 0.25)

    async def test_application_validates_structured_output(self):
        responses = FakeResponses(output_text='{"unexpected": true}')
        fake_client = SimpleNamespace(responses=responses)
        client = OpenAIClient(api_key="test", client=fake_client)

        with self.assertRaisesRegex(ValueError, "missing required field"):
            await client.call_json("Extract items", schema=TEST_SCHEMA, max_retries=1)


class MockClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_configuration_defaults_to_mock_mode(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsInstance(get_llm_client(), MockLLMClient)
            self.assertIsInstance(get_embedding_client(), MockEmbeddingClient)

    async def test_mock_llm_builds_schema_compatible_response(self):
        client = MockLLMClient()
        result = await client.call_json("Extract items", schema=TEST_SCHEMA)
        self.assertEqual(result, {"items": []})

    async def test_mock_llm_extracts_explicit_mvp_markers(self):
        prompt = """Title: Company context

Body:
Decision: Use Neo4j for the company brain.
Goal: Ship the local-documents vertical slice.
Note: This line must be ignored.
Constraint: Every extracted entity requires human review.
Project: Build Komponist MVP.

Extract all relevant items:"""
        client = MockLLMClient()

        classification = await client.call_json(
            prompt,
            schema=CLASSIFICATION_SCHEMA,
        )
        extraction = await client.call_json(
            prompt,
            schema=FACT_EXTRACTION_SCHEMA,
        )

        self.assertTrue(classification["is_relevant"])
        self.assertEqual(
            [fact["type"] for fact in extraction["facts"]],
            ["Decision", "Goal", "Constraint", "Project"],
        )
        self.assertTrue(all(fact["confidence"] == "high" for fact in extraction["facts"]))

    async def test_mock_embedding_is_deterministic_and_normalized(self):
        client = MockEmbeddingClient()
        first = await client.embed("Komponist")
        second = await client.embed("Komponist")
        different = await client.embed("Different text")

        self.assertEqual(first, second)
        self.assertNotEqual(first, different)
        self.assertEqual(len(first), EMBEDDING_DIMENSIONS)
        self.assertAlmostEqual(math.sqrt(sum(value * value for value in first)), 1.0)

    async def test_mock_mode_overrides_live_providers(self):
        with patch.dict(os.environ, {"KOMPONIST_AI_MODE": "mock"}, clear=False):
            self.assertIsInstance(get_llm_client("openai"), MockLLMClient)
            self.assertIsInstance(get_embedding_client("openai"), MockEmbeddingClient)

    async def test_unknown_ai_mode_fails_closed(self):
        with patch.dict(os.environ, {"KOMPONIST_AI_MODE": "typo"}, clear=False):
            with self.assertRaisesRegex(ValueError, "must be 'mock' or 'live'"):
                get_llm_client("openai")
            with self.assertRaisesRegex(ValueError, "must be 'mock' or 'live'"):
                get_embedding_client("openai")


class OpenAIEmbeddingClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_embedding_request_preserves_batch_order_and_dimensions(self):
        embeddings = FakeEmbeddings()
        fake_client = SimpleNamespace(embeddings=embeddings)
        client = OpenAIEmbeddingClient(api_key="test", client=fake_client)

        result = await client.embed_batch(["first", "second"])

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0][0], 0.0)
        self.assertEqual(result[1][0], 1.0)
        self.assertEqual(embeddings.kwargs["dimensions"], EMBEDDING_DIMENSIONS)
        self.assertEqual(embeddings.kwargs["encoding_format"], "float")


if __name__ == "__main__":
    unittest.main()
