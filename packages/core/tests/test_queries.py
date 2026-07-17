"""
Unit tests for graph schema and core queries.

Requires Neo4j running (docker compose -f infra/docker-compose.dev.yml up -d)
"""

import pytest
import pytest_asyncio
from datetime import datetime
from typing import List

from core.graph import GraphClient
from core.schema import GraphSchema, seed_test_data
from core.queries import BrainQueries


# Test org ID
TEST_ORG = "test-org-queries"
ID_PREFIX = f"{TEST_ORG}:"


def _test_id(value: str) -> str:
    return f"{ID_PREFIX}{value}"


@pytest_asyncio.fixture(scope="module", loop_scope="module", autouse=True)
async def setup_teardown():
    """Setup: initialize DB and schema. Teardown: clean up test data."""
    # Setup
    GraphClient.initialize()
    await GraphSchema.apply_schema()
    await GraphClient.run_query(
        "MATCH (n) WHERE n.org_id = $org_id DETACH DELETE n",
        {"org_id": TEST_ORG},
    )
    await seed_test_data(org_id=TEST_ORG, id_prefix=ID_PREFIX)

    yield

    # Teardown: delete test org data
    await GraphClient.run_query(
        "MATCH (n) WHERE n.org_id = $org_id DETACH DELETE n",
        {"org_id": TEST_ORG}
    )
    await GraphClient.close()


@pytest.mark.asyncio(loop_scope="module")
async def test_schema_verification():
    """Test schema is correctly applied."""
    verification = await GraphSchema.verify_schema()

    assert "entity_id" in verification["constraints"]
    assert "evidence_id" in verification["constraints"]
    assert "entity_embedding" in verification["indexes"]
    assert "entity_text" in verification["indexes"]

    # Test data should be present
    assert verification["counts"]["entities"] >= 6
    assert verification["counts"]["evidence"] >= 5


@pytest.mark.asyncio(loop_scope="module")
async def test_active_decisions():
    """Test active decisions query (supersedes-aware)."""
    decisions = await BrainQueries.active_decisions(org_id=TEST_ORG)

    # Should have 3 decisions (dec-neo4j, dec-python, dec-auth-new)
    # Should NOT include dec-auth-old (superseded)
    assert len(decisions) == 3

    decision_ids = [d["id"] for d in decisions]
    assert _test_id("dec-neo4j") in decision_ids
    assert _test_id("dec-python") in decision_ids
    assert _test_id("dec-auth-new") in decision_ids
    assert _test_id("dec-auth-old") not in decision_ids

    # Each should have evidence
    for d in decisions:
        assert len(d["evidence"]) > 0


@pytest.mark.asyncio(loop_scope="module")
async def test_supersedes_chain():
    """Test supersedes chain query."""
    # Get chain for the new auth decision
    chain = await BrainQueries.supersedes_chain(
        decision_id=_test_id("dec-auth-old"),
        org_id=TEST_ORG
    )

    # Should have 2 decisions: old -> new
    assert len(chain) == 2
    assert chain[0]["id"] == _test_id("dec-auth-old")
    assert chain[0]["status"] == "superseded"
    assert chain[1]["id"] == _test_id("dec-auth-new")
    assert chain[1]["status"] == "confirmed"


@pytest.mark.asyncio(loop_scope="module")
async def test_context_expansion():
    """Test context expansion (1-2 hop neighborhood)."""
    # Start with the project entity
    expansion = await BrainQueries.context_expansion(
        org_id=TEST_ORG,
        seed_ids=[_test_id("proj-step2")],
        max_hops=2
    )

    assert len(expansion["seeds"]) > 0
    assert expansion["seeds"][0]["id"] == _test_id("proj-step2")

    # Should find neighbors via ADVANCES and AFFECTS relationships
    neighbor_ids = [n["id"] for n in expansion["neighbors"]]
    assert _test_id("goal-mvp") in neighbor_ids  # via ADVANCES
    assert _test_id("dec-auth-new") in neighbor_ids  # via AFFECTS

    # Should have evidence
    assert len(expansion["evidence"]) > 0


@pytest.mark.asyncio(loop_scope="module")
async def test_applicable_constraints():
    """Test applicable constraints (global + project-scoped)."""
    # Global constraints only (no project)
    constraints = await BrainQueries.applicable_constraints(org_id=TEST_ORG)

    assert len(constraints) >= 1
    constraint_ids = [c["id"] for c in constraints]
    assert _test_id("con-review") in constraint_ids

    # Should have evidence
    for c in constraints:
        assert len(c["evidence"]) > 0
        assert c["enforcement"] in ["block", "approve", None]


@pytest.mark.asyncio(loop_scope="module")
async def test_hybrid_search_fulltext():
    """Test hybrid search with fulltext only."""
    results = await BrainQueries.hybrid_search(
        org_id=TEST_ORG,
        query_text="Neo4j database",
        k=5
    )

    assert len(results) > 0

    # Should find the Neo4j decision
    statements = [r["statement"].lower() for r in results]
    assert any("neo4j" in s for s in statements)

    # Results should have scores
    for r in results:
        assert "score" in r
        assert r["score"] > 0


@pytest.mark.asyncio(loop_scope="module")
async def test_hybrid_search_with_type_filter():
    """Test hybrid search filtered by entity type."""
    results = await BrainQueries.hybrid_search(
        org_id=TEST_ORG,
        query_text="MVP",
        entity_types=["Goal"],
        k=5
    )

    assert len(results) > 0

    # All results should be goals
    for r in results:
        assert r["entity_type"] == "Goal"


@pytest.mark.asyncio(loop_scope="module")
async def test_entity_lifecycle():
    """Test entity status filtering."""
    # Create a proposed entity
    await GraphClient.run_query(
        """
        CREATE (e:Entity:Decision {
            id: $entity_id,
            org_id: $org_id,
            entity_type: 'Decision',
            statement: 'Test proposed decision',
            status: 'proposed',
            confidence: 'low',
            created_at: datetime(),
            updated_at: datetime()
        })
        """,
        {"org_id": TEST_ORG, "entity_id": _test_id("test-proposed")}
    )

    # Confirmed-only search should not include it
    confirmed_results = await BrainQueries.hybrid_search(
        org_id=TEST_ORG,
        query_text="proposed",
        status="confirmed",
        k=10
    )

    confirmed_ids = [r["id"] for r in confirmed_results]
    assert _test_id("test-proposed") not in confirmed_ids

    # Proposed search should find it
    proposed_results = await BrainQueries.hybrid_search(
        org_id=TEST_ORG,
        query_text="proposed",
        status="proposed",
        k=10
    )

    proposed_ids = [r["id"] for r in proposed_results]
    assert _test_id("test-proposed") in proposed_ids

    # Cleanup
    await GraphClient.run_query(
        "MATCH (e:Entity {id: $entity_id, org_id: $org_id}) DELETE e",
        {"org_id": TEST_ORG, "entity_id": _test_id("test-proposed")}
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
