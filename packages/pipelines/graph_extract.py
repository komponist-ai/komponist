"""
Knowledge Graph Extraction

Simple, direct extraction of entities and relationships from source content.
Uses a single LLM call to extract both nodes and edges.
"""

import sys
sys.path.append("../../packages")

from typing import Dict, Any, List, Optional
from uuid import uuid4
from datetime import datetime

from core.llm import get_llm
from core.graph import GraphClient
from core.models import SourceItem


async def extract_graph(source_item: SourceItem) -> Dict[str, Any]:
    """
    Extract a knowledge graph from a source item.

    Returns entities (nodes) and relationships (edges) in one pass.
    """
    llm = get_llm()

    system_prompt = """You are a knowledge graph extractor. Extract entities and relationships from the given text.

ENTITIES are things like:
- Person: people mentioned by name
- Concept: ideas, topics, themes
- Fact: specific pieces of information
- Decision: choices that were made
- Goal: objectives or targets
- Project: work efforts or initiatives
- Tool: software, technologies, methods
- Location: places
- Organization: companies, teams, groups
- Event: things that happened

RELATIONSHIPS connect entities:
- RELATES_TO: general connection
- PART_OF: X is part of Y
- USES: X uses Y
- CREATED_BY: X was created by Y
- AFFECTS: X affects Y
- DEPENDS_ON: X depends on Y
- PRECEDED_BY: X came after Y
- LEADS_TO: X leads to Y

Return JSON:
{
  "entities": [
    {"id": "e1", "type": "Person", "name": "Alice", "description": "Team lead"},
    {"id": "e2", "type": "Decision", "name": "Use React", "description": "Decided to use React for frontend"}
  ],
  "relationships": [
    {"source": "e1", "target": "e2", "type": "CREATED_BY", "description": "Alice made this decision"}
  ]
}

Rules:
1. Use short IDs like e1, e2, e3
2. Name should be concise (2-5 words)
3. Description should be one sentence
4. Extract ALL meaningful entities and relationships
5. If nothing meaningful, return {"entities": [], "relationships": []}
"""

    prompt = f"""Extract the knowledge graph from this content:

Title: {source_item.title}
Source: {source_item.source}

Content:
{source_item.body[:6000]}

Return the entities and relationships as JSON:"""

    try:
        result = await llm.call_json(
            prompt=prompt,
            system=system_prompt,
            max_tokens=4000
        )

        entities = result.get("entities", [])
        relationships = result.get("relationships", [])

        print(f"[GraphExtract] Extracted {len(entities)} entities, {len(relationships)} relationships from {source_item.title[:40]}")

        return {
            "entities": entities,
            "relationships": relationships,
            "source": source_item
        }

    except Exception as e:
        print(f"[GraphExtract] Error: {e}")
        return {
            "entities": [],
            "relationships": [],
            "source": source_item,
            "error": str(e)
        }


async def persist_graph(
    extraction: Dict[str, Any],
    org_id: str,
    auto_confirm: bool = True
) -> Dict[str, Any]:
    """
    Persist extracted graph to Neo4j.

    Creates entity nodes and relationship edges.

    Args:
        extraction: Extracted entities and relationships
        org_id: Organization ID
        auto_confirm: If True, set status to 'confirmed'. If False, set to 'proposed'.
    """
    source_item = extraction["source"]
    entities = extraction.get("entities", [])
    relationships = extraction.get("relationships", [])

    # Determine status based on auto_confirm setting
    entity_status = "confirmed" if auto_confirm else "proposed"

    if not entities:
        return {"entities_created": 0, "relationships_created": 0}

    # Map temp IDs to real UUIDs
    id_map = {}
    created_entities = []
    created_relationships = []

    # Create evidence node for this source
    evidence_id = str(uuid4())
    evidence_query = """
    CREATE (ev:Evidence {
        id: $id,
        org_id: $org_id,
        source: $source,
        reference: $reference,
        url: $url,
        title: $title,
        created_at: datetime()
    })
    """
    await GraphClient.run_query(evidence_query, {
        "id": evidence_id,
        "org_id": org_id,
        "source": str(source_item.source.value) if hasattr(source_item.source, 'value') else str(source_item.source),
        "reference": source_item.reference,
        "url": source_item.url or "",
        "title": source_item.title
    })

    # Create entity nodes
    for entity in entities:
        temp_id = entity.get("id", str(uuid4()))
        real_id = str(uuid4())
        id_map[temp_id] = real_id

        entity_type = entity.get("type", "Concept")
        name = entity.get("name", "Unknown")
        description = entity.get("description", "")

        # Create entity with type as additional label
        query = f"""
        CREATE (e:Entity:{entity_type} {{
            id: $id,
            org_id: $org_id,
            entity_type: $entity_type,
            name: $name,
            statement: $name,
            detail: $description,
            status: $status,
            confidence: 'medium',
            created_at: datetime()
        }})
        WITH e
        MATCH (ev:Evidence {{id: $evidence_id}})
        CREATE (e)-[:CITED_BY]->(ev)
        RETURN e.id as id
        """

        try:
            result = await GraphClient.run_query(query, {
                "id": real_id,
                "org_id": org_id,
                "entity_type": entity_type,
                "name": name,
                "description": description,
                "evidence_id": evidence_id,
                "status": entity_status
            })
            created_entities.append(real_id)
        except Exception as e:
            print(f"[GraphExtract] Failed to create entity {name}: {e}")

    # Create relationships
    for rel in relationships:
        source_temp = rel.get("source")
        target_temp = rel.get("target")
        rel_type = rel.get("type", "RELATES_TO").upper().replace(" ", "_")
        description = rel.get("description", "")

        source_id = id_map.get(source_temp)
        target_id = id_map.get(target_temp)

        if not source_id or not target_id:
            continue

        # Create relationship
        query = f"""
        MATCH (s:Entity {{id: $source_id, org_id: $org_id}})
        MATCH (t:Entity {{id: $target_id, org_id: $org_id}})
        CREATE (s)-[r:{rel_type} {{description: $description, created_at: datetime()}}]->(t)
        RETURN type(r) as rel_type
        """

        try:
            result = await GraphClient.run_query(query, {
                "source_id": source_id,
                "target_id": target_id,
                "org_id": org_id,
                "description": description
            })
            if result:
                created_relationships.append({
                    "source": source_id,
                    "target": target_id,
                    "type": rel_type
                })
        except Exception as e:
            print(f"[GraphExtract] Failed to create relationship: {e}")

    print(f"[GraphExtract] Persisted {len(created_entities)} entities, {len(created_relationships)} relationships")

    return {
        "entities_created": len(created_entities),
        "relationships_created": len(created_relationships),
        "entity_ids": created_entities
    }


async def extract_and_persist(source_item: SourceItem, org_id: str, auto_confirm: bool = True) -> Dict[str, Any]:
    """
    Extract knowledge graph from source and persist to Neo4j.

    Args:
        source_item: The source content to extract from
        org_id: Organization ID
        auto_confirm: If True, entities are auto-confirmed. If False, they go to review queue.
    """
    extraction = await extract_graph(source_item)
    result = await persist_graph(extraction, org_id, auto_confirm=auto_confirm)
    return result


# Test
if __name__ == "__main__":
    import asyncio
    from core.models import SourceType

    async def test():
        test_item = SourceItem(
            org_id="test-org",
            source=SourceType.NOTION,
            kind="page",
            title="Engineering Team Decision: Use PostgreSQL",
            body="""
            After evaluating MongoDB, PostgreSQL, and MySQL, the engineering team decided to use PostgreSQL
            for our main database. Alice led the evaluation process and presented findings to the team.

            Key reasons:
            - Better support for complex queries
            - Strong ACID compliance
            - Bob from DevOps confirmed it integrates well with our Kubernetes setup

            This decision affects the Backend API project and the Data Pipeline project.
            We'll need to update the deployment scripts by end of Q2.
            """,
            author="alice",
            url="https://notion.so/test/123",
            reference="notion:123",
            source_date=datetime.utcnow()
        )

        GraphClient.initialize()
        result = await extract_and_persist(test_item, "test-org")
        print("Result:", result)
        await GraphClient.close()

    asyncio.run(test())
