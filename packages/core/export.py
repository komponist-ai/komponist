"""
Brain Export

Export the Komponist context graph to a portable YAML format.
"""

import yaml
from datetime import datetime
from typing import Optional, Dict, Any, List

from .graph import GraphClient


async def export_brain(
    org_id: str,
    include_embeddings: bool = False,
    include_rejected: bool = False
) -> Dict[str, Any]:
    """
    Export the brain context graph for an organization.

    Args:
        org_id: Organization ID to export
        include_embeddings: Include embedding vectors (large!)
        include_rejected: Include rejected entities

    Returns:
        Export data structure
    """
    # Build status filter
    status_filter = "e.status IN ['proposed', 'confirmed', 'superseded']"
    if include_rejected:
        status_filter = "true"

    # Export entities with their evidence
    entities_query = f"""
    MATCH (e:Entity {{org_id: $org_id}})
    WHERE {status_filter}
    OPTIONAL MATCH (e)-[:CITED_BY]->(ev:Evidence)
    RETURN
        e.id as id,
        e.entity_type as entity_type,
        e.statement as statement,
        e.detail as detail,
        e.status as status,
        e.confidence as confidence,
        e.created_at as created_at,
        e.confirmed_at as confirmed_at,
        {"e.embedding as embedding," if include_embeddings else ""}
        collect(DISTINCT ev{{
            .id,
            .source,
            .reference,
            .url,
            .excerpt,
            .source_date
        }}) as evidence
    ORDER BY e.created_at
    """

    entities = await GraphClient.run_query(
        entities_query,
        {"org_id": org_id}
    )

    # Export relationships between entities
    relationships_query = """
    MATCH (e1:Entity {org_id: $org_id})-[r]->(e2:Entity {org_id: $org_id})
    WHERE type(r) IN ['SUPERSEDES', 'AFFECTS', 'SUPPORTS', 'ADVANCES', 'CONSTRAINS', 'RELATES_TO']
    RETURN
        e1.id as source,
        type(r) as type,
        e2.id as target,
        r.score as score
    """

    relationships = await GraphClient.run_query(
        relationships_query,
        {"org_id": org_id}
    )

    # Export work packs
    workpacks_query = """
    MATCH (wp:WorkPack {org_id: $org_id})
    OPTIONAL MATCH (wp)-[:IMPLEMENTS]->(g:Entity)
    OPTIONAL MATCH (wp)-[:GOVERNED_BY]->(c:Entity)
    OPTIONAL MATCH (wp)-[:INFORMED_BY]->(i:Entity)
    RETURN
        wp.id as id,
        wp.title as title,
        wp.objective as objective,
        wp.business_context as business_context,
        wp.requirements as requirements,
        wp.constraints as constraints,
        wp.permissions as permissions,
        wp.verification as verification,
        wp.status as status,
        wp.created_at as created_at,
        collect(DISTINCT g.id) as implements,
        collect(DISTINCT c.id) as governed_by,
        collect(DISTINCT i.id) as informed_by
    """

    workpacks = await GraphClient.run_query(
        workpacks_query,
        {"org_id": org_id}
    )

    # Clean up evidence lists (remove nulls)
    for entity in entities:
        entity["evidence"] = [
            e for e in entity.get("evidence", [])
            if e and e.get("id")
        ]

    # Clean up workpack lists
    for wp in workpacks:
        wp["implements"] = [i for i in wp.get("implements", []) if i]
        wp["governed_by"] = [g for g in wp.get("governed_by", []) if g]
        wp["informed_by"] = [i for i in wp.get("informed_by", []) if i]

    # Build export structure
    export_data = {
        "komponist_export": {
            "version": "1.0",
            "exported_at": datetime.utcnow().isoformat() + "Z",
            "org_id": org_id,
            "include_embeddings": include_embeddings,
            "include_rejected": include_rejected,
            "counts": {
                "entities": len(entities),
                "relationships": len(relationships),
                "workpacks": len(workpacks)
            }
        },
        "entities": entities,
        "relationships": relationships,
        "workpacks": workpacks
    }

    return export_data


def export_to_yaml(export_data: Dict[str, Any]) -> str:
    """
    Convert export data to YAML string.

    Args:
        export_data: Export data from export_brain()

    Returns:
        YAML string
    """
    # Custom representer for datetime
    def datetime_representer(dumper, data):
        return dumper.represent_scalar('tag:yaml.org,2002:timestamp', data.isoformat())

    yaml.add_representer(datetime, datetime_representer)

    return yaml.dump(
        export_data,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False
    )


async def export_brain_yaml(
    org_id: str,
    include_embeddings: bool = False,
    include_rejected: bool = False
) -> str:
    """
    Export brain to YAML string.

    Args:
        org_id: Organization ID
        include_embeddings: Include embedding vectors
        include_rejected: Include rejected entities

    Returns:
        YAML string of the brain export
    """
    export_data = await export_brain(
        org_id=org_id,
        include_embeddings=include_embeddings,
        include_rejected=include_rejected
    )
    return export_to_yaml(export_data)
