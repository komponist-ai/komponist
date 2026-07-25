"""
Extraction Pipeline

LangGraph state machine: SourceItem -> proposed entities in the graph.

Pipeline: classify -> extract -> embed -> dedup -> link -> persist
"""

import hashlib
import re
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
from core.versioning import document_metadata
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


def source_excerpt_location(body: str, excerpt: str) -> tuple[Optional[int], Optional[int]]:
    """Locate a verbatim extracted passage in a line-oriented source document."""
    if not body or not excerpt:
        return None, None
    start = body.find(excerpt)
    if start < 0:
        return None, None
    line_start = body.count("\n", 0, start) + 1
    line_end = line_start + excerpt.count("\n")
    return line_start, line_end


def verbatim_excerpt(body: str, excerpt: str) -> Optional[str]:
    """Return the exact source slice represented by a model-provided excerpt."""
    if not body or not excerpt or not excerpt.strip():
        return None
    excerpt = excerpt.strip()
    if excerpt in body:
        return excerpt

    # Models occasionally normalize line breaks or capitalization despite being
    # asked for a quote. Accept that only when it maps unambiguously back to one
    # exact source span, and persist the original bytes from the document.
    tokens = re.findall(r"\S+", excerpt)
    if not tokens:
        return None
    pattern = r"\s+".join(re.escape(token) for token in tokens)
    matches = list(re.finditer(pattern, body, flags=re.IGNORECASE))
    if len(matches) != 1:
        return None
    return body[matches[0].start():matches[0].end()]


def preserves_source_modality(excerpt: str, statement: str) -> bool:
    """Reject the common failure mode that turns a condition into a fact."""
    source = excerpt.casefold()
    claim = statement.casefold()
    conditional = re.search(
        r"\b(depends? on|dependent on|provided that|subject to|must|needs? to|"
        r"required|requires?|before|after|if|unless)\b",
        source,
    )
    completed_claim = re.search(
        r"\b(is|are|has been|have been|was|were)\s+"
        r"(completed|finished|approved|delivered|launched|migrated)\b",
        claim,
    )
    completed_source = re.search(
        r"\b(is|are|has been|have been|was|were)\s+"
        r"(completed|finished|approved|delivered|launched|migrated)\b",
        source,
    )
    return not (conditional and completed_claim and not completed_source)


def document_chunks(body: str, max_chars: int = 6000) -> List[str]:
    """Split long sources on paragraph boundaries without silent truncation."""
    if len(body) <= max_chars:
        return [body]
    paragraphs = re.split(r"(\n\s*\n)", body)
    chunks: List[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current.strip():
                chunks.append(current.strip())
                current = ""
            for start in range(0, len(paragraph), max_chars):
                chunks.append(paragraph[start:start + max_chars].strip())
            continue
        if current and len(current) + len(paragraph) > max_chars:
            chunks.append(current.strip())
            current = paragraph
        else:
            current += paragraph
    if current.strip():
        chunks.append(current.strip())
    return chunks


async def reuse_identical_document(source_item: SourceItem) -> Optional[Dict[str, Any]]:
    """Reuse graph claims for byte-equivalent content before calling a model.

    A renamed file or a copy arriving through another connector is still useful
    provenance, but it must not produce a second, potentially different LLM
    extraction. The new DocumentVersion and Evidence nodes retain that source's
    metadata while pointing at the already extracted entities.
    """
    document = document_metadata(source_item)
    rows = await GraphClient.run_query(
        """
        MATCH (existing:DocumentVersion {
            org_id: $org_id,
            content_hash: $content_hash
        })
        WHERE (($department_id IS NULL AND existing.department_id IS NULL)
               OR existing.department_id = $department_id)
        WITH existing
        ORDER BY existing.created_at, existing.id
        LIMIT 1
        OPTIONAL MATCH (existing)-[:HAS_EVIDENCE]->(evidence:Evidence)
        OPTIONAL MATCH (entity:Entity {org_id: $org_id})-[:CITED_BY]->(evidence)
        RETURN existing.id AS document_id,
               evidence.id AS evidence_id,
               evidence.excerpt AS excerpt,
               evidence.line_start AS line_start,
               evidence.line_end AS line_end,
               entity.id AS entity_id
        """,
        {
            "org_id": source_item.org_id,
            "content_hash": document["content_hash"],
            "department_id": source_item.department_id,
        },
    )
    if not rows:
        return None

    existing_document_id = rows[0]["document_id"]
    entity_ids = list(dict.fromkeys(
        row["entity_id"] for row in rows if row.get("entity_id")
    ))

    # A retry of the exact same source already has the required provenance.
    if existing_document_id == document["document_id"]:
        return {
            "success": True,
            "entity_ids": entity_ids,
            "facts_extracted": 0,
            "entities_created": 0,
            "relationships_created": 0,
            "reused_existing_extraction": True,
            "reused_from_document_id": existing_document_id,
            "document_id": document["document_id"],
            "provenance_created": False,
        }

    await GraphClient.run_query(
        """
        MATCH (existing:DocumentVersion {id: $existing_document_id})
        MERGE (document:DocumentVersion {id: $document_id})
        ON CREATE SET
            document.org_id = $org_id,
            document.created_at = datetime(),
            document.prov_type = 'Entity'
        SET document.source = $source,
            document.kind = $kind,
            document.department_id = $department_id,
            document.title = $title,
            document.author = $author,
            document.reference = $reference,
            document.url = $url,
            document.content_hash = $content_hash,
            document.content_length = $content_length,
            document.family_key = $family_key,
            document.source_date = datetime($source_date),
            document.last_seen_at = datetime(),
            document.extraction_reused = true,
            document.reused_from_document_id = $existing_document_id
        MERGE (document)-[derived:WAS_DERIVED_FROM]->(existing)
        SET derived.method = 'exact_content_hash',
            derived.confidence = 1.0,
            derived.created_at = coalesce(derived.created_at, datetime())
        """,
        {
            **document,
            "existing_document_id": existing_document_id,
            "org_id": source_item.org_id,
        },
    )

    for row in rows:
        if not row.get("evidence_id"):
            continue
        evidence_id = "ev-reuse-" + hashlib.sha256(
            f"{document['document_id']}\x1f{row['evidence_id']}".encode("utf-8")
        ).hexdigest()
        await GraphClient.run_query(
            """
            MATCH (document:DocumentVersion {id: $document_id})
            MERGE (evidence:Evidence {id: $evidence_id})
            ON CREATE SET
                evidence.org_id = $org_id,
                evidence.created_at = datetime()
            SET evidence.source = $source,
                evidence.department_id = $department_id,
                evidence.title = $title,
                evidence.reference = $reference,
                evidence.url = $url,
                evidence.excerpt = $excerpt,
                evidence.line_start = $line_start,
                evidence.line_end = $line_end,
                evidence.source_date = datetime($source_date),
                evidence.document_id = $document_id,
                evidence.author = $author,
                evidence.kind = $kind,
                evidence.content_hash = $content_hash,
                evidence.family_key = $family_key,
                evidence.extraction_reused = true,
                evidence.reused_from_evidence_id = $original_evidence_id
            MERGE (document)-[:HAS_EVIDENCE]->(evidence)
            WITH evidence
            MATCH (entity:Entity {id: $entity_id, org_id: $org_id})
            MERGE (entity)-[:CITED_BY]->(evidence)
            """,
            {
                **document,
                "org_id": source_item.org_id,
                "evidence_id": evidence_id,
                "original_evidence_id": row["evidence_id"],
                "entity_id": row.get("entity_id"),
                "excerpt": row.get("excerpt") or "",
                "line_start": row.get("line_start"),
                "line_end": row.get("line_end"),
            },
        )

    return {
        "success": True,
        "entity_ids": entity_ids,
        "facts_extracted": 0,
        "entities_created": 0,
        "relationships_created": 0,
        "reused_existing_extraction": True,
        "reused_from_document_id": existing_document_id,
        "document_id": document["document_id"],
        "provenance_created": True,
    }


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

Body sample:
{source_item.body[:1500]}
...
{source_item.body[-1500:] if len(source_item.body) > 1500 else ''}

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
5. Modality: preserve whether the source describes a fact, decision, goal,
   requirement, plan, or condition. Never turn a dependency, plan, deadline,
   prerequisite, or requirement into a claim that it is already completed.
6. Relations hint: relationships explicitly supported by the source. Use the
   exact statement of another extracted fact as target_hint when possible.
   Valid examples: a Project ADVANCES a Goal, a Decision AFFECTS a Project,
   or a Constraint CONSTRAINS a Project. Use [] when none exist.

IMPORTANT: Always return a JSON object with a "facts" key containing an array:
{"facts": [
  {"type": "...", "statement": "...", "detail": "...", "excerpt": "...", "confidence": "...", "modality": "...", "relations_hint": []},
  ...
]}

If nothing to extract, return: {"facts": []}
Extract multiple facts if the source contains multiple pieces of information.
"""

    chunks = document_chunks(source_item.body)
    all_facts: List[Dict[str, Any]] = []
    for chunk_number, chunk in enumerate(chunks, 1):
        prompt = f"""Source: {source_item.source} | {source_item.reference}
Title: {source_item.title}
Author: {source_item.author or 'unknown'}
Part: {chunk_number} of {len(chunks)}

Body:
{chunk}

Extract all relevant items:"""

        try:
            llm = get_extraction_llm()
            result = await llm.call_json(
                prompt=prompt,
                system=system_prompt,
                max_tokens=3000,
                schema=FACT_EXTRACTION_SCHEMA,
            )

            if isinstance(result, list):
                facts = result
            elif isinstance(result, dict) and "facts" in result:
                facts = result["facts"]
            elif isinstance(result, dict) and "type" in result and "statement" in result:
                facts = [result]
            else:
                for key in ["items", "results", "data", "extracted"]:
                    if isinstance(result, dict) and key in result:
                        facts = result[key] if isinstance(result[key], list) else [result[key]]
                        break
                else:
                    facts = []
                    print(f"[Extract] Unexpected result format: {type(result)} - {str(result)[:200]}")

            for fact in facts:
                exact_excerpt = verbatim_excerpt(
                    source_item.body, str(fact.get("excerpt", ""))
                )
                if not exact_excerpt:
                    print(
                        "[Extract] Dropped fact without verifiable source quote: "
                        f"{str(fact.get('statement', ''))[:70]}"
                    )
                    continue
                fact["excerpt"] = exact_excerpt
                if not preserves_source_modality(
                    exact_excerpt, str(fact.get("statement", ""))
                ):
                    print(
                        "[Extract] Dropped fact that changed source modality: "
                        f"{str(fact.get('statement', ''))[:70]}"
                    )
                    continue
                all_facts.append(fact)
        except Exception as e:
            state["error"] = f"Extraction failed for part {chunk_number}: {e}"
            continue

    unique_facts: Dict[tuple[str, str, str], Dict[str, Any]] = {}
    for fact in all_facts:
        key = (
            str(fact.get("type", "")).casefold(),
            " ".join(str(fact.get("statement", "")).casefold().split()),
            " ".join(str(fact.get("excerpt", "")).casefold().split()),
        )
        unique_facts.setdefault(key, fact)

    state["extracted_facts"] = list(unique_facts.values())
    print(
        f"[Extract] Extracted {len(state['extracted_facts'])} verified facts "
        f"from {source_item.reference} in {len(chunks)} part(s)"
    )

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
    # Give every result a stable target ID before any entity is persisted. This
    # lets explicit relation hints resolve to facts extracted in the same batch.
    for result in state["dedupe_results"]:
        if result.get("action") == "create":
            result.setdefault("entity_id", str(uuid4()))
        elif result.get("duplicate_of"):
            result.setdefault("entity_id", result["duplicate_of"])

    def normalized(value: str) -> str:
        return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))

    batch_targets = [
        result for result in state["dedupe_results"] if result.get("entity_id")
    ]

    for result in state["dedupe_results"]:
        fact = result["fact"]
        relations_hint = fact.get("relations_hint", [])

        resolved_relations = []

        for hint in relations_hint:
            relation_type = hint.get("relation")
            target_hint = hint.get("target_hint", "")

            if not target_hint:
                continue

            source_id = result.get("entity_id")
            normalized_hint = normalized(target_hint)
            local_matches = [
                candidate
                for candidate in batch_targets
                if candidate.get("entity_id") != source_id
                and normalized(candidate["fact"].get("statement", ""))
                == normalized_hint
            ]
            if len(local_matches) == 1:
                resolved_relations.append({
                    "relation": relation_type,
                    "target_id": local_matches[0]["entity_id"],
                    "score": 1.0,
                    "resolution": "same_batch_exact",
                })
                print(
                    f"[Link] Resolved same-batch {relation_type} -> "
                    f"{local_matches[0]['fact']['statement'][:40]}"
                )
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
                        "score": candidates[0]["score"],
                        "resolution": "graph_semantic",
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
    document = document_metadata(source_item)
    created_ids = []
    relationships_created = 0
    pending_relationships: List[Dict[str, Any]] = []

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
            line_start, line_end = source_excerpt_location(
                source_item.body, fact.get("excerpt", "")
            )
            evidence_query = """
            MERGE (document:DocumentVersion {id: $document_id})
            ON CREATE SET
                document.org_id = $org_id,
                document.created_at = datetime(),
                document.prov_type = 'Entity'
            SET
                document.source = $source,
                document.kind = $kind,
                document.department_id = $department_id,
                document.title = $title,
                document.author = $author,
                document.reference = $reference,
                document.url = $url,
                document.content_hash = $content_hash,
                document.content_length = $content_length,
                document.family_key = $family_key,
                document.source_date = datetime($source_date),
                document.last_seen_at = datetime()
            MERGE (e:Evidence {id: $id})
            ON CREATE SET
                e.org_id = $org_id,
                e.source = $source,
                e.department_id = $department_id,
                e.title = $title,
                e.reference = $reference,
                e.url = $url,
                e.excerpt = $excerpt,
                e.line_start = $line_start,
                e.line_end = $line_end,
                e.source_date = datetime($source_date),
                e.created_at = datetime()
            SET
                e.document_id = $document_id,
                e.author = $author,
                e.kind = $kind,
                e.content_hash = $content_hash,
                e.family_key = $family_key
            MERGE (document)-[:HAS_EVIDENCE]->(e)
            """

            await GraphClient.run_query(evidence_query, {
                "id": evidence_id,
                "document_id": document["document_id"],
                "org_id": source_item.org_id,
                "source": source_item.source.value,
                "department_id": source_item.department_id,
                "title": source_item.title,
                "author": source_item.author,
                "kind": source_item.kind,
                "reference": source_item.reference,
                "url": source_item.url,
                "excerpt": fact.get("excerpt", ""),
                "line_start": line_start,
                "line_end": line_end,
                "source_date": source_item.source_date.isoformat(),
                "content_hash": document["content_hash"],
                "content_length": document["content_length"],
                "family_key": document["family_key"],
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
                entity_id = result.get("entity_id") or str(uuid4())
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

                for relates in result.get("relates_to", []):
                    pending_relationships.append({
                        "source_id": entity_id,
                        "target_id": relates["entity_id"],
                        "relation": "RELATES_TO",
                        "score": relates["score"],
                        "resolution": "dedup_similarity",
                    })

                for rel in result.get("resolved_relations", []):
                    if rel["relation"] not in ALLOWED_RELATION_TYPES:
                        continue
                    pending_relationships.append({
                        "source_id": entity_id,
                        "target_id": rel["target_id"],
                        "relation": rel["relation"],
                        "score": rel.get("score"),
                        "resolution": rel.get("resolution", "explicit_hint"),
                    })

                result["entity_id"] = entity_id
                created_ids.append(entity_id)
                print(f"[Persist] Created {entity_type}: {fact['statement'][:50]}")

        except Exception as e:
            print(f"[Persist] Error: {e}")
            if not state.get("error"):
                state["error"] = str(e)

    # Persist explicit and semantic relationships only after every same-batch
    # entity exists. They remain proposed until both endpoint facts are reviewed.
    for rel in pending_relationships:
        if rel["relation"] not in ALLOWED_RELATION_TYPES:
            continue
        relation_query = f"""
        MATCH (source:Entity {{id: $source_id, org_id: $org_id}})
        MATCH (target:Entity {{id: $target_id, org_id: $org_id}})
        MERGE (source)-[r:{rel["relation"]}]->(target)
        ON CREATE SET
            r.status = 'proposed',
            r.resolution = $resolution,
            r.score = $score,
            r.created_at = datetime()
        RETURN true AS linked
        """
        try:
            linked = await GraphClient.run_query(relation_query, {
                "source_id": rel["source_id"],
                "target_id": rel["target_id"],
                "org_id": source_item.org_id,
                "resolution": rel["resolution"],
                "score": rel.get("score"),
            })
            relationships_created += 1 if linked else 0
        except Exception as e:
            print(f"[Persist] Relationship error: {e}")
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
            r.status = 'proposed',
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

    # A conservative W3C PROV-style revision edge. Broader fuzzy families are
    # calculated by the Versions API and remain visibly confidence-scored.
    await GraphClient.run_query(
        """
        MATCH (member:DocumentVersion {org_id: $org_id, family_key: $family_key})
        OPTIONAL MATCH (member)-[stale:WAS_REVISION_OF]->()
        DELETE stale
        WITH DISTINCT member
        ORDER BY member.source_date, member.created_at, member.id
        WITH collect(member) AS versions
        UNWIND CASE
            WHEN size(versions) > 1 THEN range(1, size(versions) - 1)
            ELSE []
        END AS version_index
        WITH versions[version_index] AS current,
             versions[version_index - 1] AS previous
        MERGE (current)-[revision:WAS_REVISION_OF]->(previous)
        SET revision.confidence = 0.9,
            revision.method = 'normalized_title',
            revision.prov_type = 'Revision'
        """,
        {
            "org_id": source_item.org_id,
            "family_key": document["family_key"],
        },
    )

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
    reused = await reuse_identical_document(source_item)
    if reused is not None:
        print(
            "[Extract] Reused identical document extraction from "
            f"{reused['reused_from_document_id']}"
        )
        return reused

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
