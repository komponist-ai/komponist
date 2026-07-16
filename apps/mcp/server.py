"""
Komponist MCP Server

FastMCP server providing tools for coding agents to interact with the company brain.
"""

import os
import sys
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any
from datetime import datetime
import asyncio

sys.path.append("../../packages")

from fastmcp import FastMCP
from core.graph import GraphClient
from core.queries import BrainQueries
from core.embeddings import embed
from core.models import SourceItem, SourceType
from pipelines.extract import extract_from_source

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
        created_ids = []

        # Process each new decision
        if new_decisions:
            for decision in new_decisions:
                statement = decision.get("statement", "")
                detail = decision.get("detail", "")

                if not statement:
                    continue

                # Create a SourceItem from agent report
                source_item = SourceItem(
                    org_id=ORG_ID,
                    source=SourceType.AGENT_REPORT,
                    kind="agent_report",
                    title=f"Agent discovery: {statement[:50]}",
                    body=f"{statement}\n\n{detail}",
                    author="agent",
                    url="",
                    reference=f"agent-{int(time.time())}",
                    source_date=datetime.utcnow()
                )

                # Run through extraction pipeline
                result = await extract_from_source(source_item)

                if result["success"]:
                    created_ids.extend(result["entity_ids"])

        # Link to WorkPack if provided
        if work_pack_id and created_ids:
            sys.path.append("../api/integrations")
            from writeback import link_report_result_to_workpack

            await link_report_result_to_workpack(
                entity_ids=created_ids,
                work_pack_id=work_pack_id,
                org_id=ORG_ID,
                deviations=deviations,
                unresolved_questions=unresolved_questions
            )

        # TODO: Link to WorkPack if work_pack_id provided
        # TODO: Store deviations and unresolved_questions

        latency_ms = int((time.time() - start) * 1000)
        await log_tool_call("report_result", {
            "summary": summary,
            "new_decisions_count": len(new_decisions) if new_decisions else 0,
            "work_pack_id": work_pack_id
        }, {
            "entities_created": len(created_ids)
        }, latency_ms)

        if created_ids:
            return f"✅ Report received. {len(created_ids)} new decision(s) added to review queue.\n\nEntity IDs: {', '.join(created_ids)}"
        else:
            return "✅ Report received. No new decisions extracted."

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

    Posts to Slack approvals channel with Approve/Deny buttons.

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
        return f"📬 Approval requested in Slack.\n\nApproval ID: `{approval_id}`\n\nUse `get_approval_status('{approval_id}')` to check status."

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
        result = get_approval_status_impl(approval_id)

        latency_ms = int((time.time() - start) * 1000)
        await log_tool_call("get_approval_status", {
            "approval_id": approval_id
        }, result, latency_ms)

        status = result.get("status")

        if status == "not_found":
            return f"❌ Approval ID not found: {approval_id}"
        elif status == "pending":
            return f"⏳ Approval pending. Waiting for human review in Slack."
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
