"""Tests for explicit relationships between facts from one extraction batch."""

import unittest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone

from core.models import SourceItem, SourceType
from pipelines.extract import link_node


class SameBatchLinkTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_statement_hint_resolves_before_persistence(self) -> None:
        project_statement = "The Campus Forum project runs for six weeks."
        state = {
            "source_item": SourceItem(
                org_id="test-org",
                source=SourceType.UPLOAD,
                kind="document",
                title="plan.md",
                body="test",
                reference="upload:plan.md:test",
                url="",
                source_date=datetime.now(timezone.utc),
            ),
            "dedupe_results": [
                {
                    "action": "create",
                    "fact": {
                        "type": "Project",
                        "statement": project_statement,
                        "relations_hint": [],
                    },
                },
                {
                    "action": "create",
                    "fact": {
                        "type": "Constraint",
                        "statement": "The budget must not exceed €4,800.",
                        "relations_hint": [{
                            "relation": "CONSTRAINS",
                            "target_hint": project_statement,
                        }],
                    },
                },
            ],
        }

        with patch(
            "pipelines.extract.BrainQueries.hybrid_search",
            new_callable=AsyncMock,
        ) as search:
            result = await link_node(state)

        search.assert_not_awaited()
        relation = result["dedupe_results"][1]["resolved_relations"][0]
        self.assertEqual(relation["relation"], "CONSTRAINS")
        self.assertEqual(
            relation["target_id"],
            result["dedupe_results"][0]["entity_id"],
        )
        self.assertEqual(relation["resolution"], "same_batch_exact")


if __name__ == "__main__":
    unittest.main()
