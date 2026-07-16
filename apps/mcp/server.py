"""
Komponist MCP Server

FastMCP server providing tools for coding agents to interact with the company brain.
"""

import os
import sys
import hashlib
import json
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any

sys.path.append("../../packages")

from fastmcp import FastMCP
from core.graph import GraphClient
from core.queries import BrainQueries
from core.embeddings import embed

# Import database for tool call logging
sys.path.append("../api")
from database import async_session, ToolCall

# Import constraint checking
from constraints import check_constraint as check_constraint_impl
from constraints import request_approval as request_approval_impl
from constraints import get_approval_status as get_approval_status_impl


# Auth: org_id from environment (in production, use API key auth)
ORG_ID = os.getenv("KOMPONIST_ORG_ID", "default-org")


@asynccontextmanager
async def lifespan(server: FastMCP):
    """Initialize and close shared connections with the MCP server."""
    GraphClient.initialize()
    print(f"[MCP] Komponist server started for org: {ORG_ID}")
    try:
        yield
    finally:
        await GraphClient.close()
        print("[MCP] Komponist server stopped")


# Initialize MCP server
mcp = FastMCP(
    name="komponist",
    version="0.1.0",
    lifespan=lifespan,
)


async def log_tool_call(
    tool: str,
    input_data: Dict[str, Any],
    output_data: Optional[Dict[str, Any]],
    latency_ms: int,
    verdict: Optional[str] = None
):
    """Log MCP tool call to database for metrics."""
    try:
        async with async_session() as session:
            call = ToolCall(
                org_id=ORG_ID,
                tool=tool,
                input=input_data,
                output=output_data,
                verdict=verdict,
                agent_client="mcp",  # Could extract from headers
                latency_ms=latency_ms
            )
            session.add(call)
            await session.commit()
    except Exception as e:
        print(f"[MCP] Failed to log tool call: {e}")


def format_evidence(evidence: List[Dict[str, Any]]) -> str:
    """Format evidence as citation lines."""
    if not evidence:
        return ""

    citations = []
    for index, e in enumerate(evidence, 1):
        source = e.get("source") or "unknown"
        ref = e.get("reference") or "unknown reference"
        url = e.get("url")
        excerpt = (e.get("excerpt") or "").strip()
        source_date = e.get("source_date")

        label = f"{source} · {ref}"
        citation = f"  {index}. [{label}]({url})" if url else f"  {index}. {label}"
        if source_date:
            citation += f" · {str(source_date)[:10]}"
        if excerpt:
            citation += f"\n     > {excerpt}"
        citations.append(citation)

    return "\n" + "\n".join(citations)


_SEARCHABLE_ENTITY_TYPES = {"Decision", "Goal", "Constraint", "Project"}
_SEARCH_STOP_WORDS = {
    "about", "all", "are", "der", "die", "das", "do", "does", "for",
    "from", "haben", "ist", "our", "show", "the", "und", "use", "was",
    "what", "welche", "which", "who", "wie", "wir", "with",
}


def _search_terms(query: str) -> List[str]:
    """Extract stable terms for no-model and index-independent search."""
    import re

    words = re.findall(r"[\w-]+", query.casefold(), flags=re.UNICODE)
    return list(dict.fromkeys(
        word for word in words if len(word) >= 3 and word not in _SEARCH_STOP_WORDS
    ))[:12]


async def _literal_context_search(
    query: str,
    types: Optional[List[str]],
    limit: int,
) -> List[Dict[str, Any]]:
    """Search confirmed entities without embeddings or Neo4j indexes."""
    terms = _search_terms(query)
    if not terms:
        return []

    return await GraphClient.run_query(
        """
        MATCH (entity:Entity {org_id: $org_id, status: 'confirmed'})
        WHERE ($types IS NULL OR entity.entity_type IN $types)
          AND any(term IN $terms WHERE
              toLower(coalesce(entity.statement, '')) CONTAINS term OR
              toLower(coalesce(entity.detail, '')) CONTAINS term)
        WITH entity, size([term IN $terms WHERE
            toLower(coalesce(entity.statement, '')) CONTAINS term OR
            toLower(coalesce(entity.detail, '')) CONTAINS term]) AS matches
        RETURN entity.id AS id, entity.entity_type AS entity_type,
               entity.statement AS statement, entity.detail AS detail,
               entity.confidence AS confidence, toFloat(matches) AS score
        ORDER BY matches DESC, entity.confirmed_at DESC
        LIMIT $limit
        """,
        {"org_id": ORG_ID, "types": types, "terms": terms, "limit": limit},
    )


async def _evidence_for_entities(entity_ids: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    """Load exact, org-scoped provenance for each confirmed result."""
    if not entity_ids:
        return {}

    rows = await GraphClient.run_query(
        """
        MATCH (entity:Entity {org_id: $org_id, status: 'confirmed'})
        WHERE entity.id IN $entity_ids
        OPTIONAL MATCH (entity)-[:CITED_BY]->(evidence:Evidence {org_id: $org_id})
        RETURN entity.id AS entity_id,
               collect(DISTINCT evidence{.id, .source, .reference, .url,
                                         .excerpt, .source_date}) AS evidence
        """,
        {"org_id": ORG_ID, "entity_ids": entity_ids},
    )
    return {
        row["entity_id"]: [item for item in row["evidence"] if item.get("id")]
        for row in rows
    }


@mcp.tool()
async def search_company_context(
    query: str,
    types: Optional[List[str]] = None,
    limit: int = 8
) -> str:
    """
    Search the company brain for relevant context.

    Performs hybrid search (vector + fulltext) across goals, decisions,
    constraints, and projects. Returns confirmed, cited facts only.

    Args:
        query: Natural language query (e.g., "what auth approach do we use?")
        types: Filter by entity types (e.g., ["Decision", "Goal"])
        limit: Maximum results (default 8, max 20)

    Returns:
        Markdown-formatted results with citations. Empty if no matches.
        Hard cap ~2000 tokens to avoid context overflow.
    """
    import time
    start = time.time()

    try:
        result_limit = max(1, min(limit, 20))
        if types:
            invalid_types = sorted(set(types) - _SEARCHABLE_ENTITY_TYPES)
            if invalid_types:
                allowed = ", ".join(sorted(_SEARCHABLE_ENTITY_TYPES))
                return (
                    f"Unsupported entity type(s): {', '.join(invalid_types)}. "
                    f"Allowed types: {allowed}."
                )

        mock_mode = os.getenv("KOMPONIST_AI_MODE", "mock").lower() == "mock"
        results: List[Dict[str, Any]] = []

        if not mock_mode:
            try:
                query_embedding = await embed(query)
                results = await BrainQueries.hybrid_search(
                    org_id=ORG_ID,
                    query_text=query,
                    query_embedding=query_embedding,
                    entity_types=types,
                    k=result_limit,
                    status="confirmed"
                )
            except Exception as search_error:
                print(f"[MCP] Hybrid search failed, using literal fallback: {search_error}")

        literal_results = await _literal_context_search(query, types, result_limit)
        merged = {result["id"]: result for result in literal_results}
        for result in results:
            merged.setdefault(result["id"], result)
        results = list(merged.values())[:result_limit]

        if not results:
            latency_ms = int((time.time() - start) * 1000)
            await log_tool_call("search_company_context", {
                "query": query,
                "types": types,
                "limit": limit
            }, {"results": 0}, latency_ms)
            return "No context found for this query."

        evidence_map = await _evidence_for_entities([result["id"] for result in results])

        # Format output
        output = []
        token_count = 0
        TOKEN_LIMIT = 2000

        for r in results:
            entity_id = r["id"]
            entity_evidence = evidence_map.get(entity_id, [])
            if not entity_evidence:
                continue

            entity_type = r["entity_type"]
            statement = r["statement"]
            detail = r.get("detail", "")

            # Build fact section
            fact = f"**[{entity_type}]** {statement}"
            fact += f"\n  Entity ID: `{entity_id}`"
            if detail:
                fact += f"\n  {detail}"

            # Add citations
            citations = format_evidence(entity_evidence)
            fact += citations

            # Rough token counting (4 chars ≈ 1 token)
            fact_tokens = len(fact) // 4
            if token_count + fact_tokens > TOKEN_LIMIT:
                output.append("\n_(Additional results omitted to stay within token limit)_")
                break

            output.append(fact)
            token_count += fact_tokens

        markdown = "\n\n".join(output)
        if not markdown:
            markdown = "No cited confirmed context found for this query."

        latency_ms = int((time.time() - start) * 1000)
        await log_tool_call("search_company_context", {
            "query": query,
            "types": types,
            "limit": limit
        }, {
            "results": len(results),
            "returned": len(output)
        }, latency_ms)

        return markdown

    except Exception as e:
        latency_ms = int((time.time() - start) * 1000)
        await log_tool_call("search_company_context", {
            "query": query,
            "types": types,
            "limit": limit
        }, {"error": str(e)}, latency_ms)
        return f"Error searching context: {e}"


@mcp.tool()
async def get_active_decisions(
    topic: Optional[str] = None,
    project: Optional[str] = None
) -> str:
    """
    Get active (non-superseded) decisions.

    Returns confirmed decisions that have not been superseded. Optionally
    filtered by topic similarity or project scope.

    Args:
        topic: Filter by relevance to topic (e.g., "authentication")
        project: Filter by project ID

    Returns:
        Markdown-formatted decisions with supersedes history and citations.
    """
    import time
    start = time.time()

    try:
        # Get topic embedding if provided
        topic_embedding = None
        if topic:
            topic_embedding = await embed(topic)

        # Query active decisions
        decisions = await BrainQueries.active_decisions(
            org_id=ORG_ID,
            topic_embedding=topic_embedding,
            k=20
        )

        if not decisions:
            latency_ms = int((time.time() - start) * 1000)
            await log_tool_call("get_active_decisions", {
                "topic": topic,
                "project": project
            }, {"results": 0}, latency_ms)
            return "No active decisions found."

        # Format output
        output = []

        for d in decisions:
            statement = d["statement"]
            detail = d.get("detail", "")
            confidence = d.get("confidence", "medium")
            evidence = d.get("evidence", [])

            # Build decision section
            section = f"**{statement}**"
            if detail:
                section += f"\n  _{detail}_"
            section += f"\n  Confidence: {confidence}"

            # Add citations
            citations = format_evidence(evidence)
            section += citations

            # TODO: Add supersedes history (one level deep)
            # For now, skip to keep output focused

            output.append(section)

        markdown = "\n\n---\n\n".join(output)

        latency_ms = int((time.time() - start) * 1000)
        await log_tool_call("get_active_decisions", {
            "topic": topic,
            "project": project
        }, {"results": len(decisions)}, latency_ms)

        return markdown

    except Exception as e:
        latency_ms = int((time.time() - start) * 1000)
        await log_tool_call("get_active_decisions", {
            "topic": topic,
            "project": project
        }, {"error": str(e)}, latency_ms)
        return f"Error fetching decisions: {e}"


def _normalized_report_list(values: Optional[List[str]], field: str) -> List[str]:
    """Validate and normalize bounded free-text report fields."""
    if not values:
        return []
    if len(values) > 20:
        raise ValueError(f"{field} accepts at most 20 items")

    normalized = []
    for value in values:
        if not isinstance(value, str):
            raise ValueError(f"Every {field} item must be a string")
        item = value.strip()
        if len(item) > 2000:
            raise ValueError(f"Every {field} item must be at most 2000 characters")
        if item:
            normalized.append(item)
    return normalized


def _normalized_report_decisions(
    decisions: Optional[List[Dict[str, str]]],
) -> List[Dict[str, str]]:
    """Validate structured decisions and remove duplicates within one report."""
    if not decisions:
        return []
    if len(decisions) > 20:
        raise ValueError("new_decisions accepts at most 20 items")

    normalized = []
    seen = set()
    for decision in decisions:
        if not isinstance(decision, dict):
            raise ValueError("Every new_decisions item must be an object")
        statement = decision.get("statement", "")
        detail = decision.get("detail", "")
        if not isinstance(statement, str) or not isinstance(detail, str):
            raise ValueError("Decision statement and detail must be strings")
        statement = statement.strip()
        detail = detail.strip()
        if not statement:
            raise ValueError("Every decision requires a non-empty statement")
        if len(statement) > 1000:
            raise ValueError("Decision statements must be at most 1000 characters")
        if len(detail) > 4000:
            raise ValueError("Decision details must be at most 4000 characters")

        key = (statement.casefold(), detail.casefold())
        if key not in seen:
            normalized.append({"statement": statement, "detail": detail})
            seen.add(key)
    return normalized


def _report_reference(
    summary: str,
    decisions: List[Dict[str, str]],
    deviations: List[str],
    unresolved_questions: List[str],
    work_pack_id: Optional[str],
) -> str:
    """Create a stable retry key for an agent report payload."""
    payload = json.dumps({
        "org_id": ORG_ID,
        "summary": summary,
        "decisions": decisions,
        "deviations": deviations,
        "unresolved_questions": unresolved_questions,
        "work_pack_id": work_pack_id,
    }, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"agent-report-{digest[:24]}"


async def _persist_reported_decision(
    decision: Dict[str, str],
    reference: str,
) -> Dict[str, Any]:
    """Persist one structured decision with deterministic provenance."""
    statement = decision["statement"]
    detail = decision["detail"]
    normalized_statement = " ".join(statement.split()).casefold()
    fingerprint = hashlib.sha256(
        f"{ORG_ID}\x1fagent_report\x1f{normalized_statement}\x1f{detail.casefold()}".encode("utf-8")
    ).hexdigest()
    entity_id = f"agent-decision-{fingerprint[:32]}"
    evidence_id = "ev-agent-" + hashlib.sha256(
        f"{reference}\x1f{fingerprint}".encode("utf-8")
    ).hexdigest()
    excerpt = f"Decision: {statement}" + (f"\nDetail: {detail}" if detail else "")

    existing = await GraphClient.run_query(
        """
        MATCH (entity:Entity {org_id: $org_id, entity_type: 'Decision'})
        WHERE entity.status IN ['proposed', 'confirmed']
          AND (entity.source_fingerprint = $fingerprint OR
               toLower(trim(coalesce(entity.statement, ''))) = $statement)
        RETURN entity.id AS id, entity.status AS status
        ORDER BY CASE entity.status WHEN 'confirmed' THEN 0 ELSE 1 END
        LIMIT 1
        """,
        {
            "org_id": ORG_ID,
            "fingerprint": fingerprint,
            "statement": normalized_statement,
        },
    )

    was_created = not existing
    target_id = existing[0]["id"] if existing else entity_id
    if not existing:
        created = await GraphClient.run_query(
            """
            MERGE (entity:Entity:Decision {id: $entity_id})
            ON CREATE SET entity.org_id = $org_id,
                          entity.entity_type = 'Decision',
                          entity.statement = $statement,
                          entity.detail = $detail,
                          entity.status = 'proposed',
                          entity.confidence = 'high',
                          entity.source_fingerprint = $fingerprint,
                          entity.created_at = datetime(),
                          entity.updated_at = datetime()
            RETURN entity.status AS status, entity.org_id AS org_id
            """,
            {
                "entity_id": entity_id,
                "org_id": ORG_ID,
                "statement": statement,
                "detail": detail or None,
                "fingerprint": fingerprint,
            },
        )
        if not created or created[0]["org_id"] != ORG_ID:
            raise ValueError("Could not create an org-scoped decision proposal")
        status = created[0]["status"]
        if status not in {"proposed", "confirmed"}:
            return {"id": target_id, "status": status, "created": False}
    else:
        status = existing[0]["status"]

    await GraphClient.run_query(
        """
        MATCH (entity:Entity {id: $entity_id, org_id: $org_id})
        MERGE (evidence:Evidence {id: $evidence_id})
        ON CREATE SET evidence.org_id = $org_id,
                      evidence.source = 'agent_report',
                      evidence.reference = $reference,
                      evidence.url = '',
                      evidence.excerpt = $excerpt,
                      evidence.source_date = datetime(),
                      evidence.created_at = datetime()
        MERGE (entity)-[:CITED_BY]->(evidence)
        """,
        {
            "entity_id": target_id,
            "org_id": ORG_ID,
            "evidence_id": evidence_id,
            "reference": reference,
            "excerpt": excerpt,
        },
    )
    return {"id": target_id, "status": status, "created": was_created}


async def _work_pack_exists(work_pack_id: str) -> bool:
    result = await GraphClient.run_query(
        "MATCH (work_pack:WorkPack {id: $id, org_id: $org_id}) RETURN work_pack.id AS id",
        {"id": work_pack_id, "org_id": ORG_ID},
    )
    return bool(result)


async def _link_report_to_work_pack(
    entity_ids: List[str],
    work_pack_id: str,
    deviations: List[str],
    unresolved_questions: List[str],
) -> None:
    await GraphClient.run_query(
        """
        MATCH (work_pack:WorkPack {id: $work_pack_id, org_id: $org_id})
        SET work_pack.deviations = $deviations,
            work_pack.unresolved_questions = $unresolved_questions,
            work_pack.updated_at = datetime()
        WITH work_pack
        UNWIND $entity_ids AS entity_id
        MATCH (entity:Entity {id: entity_id, org_id: $org_id})
        MERGE (entity)-[:REPORTED_IN]->(work_pack)
        """,
        {
            "work_pack_id": work_pack_id,
            "org_id": ORG_ID,
            "entity_ids": entity_ids,
            "deviations": deviations,
            "unresolved_questions": unresolved_questions,
        },
    )


@mcp.tool()
async def report_result(
    summary: str,
    new_decisions: Optional[List[Dict[str, str]]] = None,
    deviations: Optional[List[str]] = None,
    unresolved_questions: Optional[List[str]] = None,
    work_pack_id: Optional[str] = None
) -> str:
    """
    Report work completion and new decisions back to the brain.

    Agents call this after completing a task to feed new decisions back into
    the brain. New decisions go through the extraction pipeline and land in
    the review queue (never auto-confirmed).

    Args:
        summary: One-paragraph summary of what was done
        new_decisions: New decisions discovered during work
            Format: [{"statement": "...", "detail": "..."}]
        deviations: List of deviations from original plan/constraints
        unresolved_questions: Questions that came up during work
        work_pack_id: Optional Work Pack ID this relates to

    Returns:
        Confirmation message with entity IDs for created proposals.
    """
    import time
    start = time.time()

    try:
        summary = summary.strip()
        if not summary:
            return "Invalid report: summary must not be empty."
        if len(summary) > 4000:
            return "Invalid report: summary must be at most 4000 characters."

        decisions = _normalized_report_decisions(new_decisions)
        normalized_deviations = _normalized_report_list(deviations, "deviations")
        normalized_questions = _normalized_report_list(
            unresolved_questions, "unresolved_questions"
        )
        work_pack_id = work_pack_id.strip() if work_pack_id else None
        if work_pack_id and not await _work_pack_exists(work_pack_id):
            return f"Invalid report: Work Pack `{work_pack_id}` was not found in this organization."

        reference = _report_reference(
            summary,
            decisions,
            normalized_deviations,
            normalized_questions,
            work_pack_id,
        )
        persisted = [
            await _persist_reported_decision(decision, reference)
            for decision in decisions
        ]
        entity_ids = [item["id"] for item in persisted]
        created_ids = [item["id"] for item in persisted if item["created"]]
        existing = [item for item in persisted if not item["created"]]

        if work_pack_id:
            await _link_report_to_work_pack(
                entity_ids,
                work_pack_id,
                normalized_deviations,
                normalized_questions,
            )

        latency_ms = int((time.time() - start) * 1000)
        await log_tool_call("report_result", {
            "summary": summary,
            "new_decisions_count": len(decisions),
            "work_pack_id": work_pack_id
        }, {
            "entities_created": len(created_ids),
            "entities_existing": len(existing),
            "reference": reference,
        }, latency_ms)

        lines = [f"Report received. Reference: `{reference}`."]
        if created_ids:
            lines.append(
                f"{len(created_ids)} new decision proposal(s) added to the review queue: "
                + ", ".join(f"`{entity_id}`" for entity_id in created_ids)
            )
        if existing:
            known = ", ".join(
                f"`{item['id']}` ({item['status']})" for item in existing
            )
            lines.append(f"Already known: {known}.")
        if not decisions:
            lines.append("No new decisions were included in the report.")
        if work_pack_id:
            lines.append(f"Linked to Work Pack `{work_pack_id}`.")
        return "\n\n".join(lines)

    except ValueError as e:
        return f"Invalid report: {e}."
    except Exception as e:
        latency_ms = int((time.time() - start) * 1000)
        await log_tool_call("report_result", {
            "summary": summary
        }, {"error": str(e)}, latency_ms)
        return f"Error reporting result: {e}"


@mcp.tool()
async def check_constraint(
    intended_action: str,
    project: Optional[str] = None
) -> str:
    """
    Check if an intended action violates any constraints.

    Use this BEFORE taking risky actions (schema changes, dependency additions,
    auth/authz changes, API contract modifications).

    Args:
        intended_action: Clear description of what you want to do
        project: Optional project ID for scoped constraints

    Returns:
        Verdict with constraint details and reasoning. Follow the verdict.
    """
    import time
    start = time.time()

    try:
        result = await check_constraint_impl(
            intended_action=intended_action,
            project=project,
            org_id=ORG_ID
        )

        verdict = result["verdict"]
        reasoning = result["reasoning"]
        constraint = result.get("constraint")

        # Log with verdict field
        latency_ms = result["latency_ms"]
        await log_tool_call("check_constraint", {
            "intended_action": intended_action,
            "project": project
        }, result, latency_ms, verdict=verdict)

        # Format response
        if verdict == "allowed":
            return f"✅ **Allowed**\n\n{reasoning}"

        elif verdict == "blocked":
            output = f"🚫 **Blocked**\n\n{reasoning}\n\n"
            if constraint:
                output += f"**Constraint:** {constraint['statement']}\n"
                if constraint.get('detail'):
                    output += f"\n_{constraint['detail']}_\n"
            output += "\n**You cannot proceed with this action.**"
            return output

        elif verdict == "approval_required":
            output = f"⏸️  **Approval Required**\n\n{reasoning}\n\n"
            if constraint:
                output += f"**Constraint:** {constraint['statement']}\n"
                if constraint.get('detail'):
                    output += f"\n_{constraint['detail']}_\n"
            output += "\n**Use `request_approval` to get human approval before proceeding.**"
            return output

        else:
            return f"⚠️  Error: {reasoning}"

    except Exception as e:
        latency_ms = int((time.time() - start) * 1000)
        await log_tool_call("check_constraint", {
            "intended_action": intended_action,
            "project": project
        }, {"error": str(e)}, latency_ms, verdict="error")
        return f"Error checking constraints: {e}"


@mcp.tool()
async def request_approval(
    action: str,
    constraint_id: str,
    context: str
) -> str:
    """
    Request human approval for an action blocked by a constraint.

    Persists the request and posts Slack buttons when Slack is configured.

    Args:
        action: Action you want to take
        constraint_id: ID of constraint requiring approval (from check_constraint)
        context: Additional context for the approver (why you need this, what's the risk)

    Returns:
        Approval ID to poll with get_approval_status
    """
    import time
    start = time.time()

    try:
        result = await request_approval_impl(
            action=action,
            constraint_id=constraint_id,
            context=context,
            org_id=ORG_ID
        )

        latency_ms = int((time.time() - start) * 1000)
        await log_tool_call("request_approval", {
            "action": action,
            "constraint_id": constraint_id
        }, result, latency_ms)

        if result.get("status") == "error":
            return f"❌ Error: {result.get('error')}"

        approval_id = result["approval_id"]
        delivery = " Sent to Slack." if result.get("delivery") == "slack" else ""
        return f"📬 Approval request created.{delivery}\n\nApproval ID: `{approval_id}`\n\nUse `get_approval_status('{approval_id}')` to check status."

    except Exception as e:
        latency_ms = int((time.time() - start) * 1000)
        await log_tool_call("request_approval", {
            "action": action
        }, {"error": str(e)}, latency_ms)
        return f"Error requesting approval: {e}"


@mcp.tool()
async def get_approval_status(approval_id: str) -> str:
    """
    Check status of a pending approval.

    Args:
        approval_id: Approval ID from request_approval

    Returns:
        Status: pending / approved / denied
    """
    import time
    start = time.time()

    try:
        result = await get_approval_status_impl(approval_id, org_id=ORG_ID)

        latency_ms = int((time.time() - start) * 1000)
        await log_tool_call("get_approval_status", {
            "approval_id": approval_id
        }, result, latency_ms)

        status = result.get("status")

        if status == "not_found":
            return f"❌ Approval ID not found: {approval_id}"
        elif status == "pending":
            return "⏳ Approval pending. Waiting for human review."
        elif status == "approved":
            resolved_by = result.get("resolved_by", "unknown")
            return f"✅ **Approved** by {resolved_by}\n\nYou may proceed with the action."
        elif status == "denied":
            resolved_by = result.get("resolved_by", "unknown")
            return f"🚫 **Denied** by {resolved_by}\n\nYou cannot proceed with this action."
        else:
            return f"⚠️  Unknown status: {status}"

    except Exception as e:
        latency_ms = int((time.time() - start) * 1000)
        await log_tool_call("get_approval_status", {
            "approval_id": approval_id
        }, {"error": str(e)}, latency_ms)
        return f"Error checking approval status: {e}"


@mcp.resource("company-brain://info")
async def brain_info() -> str:
    """Get info about the connected company brain."""
    try:
        verification = await GraphClient.run_query("""
            MATCH (e:Entity {org_id: $org_id, status: 'confirmed'})
            WITH count(e) as confirmed
            MATCH (p:Entity {org_id: $org_id, status: 'proposed'})
            RETURN confirmed, count(p) as proposed
        """, {"org_id": ORG_ID})

        if verification:
            confirmed = verification[0].get("confirmed", 0)
            proposed = verification[0].get("proposed", 0)
            return f"Organization: {ORG_ID}\nConfirmed facts: {confirmed}\nPending review: {proposed}"
        else:
            return f"Organization: {ORG_ID}\nNo data yet."

    except Exception as e:
        return f"Error: {e}"


if __name__ == "__main__":
    # Run MCP server
    mcp.run()
