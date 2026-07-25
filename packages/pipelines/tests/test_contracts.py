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

        self.assertEqual(
            result,
            {
                "is_relevant": False,
                "reasoning": "No explicit MVP entity markers found.",
            },
        )

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
                            "modality": "fact",
                            "relations_hint": [],
                        }
                    ]
                }
            ]
        )

        with self.assertRaisesRegex(ValueError, "must be one of"):
            await client.call_json("Extract facts", schema=FACT_EXTRACTION_SCHEMA)

    async def test_mock_extraction_supports_bold_markdown_markers(self):
        prompt = """Body:
**Decision:** Keep OpenAI as the future production provider.
- **Constraint:** Keep human review enabled by default.

Extract all relevant items:"""

        result = await MockLLMClient().call_json(
            prompt,
            schema=FACT_EXTRACTION_SCHEMA,
        )

        self.assertEqual(len(result["facts"]), 2)
        self.assertEqual(result["facts"][0]["type"], "Decision")
        self.assertEqual(result["facts"][1]["type"], "Constraint")


if __name__ == "__main__":
    unittest.main()
