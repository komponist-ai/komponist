"""Neo4j check for exact-content reuse across renamed uploads."""

import asyncio
from datetime import datetime, timezone

from core.graph import GraphClient
from core.models import SourceItem, SourceType
from pipelines.extract import persist_node, reuse_identical_document


ORG_ID = "e2e-identical-document-reuse"


def source(filename: str) -> SourceItem:
    return SourceItem(
        org_id=ORG_ID,
        department_id="product",
        source=SourceType.UPLOAD,
        kind="markdown",
        title=filename,
        body="# Strategy\n\nDecision: Ship the reviewed context MVP.\n",
        author="Pipeline E2E",
        url=f"upload://{filename}",
        reference=f"upload:{filename}:identical",
        source_date=datetime.now(timezone.utc),
    )


async def run() -> None:
    GraphClient.initialize()
    await GraphClient.run_query(
        "MATCH (n {org_id: $org_id}) DETACH DELETE n",
        {"org_id": ORG_ID},
    )
    original = source("strategy.md")
    fact = {
        "type": "Decision",
        "statement": "Ship the reviewed context MVP.",
        "detail": "Ship the reviewed context MVP.",
        "excerpt": "Decision: Ship the reviewed context MVP.",
        "confidence": "high",
        "embedding": None,
        "source_fingerprint": "e2e-identical-source",
        "relations_hint": [],
    }
    state = {
        "source_item": original,
        "is_relevant": True,
        "extracted_facts": [fact],
        "dedupe_results": [{
            "fact": fact,
            "action": "create",
            "relates_to": [],
            "resolved_relations": [],
        }],
        "final_entities": [],
        "relationships_created": 0,
        "error": None,
    }

    try:
        persisted = await persist_node(state)
        reused = await reuse_identical_document(source("renamed-strategy.md"))
        counts = await GraphClient.run_query(
            """
            MATCH (document:DocumentVersion {org_id: $org_id})
            OPTIONAL MATCH (document)-[:HAS_EVIDENCE]->(evidence:Evidence)
            WITH count(DISTINCT document) AS documents,
                 count(DISTINCT evidence) AS evidence
            MATCH (entity:Entity {org_id: $org_id})
            RETURN documents, evidence, count(DISTINCT entity) AS entities
            """,
            {"org_id": ORG_ID},
        )
        derived = await GraphClient.run_query(
            """
            MATCH (copy:DocumentVersion {org_id: $org_id})
                  -[relation:WAS_DERIVED_FROM]->
                  (original:DocumentVersion {org_id: $org_id})
            RETURN copy.title AS copy, original.title AS original,
                   relation.method AS method, relation.confidence AS confidence
            """,
            {"org_id": ORG_ID},
        )

        assert len(persisted["final_entities"]) == 1, persisted
        assert reused is not None and reused["reused_existing_extraction"], reused
        assert reused["entities_created"] == 0, reused
        assert reused["entity_ids"] == persisted["final_entities"], reused
        assert counts == [{"documents": 2, "evidence": 2, "entities": 1}], counts
        assert derived == [{
            "copy": "renamed-strategy.md",
            "original": "strategy.md",
            "method": "exact_content_hash",
            "confidence": 1.0,
        }], derived
        print("Identical document reuse E2E: OK")
    finally:
        await GraphClient.run_query(
            "MATCH (n {org_id: $org_id}) DETACH DELETE n",
            {"org_id": ORG_ID},
        )
        await GraphClient.close()


if __name__ == "__main__":
    asyncio.run(run())
