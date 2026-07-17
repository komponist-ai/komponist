"""
Extraction Pipeline

LangGraph state machine: SourceItem -> proposed entities in the graph.

Pipeline: classify -> extract -> embed -> dedup -> link -> persist
"""

import hashlib
import sys
sys.path.append("../../packages")

from typing import TypedDict, List, Dict, Any, Optional
from datetime import datetime
from uuid import uuid4

from langgraph.graph import StateGraph, END
from core.models import SourceItem, Entity, Evidence, EntityType, EntityStatus, Confidence, SourceType
from core.llm import get_llm, get_llm_client
from core.embeddings import embed, combine_for_embedding
from core.graph import GraphClient
from core.queries import BrainQueries
from pipelines.contracts import CLASSIFICATION_SCHEMA, FACT_EXTRACTION_SCHEMA


# Get the configured LLM client
def get_extraction_llm():
    """Get the LLM client for extraction."""
    return get_llm()


# State type for the pipeline
class ExtractionState(TypedDict):
    source_item: SourceItem
    is_relevant: bool
    extracted_facts: List[Dict[str, Any]]
    dedupe_results: List[Dict[str, Any]]
    final_entities: List[str]  # Created entity IDs
    relationships_created: int
    error: Optional[str]


# Dedup similarity thresholds
DEDUP_EXACT_THRESHOLD = 0.92  # Above this: don't create, attach evidence
DEDUP_POSSIBLE_THRESHOLD = 0.80  # Above this: create with RELATES_TO edge

# Relationship types are interpolated into Cypher, so keep them allow-listed.
ALLOWED_RELATION_TYPES = {
    "ADVANCES",
    "AFFECTS",
    "DEPENDS_ON",
    "SUPERSEDES",
    "CONSTRAINS",
    "RELATES_TO",
}


def infer_intra_document_relationships(
    dedupe_results: List[Dict[str, Any]],
) -> List[Dict[str, str]]:
    """Infer a small, deterministic relationship set for one imported document.

    A single Project acts as the document-local hub. We deliberately do not
    infer across multiple projects because choosing the correct target would be
    ambiguous and would make the graph noisier than the source supports.
    """
    created = [
        result
        for result in dedupe_results
        if result.get("action") == "create" and result.get("entity_id")
    ]
    projects = [item for item in created if item["fact"].get("type") == "Project"]
    if len(projects) != 1:
        return []

    project_id = projects[0]["entity_id"]
    relationships: List[Dict[str, str]] = []
    relationship_for_type = {
        "Goal": (project_id, "ADVANCES"),
        "Decision": (None, "AFFECTS"),
        "Constraint": (None, "CONSTRAINS"),
    }

    for item in created:
        entity_type = item["fact"].get("type")
        mapping = relationship_for_type.get(entity_type)
        if not mapping:
            continue

        fixed_source, relation_type = mapping
        relationships.append({
            "source_id": fixed_source or item["entity_id"],
            "target_id": item["entity_id"] if fixed_source else project_id,
            "relation": relation_type,
        })

    return relationships


def source_fact_fingerprint(source_item: SourceItem, fact: Dict[str, Any]) -> str:
    """Build a stable identity for one fact extracted from one source location."""
    source = (
        source_item.source.value
        if hasattr(source_item.source, "value")
        else str(source_item.source)
    )
    parts = (
        source_item.org_id,
        source,
        source_item.reference.strip().casefold(),
        str(fact.get("type", "")).strip().casefold(),
        " ".join(str(fact.get("excerpt", "")).split()).casefold(),
    )
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def evidence_id_for(source_item: SourceItem, fact: Dict[str, Any]) -> str:
    """Return a deterministic Evidence ID so retries cannot create duplicates."""
    return f"ev-{source_fact_fingerprint(source_item, fact)}"


async def classify_node(state: ExtractionState) -> ExtractionState:
    """
    Node 1: Classify if source contains extractable facts.

    Cheap gate to filter noise (most Slack threads, many PRs).
    """
    source_item = state["source_item"]

    system_prompt = """You are a fact classifier for a knowledge graph.

Your job: determine if this source contains any useful information worth storing, such as:
- Facts, information, or knowledge
- Goals or objectives
- Decisions or choices made
- Instructions or how-to guides
- Notes or summaries
- Any structured information

Respond with JSON: {"is_relevant": true/false, "reasoning": "one sentence"}

Be generous - if there's ANY useful content, mark it as relevant. Only mark as not relevant if it's truly empty or meaningless.
"""

    prompt = f"""Source: {source_item.source} | {source_item.kind}
Title: {source_item.title}

Body:
{source_item.body[:1500]}

Does this contain extractable information?"""

    try:
        llm = get_extraction_llm()
        result = await llm.call_json(
            prompt=prompt,
            system=system_prompt,
            max_tokens=200,
            schema=CLASSIFICATION_SCHEMA,
        )

        state["is_relevant"] = result.get("is_relevant", False)

        if not state["is_relevant"]:
            print(f"[Extract] Classified as not relevant: {source_item.title[:50]}")
        else:
            print(f"[Extract] Classified as relevant: {source_item.title[:50]}")

    except Exception as e:
        state["error"] = f"Classification failed: {e}"
        state["is_relevant"] = False

    return state


async def extract_node(state: ExtractionState) -> ExtractionState:
    """
    Node 2: Extract structured facts via LLM.

    Returns list of:
    - type (Goal/Decision/Constraint/CustomerRequest)
    - statement (one sentence, self-contained, present tense)
    - detail (longer explanation)
    - owner_hint (if mentioned)
    - confidence (high/medium/low)
    - excerpt (verbatim quote from source)
    - relations_hint (e.g., [{"relation": "SUPERSEDES", "target_hint": "..."}])
    """
    if not state["is_relevant"]:
        state["extracted_facts"] = []
        return state

    source_item = state["source_item"]

    system_prompt = """You are extracting structured facts for a knowledge graph.

Extract only the information needed by the Komponist MVP. Categorize each item as one of:
- Decision: a choice that was made
- Goal: an objective or target
- Constraint: a rule, limitation, or non-negotiable requirement
- Project: an active work effort or initiative

Rules:
1. Statement: one sentence, self-contained (readable without context), present tense
2. Detail: 1-3 sentences explaining more context
3. Excerpt: verbatim quote from the source
4. Confidence: high (explicit), medium (implicit), low (inferred)
5. Relations hint: relationships explicitly supported by the source. Use the
   exact statement of another extracted fact as target_hint when possible.
   Valid examples: a Project ADVANCES a Goal, a Decision AFFECTS a Project,
   or a Constraint CONSTRAINS a Project. Use [] when none exist.

IMPORTANT: Always return a JSON object with a "facts" key containing an array:
{"facts": [
  {"type": "...", "statement": "...", "detail": "...", "excerpt": "...", "confidence": "...", "relations_hint": []},
  ...
]}

If nothing to extract, return: {"facts": []}
Extract multiple facts if the source contains multiple pieces of information.
"""

    prompt = f"""Source: {source_item.source} | {source_item.reference}
Title: {source_item.title}
Author: {source_item.author or 'unknown'}

Body:
{source_item.body[:4000]}

Extract all relevant items:"""

    try:
        llm = get_extraction_llm()
        result = await llm.call_json(
            prompt=prompt,
            system=system_prompt,
            max_tokens=3000,
            schema=FACT_EXTRACTION_SCHEMA,
        )

        # Result should be array or dict with "facts" key
        if isinstance(result, list):
            facts = result
        elif isinstance(result, dict) and "facts" in result:
            facts = result["facts"]
        elif isinstance(result, dict) and "type" in result and "statement" in result:
            # Single fact returned as object instead of array
            facts = [result]
        else:
            # Try to extract from common wrapper keys
            for key in ["items", "results", "data", "extracted"]:
                if isinstance(result, dict) and key in result:
                    facts = result[key] if isinstance(result[key], list) else [result[key]]
                    break
            else:
                facts = []
                print(f"[Extract] Unexpected result format: {type(result)} - {str(result)[:200]}")

        state["extracted_facts"] = facts
        print(f"[Extract] Extracted {len(facts)} facts from {source_item.reference}")

    except Exception as e:
        state["error"] = f"Extraction failed: {e}"
        state["extracted_facts"] = []

    return state


async def embed_node(state: ExtractionState) -> ExtractionState:
    """
    Node 3: Embed each extracted fact.
    """
    for fact in state["extracted_facts"]:
        try:
            text = combine_for_embedding(
                fact["statement"],
                fact.get("detail")
            )
            embedding = await embed(text)
            fact["embedding"] = embedding
        except Exception as e:
            print(f"[Extract] Embedding failed for fact: {e}")
            fact["embedding"] = None

    print(f"[Extract] Embedded {len(state['extracted_facts'])} facts")
    return state


async def dedup_node(state: ExtractionState) -> ExtractionState:
    """
    Node 4: Dedup against existing entities via vector similarity.

    For each fact:
    - Search top-5 similar entities (any status)
    - Score > 0.92 against confirmed/proposed of same type: attach evidence, don't create
    - Score 0.80-0.92: create with RELATES_TO edge
    - Else: create fresh
    """
    source_item = state["source_item"]
    dedupe_results = []

    for fact in state["extracted_facts"]:
        fingerprint = source_fact_fingerprint(source_item, fact)
        fact["source_fingerprint"] = fingerprint

        # A source fingerprint is the authoritative retry/idempotency key. The
        # evidence fallback also upgrades entities created before fingerprints
        # were introduced.
        try:
            existing = await GraphClient.run_query(
                """
                MATCH (e:Entity {
                    org_id: $org_id,
                    entity_type: $entity_type
                })
                WHERE e.status IN ['proposed', 'confirmed']
                  AND ((size(coalesce(e.department_ids, [])) = 0 AND $department_id IS NULL)
                       OR $department_id IN coalesce(e.department_ids, []))
                OPTIONAL MATCH (e)-[:CITED_BY]->(ev:Evidence)
                WITH e, collect(ev) AS evidence
                WHERE e.source_fingerprint = $fingerprint
                   OR any(item IN evidence WHERE
                        item.reference = $reference AND item.excerpt = $excerpt)
                SET e.source_fingerprint = $fingerprint
                RETURN e.id AS id, e.status AS status
                ORDER BY CASE e.status WHEN 'confirmed' THEN 0 ELSE 1 END
                LIMIT 1
                """,
                {
                    "org_id": source_item.org_id,
                    "entity_type": fact["type"],
                    "fingerprint": fingerprint,
                    "reference": source_item.reference,
                    "excerpt": fact.get("excerpt", ""),
                    "department_id": source_item.department_id,
                },
            )
        except Exception as error:
            print(f"[Dedup] Fingerprint lookup failed: {error}")
            existing = []

        if existing:
            dedupe_results.append({
                "fact": fact,
                "action": "attach_evidence",
                "duplicate_of": existing[0]["id"],
                "duplicate_reason": "source_fingerprint",
                "relates_to": [],
            })
            print(f"[Dedup] Source retry: {fact['statement'][:50]}")
            continue

        if not fact.get("embedding"):
            dedupe_results.append({
                "fact": fact,
                "action": "create",
                "duplicate_of": None,
                "relates_to": []
            })
            continue

        # Vector search for similar entities
        try:
            similar = await BrainQueries.hybrid_search(
                org_id=source_item.org_id,
                query_embedding=fact["embedding"],
                entity_types=[fact["type"]],
                k=5,
                status="confirmed",  # Check confirmed first
                department_ids=(
                    [source_item.department_id] if source_item.department_id else []
                ),
                access_all_departments=False,
                include_global=False,
            )

            # Also check proposed
            similar_proposed = await BrainQueries.hybrid_search(
                org_id=source_item.org_id,
                query_embedding=fact["embedding"],
                entity_types=[fact["type"]],
                k=5,
                status="proposed",
                department_ids=(
                    [source_item.department_id] if source_item.department_id else []
                ),
                access_all_departments=False,
                include_global=False,
            )

            all_similar = similar + similar_proposed
            all_similar.sort(key=lambda x: x["score"], reverse=True)

            best_match = all_similar[0] if all_similar else None

            if best_match and best_match["score"] > DEDUP_EXACT_THRESHOLD:
                # Exact duplicate: attach evidence only
                dedupe_results.append({
                    "fact": fact,
                    "action": "attach_evidence",
                    "duplicate_of": best_match["id"],
                    "duplicate_reason": "semantic",
                    "relates_to": []
                })
                print(f"[Dedup] Exact duplicate (score {best_match['score']:.3f}): {fact['statement'][:50]}")

            elif best_match and best_match["score"] > DEDUP_POSSIBLE_THRESHOLD:
                # Possible duplicate: create with RELATES_TO
                relates_to = [
                    {"entity_id": m["id"], "score": m["score"]}
                    for m in all_similar
                    if m["score"] > DEDUP_POSSIBLE_THRESHOLD
                ]
                dedupe_results.append({
                    "fact": fact,
                    "action": "create",
                    "duplicate_of": None,
                    "relates_to": relates_to
                })
                print(f"[Dedup] Possible duplicate (score {best_match['score']:.3f}): {fact['statement'][:50]}")

            else:
                # Fresh entity
                dedupe_results.append({
                    "fact": fact,
                    "action": "create",
                    "duplicate_of": None,
                    "relates_to": []
                })
                print(f"[Dedup] Fresh entity: {fact['statement'][:50]}")

        except Exception as e:
            print(f"[Dedup] Error: {e}")
            dedupe_results.append({
                "fact": fact,
                "action": "create",
                "duplicate_of": None,
                "relates_to": []
            })

    state["dedupe_results"] = dedupe_results
    return state


async def link_node(state: ExtractionState) -> ExtractionState:
    """
    Node 5: Resolve relation hints via vector search.

    For each fact with relations_hint, search for target entities.
    Add edge only if similarity > 0.85.
    """
    for result in state["dedupe_results"]:
        fact = result["fact"]
        relations_hint = fact.get("relations_hint", [])

        resolved_relations = []

        for hint in relations_hint:
            relation_type = hint.get("relation")
            target_hint = hint.get("target_hint", "")

            if not target_hint:
                continue

            try:
                # Search for target
                target_embedding = await embed(target_hint)
                candidates = await BrainQueries.hybrid_search(
                    org_id=state["source_item"].org_id,
                    query_embedding=target_embedding,
                    k=3,
                    status="confirmed",
                    department_ids=(
                        [state["source_item"].department_id]
                        if state["source_item"].department_id else []
                    ),
                    access_all_departments=False,
                    include_global=False,
                )

                if candidates and candidates[0]["score"] > 0.85:
                    resolved_relations.append({
                        "relation": relation_type,
                        "target_id": candidates[0]["id"],
                        "score": candidates[0]["score"]
                    })
                    print(f"[Link] Resolved {relation_type} -> {candidates[0]['statement'][:40]}")
                else:
                    # Store hint as property for reviewer
                    result["unresolved_hint"] = hint

            except Exception as e:
                print(f"[Link] Error resolving relation: {e}")

        result["resolved_relations"] = resolved_relations

    return state


async def persist_node(state: ExtractionState) -> ExtractionState:
    """
    Node 6: Persist to Neo4j.

    For each dedupe_result:
    - If action=attach_evidence: create Evidence node, link to existing entity
    - If action=create: create Entity (proposed) + Evidence + edges
    """
    source_item = state["source_item"]
    created_ids = []
    relationships_created = 0

    for result in state["dedupe_results"]:
        fact = result["fact"]
        action = result["action"]

        try:
            if (
                action == "attach_evidence"
                and result.get("duplicate_reason") == "source_fingerprint"
            ):
                print(f"[Persist] Source evidence already attached to {result['duplicate_of']}")
                continue

            # Create Evidence node
            evidence_id = evidence_id_for(source_item, fact)
            evidence_query = """
            MERGE (e:Evidence {id: $id})
            ON CREATE SET
                e.org_id = $org_id,
                e.source = $source,
                e.department_id = $department_id,
                e.title = $title,
                e.reference = $reference,
                e.url = $url,
                e.excerpt = $excerpt,
                e.source_date = datetime($source_date),
                e.created_at = datetime()
            """

            await GraphClient.run_query(evidence_query, {
                "id": evidence_id,
                "org_id": source_item.org_id,
                "source": source_item.source.value,
                "department_id": source_item.department_id,
                "title": source_item.title,
                "reference": source_item.reference,
                "url": source_item.url,
                "excerpt": fact.get("excerpt", ""),
                "source_date": source_item.source_date.isoformat()
            })

            if action == "attach_evidence":
                # Link evidence to existing entity
                link_query = """
                MATCH (e:Entity {id: $entity_id, org_id: $org_id})
                MATCH (ev:Evidence {id: $evidence_id})
                MERGE (e)-[:CITED_BY]->(ev)
                """
                await GraphClient.run_query(link_query, {
                    "entity_id": result["duplicate_of"],
                    "evidence_id": evidence_id,
                    "org_id": source_item.org_id
                })
                print(f"[Persist] Attached evidence to {result['duplicate_of']}")

            else:
                # Create new entity
                entity_id = str(uuid4())
                entity_query = """
                CREATE (e:Entity {
                    id: $id,
                    org_id: $org_id,
                    entity_type: $entity_type,
                    statement: $statement,
                    detail: $detail,
                    status: 'proposed',
                    confidence: $confidence,
                    embedding: $embedding,
                    source_fingerprint: $source_fingerprint,
                    department_ids: $department_ids,
                    created_at: datetime(),
                    updated_at: datetime()
                })
                WITH e
                MATCH (ev:Evidence {id: $evidence_id})
                MERGE (e)-[:CITED_BY]->(ev)
                """

                # Add type label
                entity_type = fact["type"]
                entity_query = entity_query.replace(
                    "CREATE (e:Entity {",
                    f"CREATE (e:Entity:{entity_type} {{"
                )

                await GraphClient.run_query(entity_query, {
                    "id": entity_id,
                    "org_id": source_item.org_id,
                    "entity_type": entity_type,
                    "statement": fact["statement"],
                    "detail": fact.get("detail"),
                    "confidence": fact.get("confidence", "medium"),
                    "embedding": fact.get("embedding"),
                    "source_fingerprint": fact["source_fingerprint"],
                    "department_ids": [source_item.department_id] if source_item.department_id else [],
                    "evidence_id": evidence_id
                })

                # Create RELATES_TO edges
                for relates in result.get("relates_to", []):
                    relates_query = """
                    MATCH (e:Entity {id: $entity_id, org_id: $org_id})
                    MATCH (t:Entity {id: $target_id, org_id: $org_id})
                    MERGE (e)-[:RELATES_TO {score: $score}]->(t)
                    RETURN true AS linked
                    """
                    linked = await GraphClient.run_query(relates_query, {
                        "entity_id": entity_id,
                        "target_id": relates["entity_id"],
                        "score": relates["score"],
                        "org_id": source_item.org_id,
                    })
                    relationships_created += 1 if linked else 0

                # Create resolved relation edges
                for rel in result.get("resolved_relations", []):
                    if rel["relation"] not in ALLOWED_RELATION_TYPES:
                        continue
                    rel_query = f"""
                    MATCH (e:Entity {{id: $entity_id, org_id: $org_id}})
                    MATCH (t:Entity {{id: $target_id, org_id: $org_id}})
                    MERGE (e)-[:{rel["relation"]}]->(t)
                    RETURN true AS linked
                    """
                    linked = await GraphClient.run_query(rel_query, {
                        "entity_id": entity_id,
                        "target_id": rel["target_id"],
                        "org_id": source_item.org_id,
                    })
                    relationships_created += 1 if linked else 0

                result["entity_id"] = entity_id
                created_ids.append(entity_id)
                print(f"[Persist] Created {entity_type}: {fact['statement'][:50]}")

        except Exception as e:
            print(f"[Persist] Error: {e}")
            if not state.get("error"):
                state["error"] = str(e)

    # Connect facts extracted from the same document using conservative ontology
    # rules. These edges are marked as inferred so the UI/reviewer can distinguish
    # them from relationships explicitly stated by the model.
    for rel in infer_intra_document_relationships(state["dedupe_results"]):
        relation_type = rel["relation"]
        if relation_type not in ALLOWED_RELATION_TYPES:
            continue
        relation_query = f"""
        MATCH (source:Entity {{id: $source_id, org_id: $org_id}})
        MATCH (target:Entity {{id: $target_id, org_id: $org_id}})
        MERGE (source)-[r:{relation_type}]->(target)
        ON CREATE SET
            r.inferred = true,
            r.inference_basis = 'same_document',
            r.created_at = datetime()
        RETURN true AS linked
        """
        try:
            linked = await GraphClient.run_query(relation_query, {
                "source_id": rel["source_id"],
                "target_id": rel["target_id"],
                "org_id": source_item.org_id,
            })
            relationships_created += 1 if linked else 0
        except Exception as e:
            print(f"[Persist] Relationship error: {e}")
            if not state.get("error"):
                state["error"] = str(e)

    state["final_entities"] = created_ids
    state["relationships_created"] = relationships_created
    print(
        f"[Extract] Pipeline complete: {len(created_ids)} entities and "
        f"{relationships_created} relationships created"
    )
    return state


# Build the graph
def build_extraction_graph() -> StateGraph:
    """Build the extraction pipeline graph."""
    workflow = StateGraph(ExtractionState)

    # Add nodes
    workflow.add_node("classify", classify_node)
    workflow.add_node("extract", extract_node)
    workflow.add_node("embed", embed_node)
    workflow.add_node("dedup", dedup_node)
    workflow.add_node("link", link_node)
    workflow.add_node("persist", persist_node)

    # Add edges
    workflow.set_entry_point("classify")
    workflow.add_edge("classify", "extract")
    workflow.add_edge("extract", "embed")
    workflow.add_edge("embed", "dedup")
    workflow.add_edge("dedup", "link")
    workflow.add_edge("link", "persist")
    workflow.add_edge("persist", END)

    return workflow.compile()


# Main extraction function
async def extract_from_source(source_item: SourceItem) -> Dict[str, Any]:
    """
    Run extraction pipeline on a SourceItem.

    Args:
        source_item: Normalized source item

    Returns:
        Dict with created entity IDs and stats
    """
    graph = build_extraction_graph()

    initial_state: ExtractionState = {
        "source_item": source_item,
        "is_relevant": False,
        "extracted_facts": [],
        "dedupe_results": [],
        "final_entities": [],
        "relationships_created": 0,
        "error": None
    }

    try:
        final_state = await graph.ainvoke(initial_state)

        return {
            "success": final_state.get("error") is None,
            "entity_ids": final_state.get("final_entities", []),
            "facts_extracted": len(final_state.get("extracted_facts", [])),
            "entities_created": len(final_state.get("final_entities", [])),
            "relationships_created": final_state.get("relationships_created", 0),
            "error": final_state.get("error")
        }

    except Exception as e:
        return {
            "success": False,
            "entity_ids": [],
            "facts_extracted": 0,
            "entities_created": 0,
            "relationships_created": 0,
            "error": str(e)
        }


if __name__ == "__main__":
    import asyncio

    async def test():
        # Test with a sample source item
        test_item = SourceItem(
            org_id="test-org",
            source=SourceType.GITHUB,
            kind="pr_merged",
            title="Switch to WorkOS for auth",
            body="After evaluating options, we decided to use WorkOS for enterprise SSO. It handles SAML/OIDC and directory sync, which saves us months of compliance work. This supersedes the internal auth service we were building.",
            author="alice",
            url="https://github.com/test/repo/pull/42",
            reference="PR#42",
            source_date=datetime.utcnow()
        )

        GraphClient.initialize()
        result = await extract_from_source(test_item)
        print("\nResult:", result)
        await GraphClient.close()

    asyncio.run(test())


# Alias for backward compatibility
async def extract_entities(source_item: SourceItem) -> list:
    """
    Extract entities from a source item.
    Returns list of extracted entity dicts.
    """
    result = await extract_from_source(source_item)
    # Return the extracted facts for the simple fallback in main.py
    return result.get("extracted_facts", [])
