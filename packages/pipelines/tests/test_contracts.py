"""Offline tests for extraction structured-output contracts."""

import unittest

from core.llm import MockLLMClient
from pipelines.contracts import CLASSIFICATION_SCHEMA, FACT_EXTRACTION_SCHEMA


class ExtractionContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_mock_classification_matches_contract(self):
        result = await MockLLMClient().call_json(
            "Classify this source",
            schema=CLASSIFICATION_SCHEMA,
        )

        self.assertEqual(result, {"is_relevant": False, "reasoning": ""})

    async def test_mock_extraction_matches_contract(self):
        result = await MockLLMClient().call_json(
            "Extract facts",
            schema=FACT_EXTRACTION_SCHEMA,
        )

        self.assertEqual(result, {"facts": []})

    async def test_contract_rejects_non_mvp_entity_type(self):
        client = MockLLMClient(
            responses=[
                {
                    "facts": [
                        {
                            "type": "Note",
                            "statement": "A note",
                            "detail": "",
                            "excerpt": "A note",
                            "confidence": "high",
                            "relations_hint": [],
                        }
                    ]
                }
            ]
        )

        with self.assertRaisesRegex(ValueError, "must be one of"):
            await client.call_json("Extract facts", schema=FACT_EXTRACTION_SCHEMA)


if __name__ == "__main__":
    unittest.main()
