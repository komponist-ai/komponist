"""Tests for exact-content extraction reuse and provenance cloning."""

import unittest
from datetime import datetime
from unittest.mock import AsyncMock, patch

from core.models import SourceItem, SourceType
from core.versioning import document_metadata
from pipelines.extract import reuse_identical_document


def uploaded_document(filename: str) -> SourceItem:
    body = "# Strategy\n\nDecision: Ship the reviewed context MVP.\n"
    return SourceItem(
        org_id="org-reuse",
        department_id="department-product",
        source=SourceType.UPLOAD,
        kind="markdown",
        title="Strategy",
        body=body,
        author="Test User",
        url=f"upload://{filename}",
        reference=f"upload:{filename}:same-content",
        source_date=datetime(2026, 7, 22, 12, 0, 0),
    )


class IdenticalDocumentReuseTests(unittest.IsolatedAsyncioTestCase):
    async def test_renamed_document_clones_provenance_without_extraction(self) -> None:
        source_item = uploaded_document("strategy-copy.md")
        graph_rows = [{
            "document_id": "doc-original",
            "evidence_id": "ev-original",
            "excerpt": "Decision: Ship the reviewed context MVP.",
            "entity_id": "decision-1",
        }]

        with patch(
            "pipelines.extract.GraphClient.run_query",
            new=AsyncMock(side_effect=[graph_rows, [], []]),
        ) as run_query:
            result = await reuse_identical_document(source_item)

        self.assertIsNotNone(result)
        self.assertTrue(result["reused_existing_extraction"])
        self.assertEqual(result["entities_created"], 0)
        self.assertTrue(result["provenance_created"])
        self.assertEqual(result["entity_ids"], ["decision-1"])
        self.assertEqual(result["reused_from_document_id"], "doc-original")
        self.assertEqual(run_query.await_count, 3)

        lookup_params = run_query.await_args_list[0].args[1]
        self.assertEqual(
            lookup_params["content_hash"],
            document_metadata(source_item)["content_hash"],
        )
        document_query = run_query.await_args_list[1].args[0]
        self.assertIn("WAS_DERIVED_FROM", document_query)
        evidence_params = run_query.await_args_list[2].args[1]
        self.assertEqual(evidence_params["entity_id"], "decision-1")
        self.assertEqual(evidence_params["reference"], source_item.reference)

    async def test_retry_of_same_document_only_reads_existing_claims(self) -> None:
        source_item = uploaded_document("strategy.md")
        document_id = document_metadata(source_item)["document_id"]
        graph_rows = [{
            "document_id": document_id,
            "evidence_id": "ev-existing",
            "excerpt": "Decision: Ship the reviewed context MVP.",
            "entity_id": "decision-1",
        }]

        with patch(
            "pipelines.extract.GraphClient.run_query",
            new=AsyncMock(return_value=graph_rows),
        ) as run_query:
            result = await reuse_identical_document(source_item)

        self.assertEqual(result["document_id"], document_id)
        self.assertTrue(result["reused_existing_extraction"])
        self.assertFalse(result["provenance_created"])
        self.assertEqual(run_query.await_count, 1)

    async def test_new_content_continues_to_model_pipeline(self) -> None:
        with patch(
            "pipelines.extract.GraphClient.run_query",
            new=AsyncMock(return_value=[]),
        ):
            result = await reuse_identical_document(uploaded_document("new.md"))

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
