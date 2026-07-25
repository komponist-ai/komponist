"""Tests for automatic Neo4j vector-index dimension migration."""

import unittest
from unittest.mock import AsyncMock, patch

from core.embeddings import EMBEDDING_DIMENSIONS
from core.schema import GraphSchema


class VectorIndexSchemaTests(unittest.IsolatedAsyncioTestCase):
    async def test_mismatched_index_is_recreated_and_bad_vectors_removed(self) -> None:
        responses = [
            [{
                "type": "VECTOR",
                "options": {"indexConfig": {"vector.dimensions": 1024}},
            }],
            [],
            [{"removed": 3}],
            [],
        ]

        with patch(
            "core.schema.GraphClient.run_query",
            new_callable=AsyncMock,
            side_effect=responses,
        ) as run_query:
            await GraphSchema.ensure_vector_index()

        queries = [call.args[0] for call in run_query.await_args_list]
        self.assertTrue(any("DROP INDEX entity_embedding" in query for query in queries))
        self.assertTrue(any("REMOVE entity.embedding" in query for query in queries))
        self.assertTrue(any(
            f"`vector.dimensions`: {EMBEDDING_DIMENSIONS}" in query
            for query in queries
        ))

    async def test_matching_index_is_left_in_place(self) -> None:
        responses = [
            [{
                "type": "VECTOR",
                "options": {
                    "indexConfig": {
                        "vector.dimensions": EMBEDDING_DIMENSIONS,
                    }
                },
            }],
            [],
        ]

        with patch(
            "core.schema.GraphClient.run_query",
            new_callable=AsyncMock,
            side_effect=responses,
        ) as run_query:
            await GraphSchema.ensure_vector_index()

        queries = [call.args[0] for call in run_query.await_args_list]
        self.assertFalse(any("DROP INDEX" in query for query in queries))


if __name__ == "__main__":
    unittest.main()
