"""
Brain Import

Import a Komponist export file into the context graph.
"""

import yaml
from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import uuid4

from .graph import GraphClient
from .embeddings import embed, combine_for_embedding


async def import_brain(
    export_data: Dict[str, Any],
    org_id: Optional[str] = None,
    mode: str = "merge"
) -> Dict[str, Any]:
    """
    Import brain data from an export structure.

    Args:
        export_data: Export data (from YAML or dict)
        org_id: Override org_id (uses export's if not provided)
        mode: Import mode - 'merge' (default), 'replace', or 'skip_existing'

    Returns:
        Import summary
    """
    # Validate export structure
    if "komponist_export" not in export_data:
        raise ValueError("Invalid export format: missing komponist_export header")

    export_meta = export_data["komponist_export"]
    version = export_meta.get("version", "1.0")

    if version not in ["1.0"]:
        raise ValueError(f"Unsupported export version: {version}")

    # Use provided org_id or fall back to export's
    target_org = org_id or export_meta.get("org_id")
    if not target_org:
        raise ValueError("No org_id provided and none in export")

    # Track stats
    stats = {
        "entities_imported": 0,
        "entities_skipped": 0,
        "entities_updated": 0,
        "relationships_imported": 0,
        "workpacks_imported": 0,
        "evidence_imported": 0,
        "errors": []
    }

    # ID mapping for relationships (old_id -> new_id)
    id_map: Dict[str, str] = {}

    # Import entities
    entities = export_data.get("entities", [])

    for entity in entities:
        try:
            old_id = entity.get("id")

            # Check if entity exists
            existing = await GraphClient.run_query(
                """
                MATCH (e:Entity {org_id: $org_id})
                WHERE e.statement = $statement AND e.entity_type = $entity_type
                RETURN e.id as id
                """,
                {
                    "org_id": target_org,
                    "statement": entity.get("statement"),
                    "entity_type": entity.get("entity_type")
                }
            )

            if existing and mode == "skip_existing":
                # Skip, but record mapping
                id_map[old_id] = existing[0]["id"]
                stats["entities_skipped"] += 1
                continue

            elif existing and mode == "merge":
                # Update existing
                existing_id = existing[0]["id"]
                id_map[old_id] = existing_id

                await GraphClient.run_query(
                    """
                    MATCH (e:Entity {id: $id, org_id: $org_id})
                    SET e.detail = $detail,
                        e.status = $status,
                        e.confidence = $confidence,
                        e.updated_at = datetime()
                    """,
                    {
                        "id": existing_id,
                        "org_id": target_org,
                        "detail": entity.get("detail"),
                        "status": entity.get("status", "proposed"),
                        "confidence": entity.get("confidence", 0.5)
                    }
                )
                stats["entities_updated"] += 1

            else:
                # Create new entity
                new_id = f"{entity.get('entity_type', 'fact').lower()}-{uuid4().hex[:8]}"
                id_map[old_id] = new_id

                # Generate embedding if not provided
                embedding = entity.get("embedding")
                if not embedding:
                    text = combine_for_embedding(
                        entity.get("statement", ""),
                        entity.get("detail")
                    )
                    embedding = await embed(text)

                await GraphClient.run_query(
                    """
                    CREATE (e:Entity {
                        id: $id,
                        org_id: $org_id,
                        entity_type: $entity_type,
                        statement: $statement,
                        detail: $detail,
                        status: $status,
                        confidence: $confidence,
                        embedding: $embedding,
                        created_at: datetime(),
                        imported_at: datetime(),
                        import_source_id: $import_source_id
                    })
                    """,
                    {
                        "id": new_id,
                        "org_id": target_org,
                        "entity_type": entity.get("entity_type", "Fact"),
                        "statement": entity.get("statement"),
                        "detail": entity.get("detail"),
                        "status": entity.get("status", "proposed"),
                        "confidence": entity.get("confidence", 0.5),
                        "embedding": embedding,
                        "import_source_id": old_id
                    }
                )
                stats["entities_imported"] += 1

                # Import evidence for this entity
                for ev in entity.get("evidence", []):
                    if not ev:
                        continue

                    ev_id = f"ev-{uuid4().hex[:8]}"

                    await GraphClient.run_query(
                        """
                        MATCH (e:Entity {id: $entity_id, org_id: $org_id})
                        CREATE (ev:Evidence {
                            id: $ev_id,
                            org_id: $org_id,
                            source: $source,
                            reference: $reference,
                            url: $url,
                            excerpt: $excerpt,
                            source_date: $source_date,
                            created_at: datetime()
                        })
                        CREATE (e)-[:CITED_BY]->(ev)
                        """,
                        {
                            "entity_id": new_id,
                            "org_id": target_org,
                            "ev_id": ev_id,
                            "source": ev.get("source", "import"),
                            "reference": ev.get("reference"),
                            "url": ev.get("url"),
                            "excerpt": ev.get("excerpt"),
                            "source_date": ev.get("source_date")
                        }
                    )
                    stats["evidence_imported"] += 1

        except Exception as e:
            stats["errors"].append(f"Entity {entity.get('id')}: {str(e)}")

    # Import relationships
    relationships = export_data.get("relationships", [])

    for rel in relationships:
        try:
            source_id = id_map.get(rel.get("source"))
            target_id = id_map.get(rel.get("target"))

            if not source_id or not target_id:
                continue

            rel_type = rel.get("type", "RELATES_TO")
            score = rel.get("score", 0.5)

            await GraphClient.run_query(
                f"""
                MATCH (e1:Entity {{id: $source_id, org_id: $org_id}})
                MATCH (e2:Entity {{id: $target_id, org_id: $org_id}})
                MERGE (e1)-[r:{rel_type}]->(e2)
                SET r.score = $score, r.imported_at = datetime()
                """,
                {
                    "source_id": source_id,
                    "target_id": target_id,
                    "org_id": target_org,
                    "score": score
                }
            )
            stats["relationships_imported"] += 1

        except Exception as e:
            stats["errors"].append(f"Relationship: {str(e)}")

    # Import workpacks
    workpacks = export_data.get("workpacks", [])

    for wp in workpacks:
        try:
            wp_id = f"wp-{uuid4().hex[:8]}"

            await GraphClient.run_query(
                """
                CREATE (wp:WorkPack {
                    id: $id,
                    org_id: $org_id,
                    title: $title,
                    objective: $objective,
                    business_context: $business_context,
                    requirements: $requirements,
                    constraints: $constraints,
                    permissions: $permissions,
                    verification: $verification,
                    status: $status,
                    created_at: datetime(),
                    imported_at: datetime()
                })
                """,
                {
                    "id": wp_id,
                    "org_id": target_org,
                    "title": wp.get("title"),
                    "objective": wp.get("objective"),
                    "business_context": wp.get("business_context"),
                    "requirements": wp.get("requirements"),
                    "constraints": wp.get("constraints"),
                    "permissions": wp.get("permissions"),
                    "verification": wp.get("verification"),
                    "status": wp.get("status", "draft")
                }
            )

            # Link to entities
            for goal_old_id in wp.get("implements", []):
                goal_id = id_map.get(goal_old_id)
                if goal_id:
                    await GraphClient.run_query(
                        """
                        MATCH (wp:WorkPack {id: $wp_id, org_id: $org_id})
                        MATCH (g:Entity {id: $goal_id, org_id: $org_id})
                        MERGE (wp)-[:IMPLEMENTS]->(g)
                        """,
                        {"wp_id": wp_id, "goal_id": goal_id, "org_id": target_org}
                    )

            stats["workpacks_imported"] += 1

        except Exception as e:
            stats["errors"].append(f"WorkPack {wp.get('title')}: {str(e)}")

    return {
        "status": "complete" if not stats["errors"] else "partial",
        "org_id": target_org,
        "stats": stats
    }


def parse_export_yaml(yaml_content: str) -> Dict[str, Any]:
    """
    Parse YAML export content.

    Args:
        yaml_content: Raw YAML string

    Returns:
        Parsed export data
    """
    return yaml.safe_load(yaml_content)


async def import_brain_yaml(
    yaml_content: str,
    org_id: Optional[str] = None,
    mode: str = "merge"
) -> Dict[str, Any]:
    """
    Import brain from YAML string.

    Args:
        yaml_content: YAML export content
        org_id: Override org_id
        mode: Import mode

    Returns:
        Import summary
    """
    export_data = parse_export_yaml(yaml_content)
    return await import_brain(export_data, org_id=org_id, mode=mode)
