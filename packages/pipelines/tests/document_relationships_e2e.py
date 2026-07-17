"""Neo4j persistence check for relationships inferred within one document."""

import asyncio
from datetime import datetime, timezone

from core.graph import GraphClient
from core.models import SourceItem, SourceType
from pipelines.extract import persist_node


ORG_ID = "e2e-document-relationships"


def fact(entity_type: str, statement: str) -> dict:
    return {
        "type": entity_type,
        "statement": statement,
        "detail": statement,
        "excerpt": statement,
        "confidence": "high",
        "embedding": None,
        "source_fingerprint": f"e2e-{entity_type.lower()}",
        "relations_hint": [],
    }


async def run() -> None:
    GraphClient.initialize()
    await GraphClient.run_query(
        "MATCH (n {org_id: $org_id}) DETACH DELETE n",
        {"org_id": ORG_ID},
    )
    await GraphClient.run_query(
        """
        CREATE (:DocumentVersion {
            id: 'document-version-base', org_id: $org_id,
            title: 'Relationship persistence E2E draft v0',
            family_key: 'relationship persistence e2e',
            source_date: datetime('2026-01-01T00:00:00Z'),
            created_at: datetime('2026-01-01T00:00:00Z')
        })
        """,
        {"org_id": ORG_ID},
    )

    source_item = SourceItem(
        org_id=ORG_ID,
        source=SourceType.UPLOAD,
        kind="document_upload",
        title="Relationship persistence E2E",
        body="The Graph MVP project advances the connected graph goal.",
        author="Pipeline E2E",
        url="upload://relationships.md",
        reference="upload:relationships.md:e2e",
        source_date=datetime.now(timezone.utc),
    )
    state = {
        "source_item": source_item,
        "is_relevant": True,
        "extracted_facts": [],
        "dedupe_results": [
            {"fact": fact("Project", "Build the Graph MVP."), "action": "create", "relates_to": [], "resolved_relations": []},
            {"fact": fact("Goal", "Show a connected knowledge graph."), "action": "create", "relates_to": [], "resolved_relations": []},
        ],
        "final_entities": [],
        "relationships_created": 0,
        "error": None,
    }

    try:
        result = await persist_node(state)
        relationships = await GraphClient.run_query(
            """
            MATCH (project:Project {org_id: $org_id})-[r:ADVANCES]->(goal:Goal {org_id: $org_id})
            RETURN project.id AS source, goal.id AS target,
                   r.inferred AS inferred, r.inference_basis AS basis
            """,
            {"org_id": ORG_ID},
        )
        document_versions = await GraphClient.run_query(
            """
            MATCH (document:DocumentVersion {org_id: $org_id})-[:HAS_EVIDENCE]->(evidence:Evidence)
            RETURN document.title AS title, document.author AS author,
                   document.content_hash AS content_hash,
                   document.family_key AS family_key,
                   count(DISTINCT evidence) AS evidence_count
            """,
            {"org_id": ORG_ID},
        )
        revisions = await GraphClient.run_query(
            """
            MATCH (current:DocumentVersion {org_id: $org_id})-[revision:WAS_REVISION_OF]->(previous:DocumentVersion)
            RETURN current.title AS current, previous.id AS previous,
                   revision.method AS method, revision.confidence AS confidence
            """,
            {"org_id": ORG_ID},
        )

        assert len(result["final_entities"]) == 2, result
        assert result["relationships_created"] == 1, result
        assert relationships == [{
            "source": result["final_entities"][0],
            "target": result["final_entities"][1],
            "inferred": True,
            "basis": "same_document",
        }], relationships
        assert document_versions == [{
            "title": "Relationship persistence E2E",
            "author": "Pipeline E2E",
            "content_hash": document_versions[0]["content_hash"],
            "family_key": "relationship persistence e2e",
            "evidence_count": 2,
        }], document_versions
        assert len(document_versions[0]["content_hash"]) == 64, document_versions
        assert revisions == [{
            "current": "Relationship persistence E2E",
            "previous": "document-version-base",
            "method": "normalized_title",
            "confidence": 0.9,
        }], revisions
        print("Document relationship persistence E2E: OK")
    finally:
        await GraphClient.run_query(
            "MATCH (n {org_id: $org_id}) DETACH DELETE n",
            {"org_id": ORG_ID},
        )
        await GraphClient.close()


if __name__ == "__main__":
    asyncio.run(run())
