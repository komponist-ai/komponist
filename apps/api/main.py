"""
Komponist API

FastAPI application for webhooks, REST endpoints, and health checks.
The programmable company brain.
"""

import os
import hashlib
import json
import re
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

import httpx
from fastapi import FastAPI, HTTPException, UploadFile, File, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

import sys
sys.path.append("../../packages")

from core.graph import GraphClient
from core.schema import GraphSchema
from core.export import export_brain_yaml
from core.import_ import import_brain_yaml, parse_export_yaml
from database import (
    ConnectorOAuthState,
    Department,
    async_session,
    init_db,
    health_check_db,
)
from persistence import (
    append_chat_message,
    authenticate_api_key,
    create_api_key,
    create_chat_conversation,
    create_connected_source,
    delete_chat_conversation,
    delete_connected_source,
    get_chat_conversation,
    get_connected_source,
    list_chat_conversations,
    list_approval_requests,
    list_connected_sources,
    list_api_keys,
    load_org_settings,
    save_org_settings,
    revoke_api_key,
    resolve_approval_request,
    rename_chat_conversation,
    set_connected_source_department,
    update_connected_source,
    upsert_single_source_type,
)


# Import security utilities
from security import validate_org_id, check_rate_limit


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    GraphClient.initialize()
    await init_db()
    await GraphSchema.apply_schema()
    print("✓ Databases initialized")

    yield

    # Shutdown
    await GraphClient.close()
    print("✓ Connections closed")


app = FastAPI(
    title="Komponist API",
    description="The programmable company brain. Company context, composed for every agent.",
    version="0.1.0",
    lifespan=lifespan
)

# CORS
cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

async def get_org_settings(org_id: str) -> dict:
    """Get settings for an org with defaults."""
    defaults = {
        "auto_confirm": False,
        "extraction_model": os.getenv("KOMPONIST_LLM_MODEL", "gpt-5.6-terra"),
        "parallel_batch_size": 5,
    }
    settings = await load_org_settings(org_id) or {}
    return {**defaults, **settings}


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Komponist API",
        "version": "0.1.0",
        "tagline": "The programmable company brain"
    }


class DemoQueryRequest(BaseModel):
    question: str = Field(min_length=3, max_length=240)


_DEMO_FACTS = [
    {
        "id": "demo-pilot-goal",
        "type": "Goal",
        "statement": "The pilot goal is to onboard 10 design partners in 4 weeks.",
        "detail": "The team reviews progress with design partners every week.",
        "source": "01-product-strategy.md",
        "excerpt": "Goal: Onboard 10 design partners during a four-week pilot.",
    },
    {
        "id": "demo-review-constraint",
        "type": "Constraint",
        "statement": "Every extracted fact requires human review before it becomes trusted company context.",
        "detail": "Only confirmed facts are available to chat, API, and MCP consumers.",
        "source": "02-review-policy.md",
        "excerpt": "Constraint: Extracted knowledge must be reviewed before it can be trusted.",
    },
    {
        "id": "demo-agent-access",
        "type": "Decision",
        "statement": "Agents access confirmed company context through Komponist's REST API or MCP server.",
        "detail": "People use Studio while products and agents use organization-scoped credentials.",
        "source": "03-agent-integration.md",
        "excerpt": "Decision: Serve the same confirmed context through Studio, REST API, and MCP.",
    },
    {
        "id": "demo-launch-project",
        "type": "Project",
        "statement": "The MVP launch flow is upload, extraction, human review, then cited search.",
        "detail": "The first vertical slice keeps evidence attached throughout the workflow.",
        "source": "04-mvp-scope.md",
        "excerpt": "Project: Ship upload → extraction → review → cited search as one reliable loop.",
    },
]

_DEMO_STOP_WORDS = {
    "a", "an", "and", "are", "before", "can", "company", "do", "does",
    "for", "from", "has", "how", "in", "is", "it", "of", "our", "the",
    "to", "we", "what", "which", "with",
}


def _demo_query_terms(value: str) -> set[str]:
    return {
        term for term in re.findall(r"[a-z0-9]+", value.casefold())
        if len(term) > 1 and term not in _DEMO_STOP_WORDS
    }


def _rank_demo_facts(question: str) -> List[dict]:
    question_terms = _demo_query_terms(question)
    ranked = []
    for fact in _DEMO_FACTS:
        searchable = " ".join([
            fact["type"], fact["statement"], fact["detail"], fact["excerpt"]
        ])
        fact_terms = _demo_query_terms(searchable)
        overlap = question_terms & fact_terms
        score = len(overlap)
        if fact["type"].casefold() in question_terms:
            score += 2
        ranked.append((score, fact))
    ranked.sort(key=lambda item: item[0], reverse=True)
    best_score = ranked[0][0]
    if best_score == 0:
        return [_DEMO_FACTS[3]]
    return [fact for score, fact in ranked if score == best_score][:2]


@app.post("/demo/query")
async def query_demo(payload: DemoQueryRequest):
    """Query a fixed, read-only workspace used by the public landing-page demo."""
    matches = _rank_demo_facts(payload.question)
    sources = [
        {
            "id": fact["id"],
            "number": index,
            "title": fact["source"],
            "excerpt": fact["excerpt"],
            "type": fact["type"],
        }
        for index, fact in enumerate(matches, start=1)
    ]
    citations = " ".join(f"[{source['number']}]" for source in sources)
    return {
        "mode": "demo",
        "workspace": "Komponist demo workspace",
        "question": payload.question,
        "answer": f"{matches[0]['statement']} {citations}",
        "sources": sources,
        "trace": ["Demo source matched", "Confirmed fact selected", "Citation attached"],
    }


@app.get("/healthz")
async def health_check():
    """
    Health check endpoint.

    Verifies connectivity to Neo4j and Postgres.
    """
    neo4j_health = await GraphClient.health_check()
    postgres_health = await health_check_db()

    overall_healthy = (
        neo4j_health["status"] == "healthy" and
        postgres_health["status"] == "healthy"
    )

    return {
        "status": "healthy" if overall_healthy else "degraded",
        "services": {
            "neo4j": neo4j_health,
            "postgres": postgres_health
        }
    }


# Queue and entity management routes


class ConfirmEntityRequest(BaseModel):
    statement: Optional[str] = None


class MergeEntityRequest(BaseModel):
    target_id: str


class OrgSettingsUpdate(BaseModel):
    auto_confirm: Optional[bool] = None
    parallel_batch_size: Optional[int] = None


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class ApprovalResolutionRequest(BaseModel):
    approved: bool


async def _authorized_org_user(
    request: Request,
    org_id: str,
    *,
    manage: bool = False,
    write: bool = False,
) -> dict:
    import auth

    try:
        user = await auth.authorize_organization(
            request.cookies.get(auth.SESSION_COOKIE),
            org_id,
            (
                {"owner", "admin"}
                if manage
                else {"owner", "admin", "member"} if write else None
            ),
        )
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def _knowledge_scope_params(user: dict) -> dict:
    return {
        "access_all_departments": bool(user.get("access_all_departments")),
        "department_ids": user.get("department_ids") or [],
    }


def _knowledge_scope(alias: str) -> str:
    """Cypher predicate for organization-wide or department-visible knowledge."""
    return (
        f"($access_all_departments OR size(coalesce({alias}.department_ids, [])) = 0 "
        f"OR any(department_id IN coalesce({alias}.department_ids, []) "
        "WHERE department_id IN $department_ids))"
    )


def _evidence_scope(alias: str) -> str:
    return (
        f"($access_all_departments OR {alias}.department_id IS NULL "
        f"OR {alias}.department_id IN $department_ids)"
    )


def _scoped_params(org_id: str, user: dict, **values: Any) -> dict:
    return {"org_id": org_id, **_knowledge_scope_params(user), **values}


async def _validate_department_scope(
    org_id: str,
    user: dict,
    department_id: Optional[str],
    *,
    require_for_limited_member: bool = False,
) -> Optional[str]:
    if department_id is None:
        if require_for_limited_member and not user.get("access_all_departments"):
            raise HTTPException(
                status_code=403,
                detail="Choose one of your departments before adding knowledge",
            )
        return None
    async with async_session() as session:
        department = await session.get(Department, department_id)
    if department is None or department.org_id != org_id:
        raise HTTPException(status_code=400, detail="Department not found")
    if (
        not user.get("access_all_departments")
        and department_id not in (user.get("department_ids") or [])
    ):
        raise HTTPException(
            status_code=403,
            detail="You can only add knowledge to one of your departments",
        )
    return department_id


def _source_visible_to_user(source: dict, user: dict) -> bool:
    department_id = source.get("departmentId")
    return bool(
        user.get("access_all_departments")
        or department_id is None
        or department_id in (user.get("department_ids") or [])
    )


async def _get_entity_lifecycle(entity_id: str, org_id: str, user: dict) -> dict:
    """Load the lifecycle fields required by review mutations."""
    result = await GraphClient.run_query(
        f"""
        MATCH (e:Entity {{id: $entity_id, org_id: $org_id}})
        WHERE {_knowledge_scope('e')}
        RETURN e.id AS id, e.entity_type AS entity_type, e.status AS status
        """,
        _scoped_params(org_id, user, entity_id=entity_id),
    )
    if not result:
        raise HTTPException(status_code=404, detail="Entity not found")
    return result[0]


@app.get("/queue")
async def get_queue(request: Request, org_id: str = Query(...)):
    """Get review queue (proposed entities)."""
    user = await _authorized_org_user(request, org_id)
    query = f"""
    MATCH (e:Entity {{org_id: $org_id, status: 'proposed'}})
    WHERE {_knowledge_scope('e')}
    OPTIONAL MATCH (e)-[:CITED_BY]->(ev:Evidence)
    WHERE {_evidence_scope('ev')}
    OPTIONAL MATCH (e)-[r:RELATES_TO]->(related:Entity)
    WHERE r IS NULL OR (r.score > 0.80 AND {_knowledge_scope('related')})
    RETURN
        e.id as id,
        e.entity_type as entity_type,
        e.statement as statement,
        e.detail as detail,
        e.confidence as confidence,
        toString(e.created_at) as created_at,
        collect(DISTINCT {{
            id: ev.id,
            source: ev.source,
            reference: ev.reference,
            url: ev.url,
            source_date: toString(ev.source_date)
        }}) as evidence,
        collect(DISTINCT {{id: related.id, statement: related.statement, score: r.score}}) as related_to
    ORDER BY created_at DESC
    """

    results = await GraphClient.run_query(query, _scoped_params(org_id, user))

    # Filter out null evidence/related_to
    for r in results:
        r["evidence"] = [e for e in r.get("evidence", []) if e.get("id")]
        r["related_to"] = [rel for rel in r.get("related_to", []) if rel.get("id")]

    return {"items": results, "total": len(results)}


@app.get("/entities")
async def list_entities(
    request: Request,
    org_id: str = Query(...),
    status: str = "confirmed",
    entity_type: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
):
    """List brain entities."""
    user = await _authorized_org_user(request, org_id)
    allowed_statuses = {"confirmed", "proposed", "rejected", "all"}
    if status not in allowed_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"status must be one of {sorted(allowed_statuses)}",
        )

    query = f"""
    MATCH (e:Entity {{org_id: $org_id}})
    WHERE ($status = 'all' OR e.status = $status)
      AND ($entity_type IS NULL OR e.entity_type = $entity_type)
      AND {_knowledge_scope('e')}
    OPTIONAL MATCH (e)-[:CITED_BY]->(ev:Evidence)
    WHERE {_evidence_scope('ev')}
    RETURN
        e.id as id,
        e.entity_type as entity_type,
        e.statement as statement,
        e.detail as detail,
        e.status as status,
        e.confidence as confidence,
        toString(e.confirmed_at) as confirmed_at,
        toString(e.created_at) as created_at,
        collect(ev{{.id, .source, .reference, .url}}) as evidence
    ORDER BY confirmed_at DESC, created_at DESC
    LIMIT $limit
    """

    params = _scoped_params(
        org_id,
        user,
        status=status,
        entity_type=entity_type,
        limit=limit,
    )

    results = await GraphClient.run_query(query, params)
    type_counts = await GraphClient.run_query(
        f"""
        MATCH (e:Entity {{org_id: $org_id}})
        WHERE ($status = 'all' OR e.status = $status)
          AND ($entity_type IS NULL OR e.entity_type = $entity_type)
          AND {_knowledge_scope('e')}
        RETURN e.entity_type AS entity_type, count(e) AS count
        ORDER BY entity_type
        """,
        params,
    )
    status_counts = await GraphClient.run_query(
        f"""
        MATCH (e:Entity {{org_id: $org_id}})
        WHERE ($entity_type IS NULL OR e.entity_type = $entity_type)
          AND {_knowledge_scope('e')}
        RETURN e.status AS status, count(e) AS count
        ORDER BY status
        """,
        params,
    )

    # Filter nulls
    for r in results:
        r["evidence"] = [e for e in r.get("evidence", []) if e.get("id")]

    counts_by_type = {
        row["entity_type"]: row["count"]
        for row in type_counts
        if row.get("entity_type")
    }
    counts_by_status = {
        row["status"]: row["count"]
        for row in status_counts
        if row.get("status")
    }

    return {
        "entities": results,
        "total": sum(counts_by_type.values()),
        "counts_by_type": counts_by_type,
        "counts_by_status": counts_by_status,
    }


@app.get("/entities/{entity_id}")
async def get_entity(entity_id: str, request: Request, org_id: str = Query(...)):
    """Get entity details."""
    user = await _authorized_org_user(request, org_id)
    query = f"""
    MATCH (e:Entity {{id: $entity_id, org_id: $org_id}})
    WHERE {_knowledge_scope('e')}
    OPTIONAL MATCH (e)-[:CITED_BY]->(ev:Evidence)
    WHERE {_evidence_scope('ev')}
    OPTIONAL MATCH (e)-[r:SUPERSEDES]->(old:Entity)
    WHERE old IS NULL OR {_knowledge_scope('old')}
    RETURN
        e.id as id,
        e.entity_type as entity_type,
        e.statement as statement,
        e.detail as detail,
        e.status as status,
        e.confidence as confidence,
        e.created_at as created_at,
        e.confirmed_at as confirmed_at,
        collect(DISTINCT ev{{.id, .source, .reference, .url, .excerpt, .source_date}}) as evidence,
        collect(DISTINCT old{{.id, .statement, .status}}) as superseded
    """

    results = await GraphClient.run_query(
        query, _scoped_params(org_id, user, entity_id=entity_id)
    )

    if not results:
        raise HTTPException(status_code=404, detail="Entity not found")

    entity = results[0]
    entity["evidence"] = [e for e in entity.get("evidence", []) if e.get("id")]
    entity["superseded"] = [s for s in entity.get("superseded", []) if s.get("id")]

    return entity


@app.get("/entities/{entity_id}/neighborhood")
async def get_entity_neighborhood(
    entity_id: str, request: Request, org_id: str = Query(...)
):
    """Get entity 1-hop neighborhood."""
    user = await _authorized_org_user(request, org_id)
    params = _scoped_params(org_id, user, entity_id=entity_id)
    seed_rows = await GraphClient.run_query(
        f"""
        MATCH (seed:Entity {{id: $entity_id, org_id: $org_id}})
        WHERE {_knowledge_scope('seed')}
        OPTIONAL MATCH (seed)-[:CITED_BY]->(evidence:Evidence {{org_id: $org_id}})
        WHERE {_evidence_scope('evidence')}
        RETURN seed{{.id, .entity_type, .statement, .detail, .status, .confidence}} AS seed,
               collect(DISTINCT evidence{{.id, .source, .reference, .url, .excerpt}}) AS evidence
        """,
        params,
    )
    if not seed_rows:
        return {"seeds": [], "neighbors": [], "evidence": []}
    neighbor_rows = await GraphClient.run_query(
        f"""
        MATCH (seed:Entity {{id: $entity_id, org_id: $org_id}})
              -[:SUPERSEDES|AFFECTS|SUPPORTS|ADVANCES|CONSTRAINS|RELATES_TO]-(neighbor:Entity {{org_id: $org_id}})
        WHERE neighbor.status = 'confirmed' AND {_knowledge_scope('neighbor')}
        OPTIONAL MATCH (neighbor)-[:CITED_BY]->(evidence:Evidence {{org_id: $org_id}})
        WHERE {_evidence_scope('evidence')}
        RETURN neighbor{{.id, .entity_type, .statement, .detail, .status}} AS neighbor,
               collect(DISTINCT evidence{{.id, .source, .reference, .url, .excerpt}}) AS evidence
        """,
        params,
    )
    evidence = [item for item in seed_rows[0].get("evidence", []) if item.get("id")]
    neighbors = []
    for row in neighbor_rows:
        if row.get("neighbor"):
            neighbors.append(row["neighbor"])
        evidence.extend(item for item in row.get("evidence", []) if item.get("id"))
    return {
        "seeds": [seed_rows[0]["seed"]],
        "neighbors": list({item["id"]: item for item in neighbors}.values()),
        "evidence": list({item["id"]: item for item in evidence}.values()),
    }


@app.post("/entities/{entity_id}/confirm")
async def confirm_entity(
    entity_id: str,
    request: Request,
    payload: Optional[ConfirmEntityRequest] = None,
    org_id: str = Query(...),
    statement: Optional[str] = None,
):
    """Confirm a proposed entity."""
    user = await _authorized_org_user(request, org_id, write=True)
    entity = await _get_entity_lifecycle(entity_id, org_id, user)
    if entity["status"] != "proposed":
        raise HTTPException(
            status_code=409,
            detail="Only proposed entities can be confirmed",
        )

    edited_statement = payload.statement if payload else statement
    if edited_statement is not None:
        edited_statement = edited_statement.strip()
        if not edited_statement:
            raise HTTPException(status_code=422, detail="statement cannot be empty")

    # Update statement if provided
    if edited_statement:
        query = f"""
        MATCH (e:Entity {{id: $entity_id, org_id: $org_id, status: 'proposed'}})
        WHERE {_knowledge_scope('e')}
        SET e.statement = $statement,
            e.status = 'confirmed',
            e.confirmed_at = datetime(),
            e.updated_at = datetime()
        RETURN e.id as id, e.status as status
        """
        params = _scoped_params(
            org_id, user, entity_id=entity_id, statement=edited_statement
        )
    else:
        query = f"""
        MATCH (e:Entity {{id: $entity_id, org_id: $org_id, status: 'proposed'}})
        WHERE {_knowledge_scope('e')}
        SET e.status = 'confirmed',
            e.confirmed_at = datetime(),
            e.updated_at = datetime()
        RETURN e.id as id, e.status as status
        """
        params = _scoped_params(org_id, user, entity_id=entity_id)

    result = await GraphClient.run_query(query, params)

    if not result:
        raise HTTPException(status_code=409, detail="Entity lifecycle changed")

    return result[0]


@app.post("/entities/{entity_id}/reject")
async def reject_entity(
    entity_id: str, request: Request, org_id: str = Query(...)
):
    """Reject a proposed entity."""
    user = await _authorized_org_user(request, org_id, write=True)
    entity = await _get_entity_lifecycle(entity_id, org_id, user)
    if entity["status"] != "proposed":
        raise HTTPException(
            status_code=409,
            detail="Only proposed entities can be rejected",
        )

    query = f"""
    MATCH (e:Entity {{id: $entity_id, org_id: $org_id, status: 'proposed'}})
    WHERE {_knowledge_scope('e')}
    SET e.status = 'rejected',
        e.updated_at = datetime()
    RETURN e.id as id, e.status as status
    """

    result = await GraphClient.run_query(
        query, _scoped_params(org_id, user, entity_id=entity_id)
    )

    if not result:
        raise HTTPException(status_code=409, detail="Entity lifecycle changed")

    return result[0]


@app.post("/entities/{entity_id}/merge")
async def merge_entity(
    entity_id: str,
    request: Request,
    payload: Optional[MergeEntityRequest] = None,
    target_id: Optional[str] = None,
    org_id: str = Query(...),
):
    """Merge entity into another."""
    user = await _authorized_org_user(request, org_id, write=True)
    resolved_target_id = payload.target_id if payload else target_id
    if not resolved_target_id:
        raise HTTPException(status_code=422, detail="target_id is required")
    if resolved_target_id == entity_id:
        raise HTTPException(status_code=422, detail="Cannot merge an entity into itself")

    source = await _get_entity_lifecycle(entity_id, org_id, user)
    target = await _get_entity_lifecycle(resolved_target_id, org_id, user)
    if source["status"] != "proposed":
        raise HTTPException(
            status_code=409,
            detail="Only proposed entities can be merged",
        )
    if target["status"] not in {"proposed", "confirmed"}:
        raise HTTPException(
            status_code=409,
            detail="Merge target must be proposed or confirmed",
        )
    if source["entity_type"] != target["entity_type"]:
        raise HTTPException(
            status_code=409,
            detail="Entities must have the same type to be merged",
        )

    # Attach the source entity's evidence to the target, then delete source
    query = f"""
    MATCH (source:Entity {{id: $entity_id, org_id: $org_id}})
    MATCH (target:Entity {{id: $target_id, org_id: $org_id}})
    WHERE {_knowledge_scope('source')} AND {_knowledge_scope('target')}
    OPTIONAL MATCH (source)-[:CITED_BY]->(ev:Evidence)
    WHERE {_evidence_scope('ev')}
    WITH source, target, collect(ev) as evidences
    FOREACH (ev IN evidences |
        MERGE (target)-[:CITED_BY]->(ev)
    )
    DETACH DELETE source
    RETURN target.id as target_id, size(evidences) as evidence_moved
    """

    result = await GraphClient.run_query(
        query,
        _scoped_params(
            org_id, user, entity_id=entity_id, target_id=resolved_target_id
        ),
    )

    if not result:
        raise HTTPException(status_code=409, detail="Entity lifecycle changed")

    await _recalculate_entity_department_scopes(org_id)

    return {
        "merged": entity_id,
        "into": resolved_target_id,
        "evidence_moved": result[0]["evidence_moved"],
    }


# Webhook handlers
@app.post("/webhooks/github")
async def github_webhook(request: Request, org_id: str = Query(...)):
    """Verify and persist an organization-scoped GitHub event."""
    from integrations.github import handle_github_webhook

    if not validate_org_id(org_id):
        raise HTTPException(status_code=400, detail="Invalid organization ID")
    return await handle_github_webhook(request, org_id)


@app.post("/webhooks/slack")
async def slack_webhook(request: Request, org_id: str = Query(...)):
    """Verify and persist an organization-scoped Slack event."""
    from integrations.slack import handle_slack_webhook

    if not validate_org_id(org_id):
        raise HTTPException(status_code=400, detail="Invalid organization ID")
    return await handle_slack_webhook(request, org_id)


@app.post("/webhooks/slack/interactions")
async def slack_interaction(request: Request, org_id: str = Query(...)):
    """Resolve durable MCP approval requests from signed Slack buttons."""
    from urllib.parse import parse_qs
    from integrations.slack import verify_slack_signature

    if not validate_org_id(org_id):
        raise HTTPException(status_code=400, detail="Invalid organization ID")
    body = await request.body()
    if not verify_slack_signature(
        body,
        request.headers.get("X-Slack-Request-Timestamp", ""),
        request.headers.get("X-Slack-Signature", ""),
    ):
        raise HTTPException(status_code=401, detail="Invalid signature")
    try:
        form = parse_qs(body.decode("utf-8"), strict_parsing=True)
        payload = json.loads(form["payload"][0])
        action = payload["actions"][0]
        action_id = str(action["action_id"])
        approval_id = str(action["value"])
        resolved_by = str(payload.get("user", {}).get("id") or "slack")
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=400, detail="Invalid Slack interaction") from error
    if action_id.startswith("approve_"):
        approved = True
    elif action_id.startswith("deny_"):
        approved = False
    else:
        raise HTTPException(status_code=400, detail="Unsupported Slack action")
    approval = await resolve_approval_request(
        org_id, approval_id, approved, resolved_by
    )
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval request not found")
    return {"status": approval["status"], "approval_id": approval_id}


@app.post("/webhooks/notion")
async def notion_webhook():
    """Notion does not expose a supported webhook for this connector."""
    raise HTTPException(status_code=501, detail="Notion webhook ingestion is not supported")


@app.post("/webhooks/google")
async def google_webhook(request: Request, org_id: str = Query(...)):
    """Validate and persist a Google Drive change notification."""
    from integrations.google import handle_google_webhook

    if not validate_org_id(org_id):
        raise HTTPException(status_code=400, detail="Invalid organization ID")
    return await handle_google_webhook(request, org_id)


@app.post("/webhooks/linear")
async def linear_webhook(request: Request, org_id: str = Query(...)):
    """Verify and persist an organization-scoped Linear event."""
    from integrations.linear import handle_linear_webhook

    if not validate_org_id(org_id):
        raise HTTPException(status_code=400, detail="Invalid organization ID")
    return await handle_linear_webhook(request, org_id)


FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")


# =============================================================================
# User authentication endpoints
# =============================================================================

class OrganizationInvitationRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    role: str = Field(default="member", max_length=20)
    department_ids: List[str] = Field(default_factory=list, max_length=25)


class DepartmentCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    color: str = Field(default="orange", max_length=20)


class DepartmentUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    color: Optional[str] = Field(default=None, max_length=20)


class OrganizationMemberUpdateRequest(BaseModel):
    role: Optional[str] = Field(default=None, max_length=20)
    department_ids: Optional[List[str]] = Field(default=None, max_length=25)


class AcceptInvitationRequest(BaseModel):
    token: str = Field(min_length=20, max_length=200)


class EmailRegistrationRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=12, max_length=128)


class EmailLoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class NotionTokenRequest(BaseModel):
    token: str = Field(min_length=10, max_length=512)


def _set_session_cookie(response: Response, raw_token: str) -> None:
    import auth

    response.set_cookie(
        key=auth.SESSION_COOKIE,
        value=raw_token,
        max_age=auth.SESSION_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=os.getenv("KOMPONIST_COOKIE_SECURE", "false").lower() == "true",
        samesite="lax",
        path="/",
    )


def _check_auth_rate_limit(request: Request) -> None:
    client_host = request.client.host if request.client else "unknown"
    if not check_rate_limit(f"user-auth:{client_host}", limit=10):
        raise HTTPException(status_code=429, detail="Too many authentication attempts")


@app.post("/auth/register", status_code=201)
async def register_with_email(
    payload: EmailRegistrationRequest,
    request: Request,
    response: Response,
):
    """Create an email/password user and issue the standard session cookie."""
    import auth

    _check_auth_rate_limit(request)
    try:
        user = await auth.register_password_user(
            payload.name, payload.email, payload.password
        )
    except ValueError as error:
        status = 409 if "already exists" in str(error) else 400
        raise HTTPException(status_code=status, detail=str(error)) from error
    raw_token, _ = await auth.create_session(user.id)
    _set_session_cookie(response, raw_token)
    return {"user": await auth.authenticated_user(raw_token)}


@app.post("/auth/login/email")
async def login_with_email(
    payload: EmailLoginRequest,
    request: Request,
    response: Response,
):
    """Authenticate a first-party password without revealing which field failed."""
    import auth

    _check_auth_rate_limit(request)
    user = await auth.authenticate_password_user(payload.email, payload.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    raw_token, _ = await auth.create_session(user.id)
    _set_session_cookie(response, raw_token)
    return {"user": await auth.authenticated_user(raw_token)}

@app.get("/auth/login/google")
async def google_login_start(return_to: str = "/"):
    """Start Google OIDC login for a Komponist user."""
    import auth

    if not auth.GOOGLE_AUTH_CLIENT_ID or not auth.GOOGLE_AUTH_CLIENT_SECRET:
        raise HTTPException(status_code=503, detail="Google user login is not configured")
    state = await auth.create_login_state(return_to)
    response = RedirectResponse(auth.google_authorization_url(state))
    response.set_cookie(
        key=auth.LOGIN_STATE_COOKIE,
        value=state,
        max_age=auth.STATE_MINUTES * 60,
        httponly=True,
        secure=os.getenv("KOMPONIST_COOKIE_SECURE", "false").lower() == "true",
        samesite="lax",
        path="/auth/login/google/callback",
    )
    return response


@app.get("/auth/login/google/callback")
async def google_login_callback(request: Request, code: str, state: str):
    """Complete Google login and issue a persistent HttpOnly session cookie."""
    import auth

    if not auth.login_state_matches(
        state, request.cookies.get(auth.LOGIN_STATE_COOKIE)
    ):
        raise HTTPException(status_code=400, detail="Login state does not match browser")
    return_to = await auth.consume_login_state(state)
    if return_to is None:
        raise HTTPException(status_code=400, detail="Invalid or expired login state")
    try:
        tokens = await auth.exchange_google_code(code)
        identity = await auth.fetch_google_identity(tokens["access_token"])
        user = await auth.upsert_google_user(identity)
        raw_token, _ = await auth.create_session(user.id)
    except (httpx.HTTPError, ValueError) as error:
        print(f"[User Auth] Google callback failed: {type(error).__name__}")
        raise HTTPException(status_code=400, detail="Google login failed") from error

    response = RedirectResponse(f"{FRONTEND_URL}{return_to}")
    _set_session_cookie(response, raw_token)
    response.delete_cookie(
        auth.LOGIN_STATE_COOKIE,
        path="/auth/login/google/callback",
        secure=os.getenv("KOMPONIST_COOKIE_SECURE", "false").lower() == "true",
        httponly=True,
        samesite="lax",
    )
    return response


@app.get("/auth/session")
async def get_auth_session(request: Request):
    """Return the current browser session without exposing its bearer token."""
    import auth

    user = await auth.authenticated_user(request.cookies.get(auth.SESSION_COOKIE))
    return {"authenticated": user is not None, "user": user}


@app.post("/auth/logout", status_code=204)
async def logout(request: Request, response: Response):
    """Revoke the current session and clear its browser cookie."""
    import auth

    await auth.revoke_session(request.cookies.get(auth.SESSION_COOKIE))
    response.delete_cookie(
        auth.SESSION_COOKIE,
        path="/",
        secure=os.getenv("KOMPONIST_COOKIE_SECURE", "false").lower() == "true",
        httponly=True,
        samesite="lax",
    )


@app.get("/auth/organizations")
async def get_auth_organizations(request: Request):
    """List all organizations the signed-in user belongs to."""
    import auth

    organizations = await auth.list_organizations(
        request.cookies.get(auth.SESSION_COOKIE)
    )
    if organizations is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return {"organizations": organizations}


@app.post("/auth/organizations/{org_id}/select")
async def select_auth_organization(org_id: str, request: Request):
    """Switch the active organization for the current browser session."""
    import auth

    try:
        user = await auth.select_organization(
            request.cookies.get(auth.SESSION_COOKIE), org_id
        )
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return {"user": user}


@app.get("/auth/organizations/{org_id}/members")
async def get_organization_members(org_id: str, request: Request):
    """List active members of an organization visible to the signed-in user."""
    import auth

    try:
        members = await auth.list_organization_members(
            request.cookies.get(auth.SESSION_COOKIE), org_id
        )
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    if members is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return {"members": members}


@app.patch("/auth/organizations/{org_id}/members/{membership_id}")
async def update_organization_member(
    org_id: str,
    membership_id: str,
    payload: OrganizationMemberUpdateRequest,
    request: Request,
):
    """Change a member's governance role and department assignments."""
    import auth

    try:
        member = await auth.update_organization_member(
            request.cookies.get(auth.SESSION_COOKIE),
            org_id,
            membership_id,
            role=payload.role,
            department_ids=payload.department_ids,
        )
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if member is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return member


@app.delete("/auth/organizations/{org_id}/members/{membership_id}", status_code=204)
async def remove_organization_member(
    org_id: str, membership_id: str, request: Request
):
    """Remove a non-owner member from an organization."""
    import auth

    try:
        member = await auth.remove_organization_member(
            request.cookies.get(auth.SESSION_COOKIE), org_id, membership_id
        )
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    if member is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return Response(status_code=204)


@app.get("/auth/organizations/{org_id}/departments")
async def get_organization_departments(org_id: str, request: Request):
    """List departments the active organization member can access."""
    import auth

    try:
        departments = await auth.list_organization_departments(
            request.cookies.get(auth.SESSION_COOKIE), org_id
        )
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    if departments is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return {"departments": departments}


@app.post("/auth/organizations/{org_id}/departments", status_code=201)
async def create_organization_department(
    org_id: str, payload: DepartmentCreateRequest, request: Request
):
    """Create a department access boundary."""
    import auth

    try:
        department = await auth.create_organization_department(
            request.cookies.get(auth.SESSION_COOKIE),
            org_id,
            payload.name,
            payload.description,
            payload.color,
        )
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if department is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return department


@app.patch("/auth/organizations/{org_id}/departments/{department_id}")
async def update_organization_department(
    org_id: str,
    department_id: str,
    payload: DepartmentUpdateRequest,
    request: Request,
):
    """Rename or restyle an existing department."""
    import auth

    try:
        department = await auth.update_organization_department(
            request.cookies.get(auth.SESSION_COOKIE),
            org_id,
            department_id,
            name=payload.name,
            description=payload.description,
            color=payload.color,
        )
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if department is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return department


async def _recalculate_entity_department_scopes(org_id: str) -> None:
    """Derive every entity scope from the evidence currently attached to it."""
    await GraphClient.run_query(
        """
        MATCH (entity:Entity {org_id: $org_id})
        OPTIONAL MATCH (entity)-[:CITED_BY]->(evidence:Evidence {org_id: $org_id})
        WITH entity,
             collect(DISTINCT evidence.department_id) AS scoped_departments,
             sum(CASE WHEN evidence.department_id IS NULL THEN 1 ELSE 0 END) AS global_evidence
        SET entity.department_ids = CASE
            WHEN global_evidence > 0 THEN []
            ELSE scoped_departments
        END
        """,
        {"org_id": org_id},
    )


@app.delete("/auth/organizations/{org_id}/departments/{department_id}")
async def delete_organization_department(
    org_id: str,
    department_id: str,
    request: Request,
    reassign_to: Optional[str] = Query(default=None),
):
    """Delete a department, optionally moving its people and knowledge first."""
    import auth

    if reassign_to is None:
        scoped_content = await GraphClient.run_query(
            """
            MATCH (evidence:Evidence {org_id: $org_id, department_id: $department_id})
            RETURN count(evidence) AS count
            """,
            {"org_id": org_id, "department_id": department_id},
        )
        if scoped_content and scoped_content[0].get("count", 0) > 0:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Move this department's knowledge to another department before "
                    "deleting it"
                ),
            )
    try:
        result = await auth.delete_organization_department(
            request.cookies.get(auth.SESSION_COOKIE),
            org_id,
            department_id,
            reassign_to,
        )
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if result is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    await GraphClient.run_query(
        """
        MATCH (evidence:Evidence {org_id: $org_id, department_id: $department_id})
        SET evidence.department_id = $reassign_to
        """,
        {
            "org_id": org_id,
            "department_id": department_id,
            "reassign_to": reassign_to,
        },
    )
    await _recalculate_entity_department_scopes(org_id)
    return result


@app.post("/auth/organizations/{org_id}/invitations", status_code=201)
async def invite_organization_member(
    org_id: str,
    payload: OrganizationInvitationRequest,
    request: Request,
):
    """Create a single-use invite link. Email delivery will be added later."""
    import auth
    from urllib.parse import urlencode

    try:
        invitation = await auth.create_organization_invitation(
            request.cookies.get(auth.SESSION_COOKIE),
            org_id,
            payload.email,
            payload.role,
            payload.department_ids,
        )
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if invitation is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    invitation["invite_url"] = (
        f"{FRONTEND_URL}/invite?{urlencode({'token': invitation['token']})}"
    )
    return invitation


@app.post("/auth/invitations/accept")
async def accept_organization_invitation(
    payload: AcceptInvitationRequest,
    request: Request,
):
    """Accept an invite matching the signed-in user's verified Google email."""
    import auth

    try:
        user = await auth.accept_organization_invitation(
            request.cookies.get(auth.SESSION_COOKIE), payload.token
        )
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return {"user": user}


def _validated_oauth_org(org_id: str) -> str:
    """Accept only org identifiers that are safe to persist and redirect."""
    if not validate_org_id(org_id):
        raise HTTPException(status_code=400, detail="Invalid organization ID")
    return org_id


async def _connector_oauth_state(org_id: str) -> str:
    """Create a short-lived opaque connector state stored only as a hash."""
    org_id = _validated_oauth_org(org_id)
    state = f"komponist_oauth_{secrets.token_urlsafe(32)}"
    state_hash = hashlib.sha256(state.encode("utf-8")).hexdigest()
    now = datetime.utcnow()
    async with async_session() as session:
        await session.execute(
            delete(ConnectorOAuthState).where(
                ConnectorOAuthState.expires_at < now
            )
        )
        session.add(ConnectorOAuthState(
            state_hash=state_hash,
            org_id=org_id,
            expires_at=now + timedelta(minutes=10),
        ))
        await session.commit()
    return state


async def _connector_oauth_org(state: str) -> str:
    """Consume connector state once and return its authorized organization."""
    if not state.startswith("komponist_oauth_") or len(state) > 200:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")
    state_hash = hashlib.sha256(state.encode("utf-8")).hexdigest()
    now = datetime.utcnow()
    async with async_session() as session:
        row = (
            await session.execute(
                select(ConnectorOAuthState)
                .where(ConnectorOAuthState.state_hash == state_hash)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if row is None or row.consumed_at is not None or row.expires_at < now:
            raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")
        row.consumed_at = now
        await session.commit()
        return _validated_oauth_org(row.org_id)


def _oauth_redirect(source: str, org_id: str, status: str) -> RedirectResponse:
    """Build a callback redirect without reflecting provider errors or secrets."""
    from urllib.parse import urlencode

    query = urlencode({"source": source, "status": status, "org": org_id})
    return RedirectResponse(url=f"{FRONTEND_URL}/onboard?{query}")


def _required_oauth_token(tokens: dict, provider: str) -> str:
    token = tokens.get("access_token")
    if not isinstance(token, str) or not token.strip():
        raise ValueError(f"{provider} OAuth response contained no access token")
    return token.strip()


# =============================================================================
# Notion connector endpoints
# =============================================================================

@app.get("/auth/notion")
async def notion_auth_start(org: str, request: Request):
    """Start Notion OAuth flow."""
    from integrations.notion import get_oauth_url, NOTION_CLIENT_ID
    org = _validated_oauth_org(org)
    await _authorized_org_user(request, org, manage=True)
    if not NOTION_CLIENT_ID:
        return {"error": "NOTION_CLIENT_ID not configured. Use token-based auth instead.", "use_token": True}
    url = get_oauth_url(state=await _connector_oauth_state(org))
    return {"auth_url": url}


@app.post("/auth/notion/token")
async def notion_token_connect(
    payload: NotionTokenRequest,
    request: Request,
    org_id: str = Query(...),
    department_id: Optional[str] = Query(default=None),
):
    """
    Connect Notion using an Internal Integration token.

    This is the easy setup path - no OAuth app needed.
    User creates an integration at notion.so/my-integrations and pastes the token.
    """
    from integrations.notion import validate_token
    user = await _authorized_org_user(request, org_id, manage=True)
    department_id = await _validate_department_scope(org_id, user, department_id)
    token = payload.token.strip()
    # Validate the token
    user_info = await validate_token(token)

    # Get workspace/bot name
    bot_info = user_info.get("bot", {})
    workspace_name = bot_info.get("workspace_name", "Notion Workspace")

    await upsert_single_source_type(
        org_id=org_id,
        source_type="notion",
        name=workspace_name,
        config={"token": token},
        department_id=department_id,
    )

    print(f"[Notion] Token validated for org {org_id}: {workspace_name}")

    return {
        "status": "connected",
        "bot": bot_info,
        "name": workspace_name,
        "message": "Token validated. Share pages with your integration to sync them."
    }


@app.get("/auth/notion/callback")
async def notion_auth_callback(code: str, state: str):
    """Handle Notion OAuth callback."""
    from integrations.notion import exchange_code
    org_id = await _connector_oauth_org(state)
    try:
        tokens = await exchange_code(code)
        access_token = _required_oauth_token(tokens, "Notion")
        await upsert_single_source_type(
            org_id=org_id,
            source_type="notion",
            name=tokens.get("workspace_name") or "Notion Workspace",
            config={
                "token": access_token,
                "workspace_id": tokens.get("workspace_id"),
                "bot_id": tokens.get("bot_id"),
                "oauth": True,
            },
        )
        return _oauth_redirect("notion", org_id, "connected")
    except Exception as error:
        print(f"[Notion OAuth] Callback failed for org {org_id}: {type(error).__name__}")
        return _oauth_redirect("notion", org_id, "error")


@app.get("/auth/slack")
async def slack_auth_start(org: str, request: Request):
    """Start Slack OAuth flow."""
    from integrations.slack import get_oauth_url
    org = _validated_oauth_org(org)
    await _authorized_org_user(request, org, manage=True)
    url = get_oauth_url(state=await _connector_oauth_state(org))
    return {"auth_url": url}


@app.get("/auth/slack/callback")
async def slack_auth_callback(code: str, state: str):
    """Handle Slack OAuth callback."""
    from integrations.slack import exchange_code
    org_id = await _connector_oauth_org(state)
    try:
        tokens = await exchange_code(code)
        access_token = _required_oauth_token(tokens, "Slack")
        team = tokens.get("team") if isinstance(tokens.get("team"), dict) else {}
        await upsert_single_source_type(
            org_id=org_id,
            source_type="slack",
            name=team.get("name") or "Slack Workspace",
            config={
                "token": access_token,
                "team_id": team.get("id"),
                "bot_user_id": tokens.get("bot_user_id"),
                "scope": tokens.get("scope"),
                "oauth": True,
            },
        )
        return _oauth_redirect("slack", org_id, "connected")
    except Exception as error:
        print(f"[Slack OAuth] Callback failed for org {org_id}: {type(error).__name__}")
        return _oauth_redirect("slack", org_id, "error")


@app.get("/auth/google")
async def google_auth_start(org: str, request: Request):
    """Start Google OAuth flow."""
    from integrations.google import get_oauth_url
    org = _validated_oauth_org(org)
    await _authorized_org_user(request, org, manage=True)
    url = get_oauth_url(state=await _connector_oauth_state(org))
    return {"auth_url": url}


@app.get("/auth/google/callback")
async def google_auth_callback(code: str, state: str):
    """Handle Google OAuth callback."""
    from integrations.google import exchange_code
    org_id = await _connector_oauth_org(state)
    try:
        tokens = await exchange_code(code)
        access_token = _required_oauth_token(tokens, "Google")
        config = {
            "access_token": access_token,
            "expires_in": tokens.get("expires_in"),
            "scope": tokens.get("scope"),
            "token_type": tokens.get("token_type"),
            "oauth": True,
        }
        refresh_token = tokens.get("refresh_token")
        if isinstance(refresh_token, str) and refresh_token.strip():
            config["refresh_token"] = refresh_token.strip()
        await upsert_single_source_type(
            org_id=org_id,
            source_type="google",
            name="Google Workspace",
            config=config,
            preserve_existing_config=True,
        )
        return _oauth_redirect("google", org_id, "connected")
    except Exception as error:
        print(f"[Google OAuth] Callback failed for org {org_id}: {type(error).__name__}")
        return _oauth_redirect("google", org_id, "error")


# =============================================================================
# Export / Import endpoints
# =============================================================================

@app.get("/export", response_class=PlainTextResponse)
async def export_brain_endpoint(
    request: Request,
    org_id: str = Query("default-org", description="Organization ID to export"),
    include_embeddings: bool = Query(False, description="Include embedding vectors (large!)"),
    include_rejected: bool = Query(False, description="Include rejected entities")
):
    """
    Export the brain to portable YAML format.

    Returns a YAML file containing all entities, relationships, evidence,
    and workpacks for the organization.
    """
    await _authorized_org_user(request, org_id, manage=True)
    yaml_content = await export_brain_yaml(
        org_id=org_id,
        include_embeddings=include_embeddings,
        include_rejected=include_rejected
    )
    safe_org_id = re.sub(r"[^a-z0-9_-]+", "-", org_id.casefold()).strip("-")

    return PlainTextResponse(
        content=yaml_content,
        media_type="application/x-yaml",
        headers={
            "Content-Disposition": f"attachment; filename=komponist-export-{safe_org_id}.yaml"
        }
    )


@app.get("/export/summary")
async def export_summary(
    request: Request,
    org_id: str = Query(..., description="Organization ID to summarize"),
):
    """Preview the organization-scoped data contained in an export."""
    await _authorized_org_user(request, org_id, manage=True)
    entity_rows = await GraphClient.run_query(
        """
        MATCH (entity:Entity {org_id: $org_id})
        RETURN count(entity) AS total,
               sum(CASE WHEN entity.status = 'confirmed' THEN 1 ELSE 0 END) AS confirmed,
               sum(CASE WHEN entity.status = 'proposed' THEN 1 ELSE 0 END) AS proposed,
               sum(CASE WHEN entity.status = 'rejected' THEN 1 ELSE 0 END) AS rejected
        """,
        {"org_id": org_id},
    )
    type_rows = await GraphClient.run_query(
        """
        MATCH (entity:Entity {org_id: $org_id})
        RETURN entity.entity_type AS type, count(entity) AS count
        ORDER BY count DESC, type ASC
        """,
        {"org_id": org_id},
    )
    graph_rows = await GraphClient.run_query(
        """
        OPTIONAL MATCH (:Entity {org_id: $org_id})-[relationship]->(:Entity {org_id: $org_id})
        WHERE type(relationship) IN [
            'SUPERSEDES', 'AFFECTS', 'SUPPORTS', 'ADVANCES',
            'CONSTRAINS', 'RELATES_TO'
        ]
        WITH count(relationship) AS relationships
        OPTIONAL MATCH (evidence:Evidence {org_id: $org_id})
        RETURN relationships, count(evidence) AS evidence
        """,
        {"org_id": org_id},
    )
    sources = await list_connected_sources(org_id)
    entity_summary = entity_rows[0] if entity_rows else {
        "total": 0, "confirmed": 0, "proposed": 0, "rejected": 0
    }
    graph_summary = graph_rows[0] if graph_rows else {
        "relationships": 0, "evidence": 0
    }
    return {
        "entities": entity_summary,
        "by_type": {row["type"]: row["count"] for row in type_rows if row["type"]},
        "relationships": graph_summary["relationships"],
        "evidence": graph_summary["evidence"],
        "connected_sources": len(sources),
    }


@app.post("/import")
async def import_brain_endpoint(
    request: Request,
    file: UploadFile = File(..., description="YAML export file to import"),
    org_id: Optional[str] = Query(None, description="Override org_id (uses export's if not provided)"),
    mode: str = Query("merge", description="Import mode: merge, replace, or skip_existing")
):
    """
    Import a brain export.

    Modes:
    - merge: Update existing entities, create new ones (default)
    - skip_existing: Only import entities that don't exist
    - replace: Clear and replace all data (dangerous!)
    """
    if mode not in ["merge", "skip_existing", "replace"]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode: {mode}. Use merge, skip_existing, or replace.",
        )

    # Read uploaded file
    content = await file.read()
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Import file exceeds 25 MB")
    try:
        yaml_content = content.decode("utf-8")
        export_data = parse_export_yaml(yaml_content)
    except (UnicodeDecodeError, ValueError) as error:
        raise HTTPException(status_code=400, detail="Invalid YAML export") from error
    export_meta = export_data.get("komponist_export", {}) if isinstance(export_data, dict) else {}
    target_org = org_id or export_meta.get("org_id")
    if not isinstance(target_org, str) or not validate_org_id(target_org):
        raise HTTPException(status_code=400, detail="A valid target organization is required")
    await _authorized_org_user(request, target_org, manage=True)

    # Import
    result = await import_brain_yaml(
        yaml_content=yaml_content,
        org_id=target_org,
        mode=mode
    )

    return result


# =============================================================================
# Sources management
# =============================================================================

SOURCE_EVIDENCE_TYPES = {
    "notion": ["notion"],
    "slack": ["slack"],
    "google": ["google"],
    "local": ["manual"],
    "upload": ["upload"],
}


class SourceDepartmentUpdate(BaseModel):
    department_id: Optional[str] = None


class SourceDocumentDepartmentUpdate(BaseModel):
    reference: str = Field(min_length=1, max_length=2048)
    department_id: Optional[str] = None


def _source_evidence_types(source_type: str) -> list[str]:
    return SOURCE_EVIDENCE_TYPES.get(source_type.lower(), [source_type.lower()])


def _document_title(reference: str) -> str:
    """Create a human label for legacy evidence without a persisted title."""
    if reference.startswith("upload:"):
        parts = reference.split(":")
        if len(parts) > 2:
            return ":".join(parts[1:-1])
    if reference.startswith(("local:", "manual:")):
        return Path(reference.split(":", 1)[1]).name
    return reference


@app.get("/sources")
async def list_sources(request: Request, org_id: str = Query(...)):
    """List connected sources for an organization."""
    user = await _authorized_org_user(request, org_id)
    org_sources = await list_connected_sources(org_id)
    org_sources = [
        source for source in org_sources if _source_visible_to_user(source, user)
    ]
    return {"sources": org_sources, "total": len(org_sources)}


@app.get("/sources/{source_id}/documents")
async def list_source_documents(
    request: Request,
    source_id: str,
    org_id: str = Query(...),
):
    """List document-level evidence stored by Komponist for one connector."""
    user = await _authorized_org_user(request, org_id)
    source = await get_connected_source(org_id, source_id)
    if not source or not _source_visible_to_user(source, user):
        raise HTTPException(status_code=404, detail="Source not found")

    rows = await GraphClient.run_query(
        f"""
        MATCH (ev:Evidence {{org_id: $org_id}})
        WHERE toLower(ev.source) IN $source_types
          AND {_evidence_scope('ev')}
        OPTIONAL MATCH (entity:Entity {{org_id: $org_id}})-[:CITED_BY]->(ev)
        WHERE entity IS NULL OR {_knowledge_scope('entity')}
        RETURN
            ev.reference AS reference,
            head(collect(DISTINCT ev.title)) AS title,
            head(collect(DISTINCT ev.url)) AS url,
            toString(max(ev.source_date)) AS synced_at,
            count(DISTINCT ev) AS evidence_count,
            count(DISTINCT entity) AS entity_count,
            collect(DISTINCT entity.status) AS entity_statuses,
            head(collect(DISTINCT ev.department_id)) AS department_id
        ORDER BY synced_at DESC, reference
        """,
        _scoped_params(
            org_id,
            user,
            source_types=_source_evidence_types(source["type"]),
        ),
    )

    documents = []
    for row in rows:
        reference = row.get("reference")
        if not reference:
            continue
        statuses = [status for status in row.get("entity_statuses", []) if status]
        if "proposed" in statuses and "confirmed" in statuses:
            review_status = "mixed"
        elif "proposed" in statuses:
            review_status = "proposed"
        elif statuses:
            review_status = "confirmed"
        else:
            review_status = "empty"
        documents.append({
            "id": hashlib.sha256(
                f"{source_id}\0{reference}".encode("utf-8")
            ).hexdigest()[:20],
            "title": row.get("title") or _document_title(reference),
            "reference": reference,
            "url": row.get("url"),
            "synced_at": row.get("synced_at"),
            "evidence_count": row.get("evidence_count", 0),
            "entity_count": row.get("entity_count", 0),
            "review_status": review_status,
            "department_id": row.get("department_id"),
        })

    return {"documents": documents, "total": len(documents)}


@app.patch("/sources/{source_id}/documents")
async def update_source_document_department(
    request: Request,
    source_id: str,
    payload: SourceDocumentDepartmentUpdate,
    org_id: str = Query(...),
):
    """Move one synced document and all knowledge derived from it."""
    user = await _authorized_org_user(request, org_id, manage=True)
    department_id = await _validate_department_scope(
        org_id, user, payload.department_id
    )
    source = await get_connected_source(org_id, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    result = await GraphClient.run_query(
        """
        MATCH (evidence:Evidence {org_id: $org_id, reference: $reference})
        WHERE toLower(evidence.source) IN $source_types
        SET evidence.department_id = $department_id
        RETURN count(evidence) AS updated
        """,
        {
            "org_id": org_id,
            "reference": payload.reference,
            "source_types": _source_evidence_types(source["type"]),
            "department_id": department_id,
        },
    )
    updated = result[0].get("updated", 0) if result else 0
    if not updated:
        raise HTTPException(status_code=404, detail="Synced document not found")
    await _recalculate_entity_department_scopes(org_id)
    return {
        "reference": payload.reference,
        "department_id": department_id,
        "evidence_updated": updated,
    }


@app.delete("/sources/{source_id}/documents")
async def remove_source_document(
    request: Request,
    source_id: str,
    org_id: str = Query(...),
    reference: str = Query(..., min_length=1, max_length=2048),
):
    """Delete one document's derived Komponist data, never the upstream file."""
    await _authorized_org_user(request, org_id, manage=True)
    source = await get_connected_source(org_id, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    matches = await GraphClient.run_query(
        """
        MATCH (ev:Evidence {org_id: $org_id, reference: $reference})
        WHERE toLower(ev.source) IN $source_types
        OPTIONAL MATCH (entity:Entity {org_id: $org_id})-[:CITED_BY]->(ev)
        RETURN
            collect(DISTINCT ev.id) AS evidence_ids,
            collect(DISTINCT entity.id) AS entity_ids
        """,
        {
            "org_id": org_id,
            "reference": reference,
            "source_types": _source_evidence_types(source["type"]),
        },
    )
    evidence_ids = matches[0].get("evidence_ids", []) if matches else []
    entity_ids = matches[0].get("entity_ids", []) if matches else []
    if not evidence_ids:
        raise HTTPException(status_code=404, detail="Synced document not found")

    await GraphClient.run_query(
        """
        MATCH (ev:Evidence {org_id: $org_id})
        WHERE ev.id IN $evidence_ids
        DETACH DELETE ev
        """,
        {"org_id": org_id, "evidence_ids": evidence_ids},
    )

    orphan_result = await GraphClient.run_query(
        """
        MATCH (entity:Entity {org_id: $org_id})
        WHERE entity.id IN $entity_ids
          AND NOT (entity)-[:CITED_BY]->(:Evidence)
        WITH collect(entity) AS orphans
        WITH orphans, size(orphans) AS deleted
        FOREACH (entity IN orphans | DETACH DELETE entity)
        RETURN deleted
        """,
        {"org_id": org_id, "entity_ids": entity_ids},
    )
    entities_deleted = orphan_result[0].get("deleted", 0) if orphan_result else 0
    await _recalculate_entity_department_scopes(org_id)

    await update_connected_source(
        org_id,
        source_id,
        item_count=max(0, source.get("itemCount", 0) - 1),
    )

    return {
        "status": "removed",
        "reference": reference,
        "evidence_deleted": len(evidence_ids),
        "entities_deleted": entities_deleted,
        "platform_unchanged": True,
    }


@app.post("/sources")
async def add_source(
    request: Request,
    org_id: str = Query(...),
    source_type: str = Query(..., description="Source type: notion, slack, google, local, upload"),
    name: str = Query(..., description="Display name for the source"),
    config: dict = None,
    department_id: Optional[str] = Query(default=None),
):
    """Register a connected source."""
    user = await _authorized_org_user(request, org_id, manage=True)
    department_id = await _validate_department_scope(org_id, user, department_id)
    if source_type not in {"notion", "slack", "google", "local", "upload"}:
        raise HTTPException(status_code=400, detail="Unsupported source type")
    return await create_connected_source(
        org_id=org_id,
        source_type=source_type,
        name=name,
        config=config or {},
        department_id=department_id,
    )


@app.patch("/sources/{source_id}")
async def update_source_department(
    source_id: str,
    payload: SourceDepartmentUpdate,
    request: Request,
    org_id: str = Query(...),
):
    """Set the default department for future connector items."""
    user = await _authorized_org_user(request, org_id, manage=True)
    department_id = await _validate_department_scope(
        org_id, user, payload.department_id
    )
    source = await set_connected_source_department(org_id, source_id, department_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return source


@app.delete("/sources/{source_id}")
async def remove_source(
    source_id: str,
    request: Request,
    org_id: str = Query(...),
    remove_data: bool = Query(False)
):
    """
    Remove a connected source.

    Args:
        source_id: ID of the source to remove
        org_id: Organization ID
        remove_data: If True, also delete all entities and evidence from this source
    """
    await _authorized_org_user(request, org_id, manage=True)
    # Get source info before removing
    source = await get_connected_source(org_id, source_id, include_config=True)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    entities_deleted = 0
    evidence_deleted = 0

    if remove_data and source:
        source_type = source.get("type", "").lower()
        evidence_types = _source_evidence_types(source_type)

        try:
            affected_query = """
            MATCH (entity:Entity {org_id: $org_id})-[:CITED_BY]->(ev:Evidence)
            WHERE toLower(ev.source) IN $evidence_types
            RETURN collect(DISTINCT entity.id) AS entity_ids
            """
            affected = await GraphClient.run_query(affected_query, {
                "org_id": org_id,
                "evidence_types": evidence_types
            })
            entity_ids = affected[0].get("entity_ids", []) if affected else []

            delete_evidence_query = """
            MATCH (ev:Evidence {org_id: $org_id})
            WHERE toLower(ev.source) IN $evidence_types
            DETACH DELETE ev
            RETURN count(ev) as deleted
            """
            result = await GraphClient.run_query(delete_evidence_query, {
                "org_id": org_id,
                "evidence_types": evidence_types
            })
            if result:
                evidence_deleted = result[0].get("deleted", 0)

            orphan_query = """
            MATCH (entity:Entity {org_id: $org_id})
            WHERE entity.id IN $entity_ids
              AND NOT (entity)-[:CITED_BY]->(:Evidence {org_id: $org_id})
            WITH collect(entity) AS orphans
            WITH orphans, size(orphans) AS deleted
            FOREACH (entity IN orphans | DETACH DELETE entity)
            RETURN deleted
            """
            orphaned = await GraphClient.run_query(orphan_query, {
                "org_id": org_id,
                "entity_ids": entity_ids,
            })
            entities_deleted = orphaned[0].get("deleted", 0) if orphaned else 0

            print(f"[Disconnect] Removed {entities_deleted} entities, {evidence_deleted} evidence from {source_type}")

        except Exception as error:
            print(f"[Disconnect] Error removing data: {type(error).__name__}")
            import traceback
            traceback.print_exc()
            raise HTTPException(
                status_code=500,
                detail="Could not safely remove the source data",
            ) from error

    await delete_connected_source(org_id, source_id)

    return {
        "status": "removed",
        "source_id": source_id,
        "data_removed": remove_data,
        "entities_deleted": entities_deleted,
        "evidence_deleted": evidence_deleted
    }


@app.post("/sources/{source_id}/sync")
async def sync_source(
    source_id: str, request: Request, org_id: str = Query(...)
):
    """
    Sync a connected source - fetch data and extract facts.
    """
    await _authorized_org_user(request, org_id, manage=True)
    from datetime import datetime

    # Find the source
    source = await get_connected_source(org_id, source_id, include_config=True)

    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    await update_connected_source(org_id, source_id, status="syncing")

    try:
        if source["type"] == "notion":
            result = await sync_notion_source(org_id, source)
        elif source["type"] == "local":
            result = await sync_local_source(org_id, source)
        else:
            raise ValueError(f"Sync not implemented for {source['type']}")

        await update_connected_source(
            org_id,
            source_id,
            status="connected",
            last_sync=datetime.utcnow(),
            item_count=result.get("items_processed", 0),
        )

        return result

    except Exception as e:
        await update_connected_source(org_id, source_id, status="error")
        raise HTTPException(status_code=400, detail=str(e))


async def sync_notion_source(org_id: str, source: dict) -> dict:
    """Sync Notion pages and extract facts with parallel processing."""
    import asyncio
    from integrations.notion import search_notion, get_page_content, normalize_page

    token = source.get("config", {}).get("token")
    if not token:
        raise ValueError("No token found for Notion source")

    print(f"[Notion Sync] Starting sync for org {org_id}")

    # Collect all pages first
    all_pages = []
    start_cursor = None

    while True:
        result = await search_notion(
            access_token=token,
            filter_type="page",
            start_cursor=start_cursor
        )

        pages = result.get("results", [])
        all_pages.extend(pages)

        if not result.get("has_more"):
            break
        start_cursor = result.get("next_cursor")

    print(f"[Notion Sync] Found {len(all_pages)} pages total, processing in parallel...")

    # Get org settings
    settings = await get_org_settings(org_id)
    auto_confirm = settings.get("auto_confirm", True)
    batch_size = settings.get("parallel_batch_size", 5)

    print(f"[Notion Sync] Auto-confirm: {auto_confirm}, Batch size: {batch_size}")

    # Process pages in parallel batches
    total_entities = 0
    total_relationships = 0
    pages_processed = 0

    async def process_page(page):
        """Process a single page."""
        try:
            page_id = page["id"]
            content = await get_page_content(token, page_id)

            if content and len(content.strip()) > 50:  # Skip near-empty pages
                source_item = normalize_page(page, content, org_id)
                source_item.department_id = source.get("departmentId")
                print(f"[Notion Sync] Processing: {source_item.title[:40]}...")

                result = await run_extraction(source_item, auto_confirm=auto_confirm)
                return {
                    "success": True,
                    "entities": result.get("entities_created", 0),
                    "relationships": result.get("relationships_created", 0)
                }
            return {"success": True, "entities": 0, "relationships": 0}
        except Exception as e:
            print(f"[Notion Sync] Error: {e}")
            return {"success": False, "entities": 0, "relationships": 0}

    # Process in batches
    for i in range(0, len(all_pages), batch_size):
        batch = all_pages[i:i + batch_size]
        print(f"[Notion Sync] Processing batch {i // batch_size + 1}/{(len(all_pages) + batch_size - 1) // batch_size}")

        # Run batch in parallel
        results = await asyncio.gather(*[process_page(page) for page in batch])

        for r in results:
            if r["success"]:
                pages_processed += 1
                total_entities += r["entities"]
                total_relationships += r["relationships"]

    print(f"[Notion Sync] Complete: {pages_processed} pages, {total_entities} entities, {total_relationships} relationships")

    return {
        "status": "complete",
        "items_processed": pages_processed,
        "entities_created": total_entities,
        "relationships_created": total_relationships
    }


async def sync_local_source(org_id: str, source: dict) -> dict:
    """Sync local documents."""
    from integrations.local_docs import backfill_local_docs

    path = source.get("config", {}).get("path", "./docs")
    result = await backfill_local_docs(
        org_id=org_id,
        docs_path=path,
        department_id=source.get("departmentId"),
    )
    if result.get("status") == "error":
        raise ValueError(result.get("error", "Local documents sync failed"))
    return result


async def run_extraction(source_item, auto_confirm: bool = False) -> dict:
    """Run the narrow MVP extraction pipeline on a source item."""
    from pipelines.extract import extract_from_source

    result = await extract_from_source(source_item)
    if not result.get("success"):
        raise RuntimeError(result.get("error") or "Extraction pipeline failed")

    entity_ids = result.get("entity_ids", [])
    if auto_confirm and entity_ids:
        await GraphClient.run_query(
            """
            MATCH (e:Entity {org_id: $org_id})
            WHERE e.id IN $entity_ids AND e.status = 'proposed'
            SET e.status = 'confirmed',
                e.confirmed_at = datetime(),
                e.updated_at = datetime()
            """,
            {"org_id": source_item.org_id, "entity_ids": entity_ids},
        )

    return {
        "entities_created": result.get("entities_created", 0),
        "relationships_created": result.get("relationships_created", 0),
        "entity_ids": entity_ids,
    }


UPLOAD_EXTENSIONS = {".md", ".markdown", ".txt", ".yaml", ".yml"}
MAX_UPLOAD_FILES = 10
MAX_UPLOAD_BYTES = 1024 * 1024


@app.post("/sources/upload")
async def upload_documents(
    request: Request,
    org_id: str = Query(...),
    department_id: Optional[str] = Query(default=None),
    files: List[UploadFile] = File(...),
):
    """Extract uploaded text documents without persisting their raw contents."""
    user = await _authorized_org_user(request, org_id, write=True)
    department_id = await _validate_department_scope(
        org_id, user, department_id, require_for_limited_member=True
    )
    if not files or len(files) > MAX_UPLOAD_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Upload between 1 and {MAX_UPLOAD_FILES} files at a time",
        )

    from core.models import SourceItem, SourceType
    from integrations.local_docs import extract_title_from_markdown

    settings = await get_org_settings(org_id)
    auto_confirm = settings.get("auto_confirm", False)
    results = []
    total_entities = 0

    for upload in files:
        filename = Path(upload.filename or "document.txt").name
        suffix = Path(filename).suffix.lower()
        if suffix not in UPLOAD_EXTENSIONS:
            results.append({
                "filename": filename,
                "status": "error",
                "error": "Supported formats: .md, .txt, .yaml, .yml",
            })
            continue

        content_bytes = await upload.read(MAX_UPLOAD_BYTES + 1)
        if len(content_bytes) > MAX_UPLOAD_BYTES:
            results.append({
                "filename": filename,
                "status": "error",
                "error": "File exceeds the 1 MB limit",
            })
            continue
        try:
            content = content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            results.append({
                "filename": filename,
                "status": "error",
                "error": "File must be UTF-8 encoded text",
            })
            continue
        if not content.strip():
            results.append({
                "filename": filename, "status": "error", "error": "File is empty"
            })
            continue

        digest = hashlib.sha256(content_bytes).hexdigest()
        source_item = SourceItem(
            org_id=org_id,
            department_id=department_id,
            source=SourceType.UPLOAD,
            kind={
                ".md": "markdown", ".markdown": "markdown",
                ".yaml": "yaml", ".yml": "yaml",
            }.get(suffix, "text"),
            title=extract_title_from_markdown(content, filename),
            body=content,
            url=f"upload://{filename}",
            reference=f"upload:{filename}:{digest[:12]}",
            source_date=datetime.utcnow(),
        )
        try:
            extraction = await run_extraction(source_item, auto_confirm=auto_confirm)
            created = extraction["entities_created"]
            total_entities += created
            results.append({
                "filename": filename,
                "status": "processed",
                "entities_created": created,
                "entity_ids": extraction["entity_ids"],
            })
        except Exception as error:
            results.append({
                "filename": filename,
                "status": "error",
                "error": str(error),
            })

    processed = sum(item["status"] == "processed" for item in results)
    if processed:
        source = await upsert_single_source_type(
            org_id=org_id,
            source_type="upload",
            name="Document Uploads",
            config={},
        )
        await update_connected_source(
            org_id,
            source["id"],
            last_sync=datetime.utcnow(),
            item_count=source.get("itemCount", 0) + processed,
        )

    return {
        "status": "complete" if processed == len(files) else "partial",
        "files_processed": processed,
        "entities_created": total_entities,
        "review_mode": not auto_confirm,
        "results": results,
    }


# =============================================================================
# Local Documents connector
# =============================================================================

@app.get("/connectors/local-docs/status")
async def local_docs_status(request: Request, org_id: str = Query(...)):
    """Get local documents connector status."""
    await _authorized_org_user(request, org_id)
    from integrations.local_docs import get_local_docs_status
    return get_local_docs_status()


@app.post("/connectors/local-docs/scan")
async def local_docs_scan(
    request: Request,
    org_id: str = Query(...),
    path: Optional[str] = Query(None, description="Override docs path")
):
    """Trigger a scan of local documents."""
    await _authorized_org_user(request, org_id, manage=True)
    from integrations.local_docs import backfill_local_docs
    result = await backfill_local_docs(org_id=org_id, docs_path=path)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


# =============================================================================
# Graph API endpoints
# =============================================================================

@app.get("/graph")
async def get_graph(
    request: Request,
    org_id: str = Query(...),
    limit: int = Query(200, ge=1, le=500, description="Max nodes to return"),
    entity_types: Optional[str] = Query(None, description="Comma-separated entity types to filter")
):
    """
    Get the knowledge graph for visualization.

    Returns nodes (entities) and edges (relationships).
    """
    user = await _authorized_org_user(request, org_id)
    types = [value.strip() for value in entity_types.split(",")] if entity_types else []
    invalid_types = sorted(set(types) - set(_CHAT_ENTITY_TYPES))
    if invalid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported entity types: {', '.join(invalid_types)}",
        )

    # Get nodes
    nodes_query = f"""
    MATCH (e:Entity {{org_id: $org_id}})
    WHERE e.status IN ['proposed', 'confirmed']
      AND (size($entity_types) = 0 OR e.entity_type IN $entity_types)
      AND {_knowledge_scope('e')}
    RETURN
        e.id as id,
        coalesce(e.name, e.statement) as name,
        e.entity_type as type,
        e.detail as description,
        e.status as status,
        e.confidence as confidence
    ORDER BY e.created_at DESC
    LIMIT $limit
    """

    nodes = await GraphClient.run_query(
        nodes_query,
        _scoped_params(org_id, user, limit=limit, entity_types=types),
    )

    # Get all node IDs for edge filtering
    node_ids = [n["id"] for n in nodes]

    if not node_ids:
        return {"nodes": [], "edges": []}

    # Get edges between these nodes
    edges_query = """
    MATCH (s:Entity {org_id: $org_id})-[r]->(t:Entity {org_id: $org_id})
    WHERE s.id IN $node_ids AND t.id IN $node_ids
    AND NOT type(r) = 'CITED_BY'
    RETURN
        s.id as source,
        t.id as target,
        type(r) as type,
        r.description as description
    """

    edges = await GraphClient.run_query(edges_query, {
        "org_id": org_id,
        "node_ids": node_ids
    })

    return {
        "nodes": nodes,
        "edges": edges
    }


@app.get("/graph/stats")
async def get_graph_stats(request: Request, org_id: str = Query(...)):
    """Get statistics about the knowledge graph."""
    user = await _authorized_org_user(request, org_id)

    # Count nodes by type
    type_query = f"""
    MATCH (e:Entity {{org_id: $org_id}})
    WHERE e.status IN ['proposed', 'confirmed'] AND {_knowledge_scope('e')}
    RETURN e.entity_type as type, count(e) as count
    ORDER BY count DESC
    """

    params = _scoped_params(org_id, user)
    type_counts = await GraphClient.run_query(type_query, params)

    # Count relationships by type
    rel_query = f"""
    OPTIONAL MATCH (s:Entity {{org_id: $org_id}})-[r]->(t:Entity {{org_id: $org_id}})
    WHERE NOT type(r) = 'CITED_BY'
      AND {_knowledge_scope('s')} AND {_knowledge_scope('t')}
    RETURN type(r) as type, count(r) as count
    ORDER BY count DESC
    """

    rel_counts = await GraphClient.run_query(rel_query, params)

    # Total counts
    totals_query = f"""
    MATCH (e:Entity {{org_id: $org_id}})
    WHERE e.status IN ['proposed', 'confirmed'] AND {_knowledge_scope('e')}
    WITH count(e) as node_count
    OPTIONAL MATCH (s:Entity {{org_id: $org_id}})-[r]->(t:Entity {{org_id: $org_id}})
    WHERE NOT type(r) = 'CITED_BY'
      AND {_knowledge_scope('s')} AND {_knowledge_scope('t')}
    RETURN node_count, count(r) as edge_count
    """

    totals = await GraphClient.run_query(totals_query, params)

    node_count = totals[0]["node_count"] if totals else 0
    edge_count = totals[0]["edge_count"] if totals else 0

    return {
        "total_nodes": node_count,
        "total_edges": edge_count,
        "nodes_by_type": {t["type"]: t["count"] for t in type_counts},
        "edges_by_type": {
            row["type"]: row["count"] for row in rel_counts if row.get("type")
        },
    }


@app.get("/graph/neighbors/{entity_id}")
async def get_entity_neighbors(
    entity_id: str,
    request: Request,
    org_id: str = Query(...),
    depth: int = Query(1, ge=1, le=2, description="How many hops to traverse"),
):
    """Get the neighborhood of a specific entity."""
    user = await _authorized_org_user(request, org_id)

    # Get the entity and its neighbors up to N hops
    query = f"""
    MATCH path = (center:Entity {{id: $entity_id, org_id: $org_id}})-[*1..{depth}]-(neighbor:Entity)
    WHERE neighbor.org_id = $org_id
      AND center.status IN ['proposed', 'confirmed']
      AND neighbor.status IN ['proposed', 'confirmed']
      AND {_knowledge_scope('center')}
      AND {_knowledge_scope('neighbor')}
    WITH center, neighbor, relationships(path) as rels
    UNWIND rels as r
    WITH center, neighbor, r, startNode(r) as source, endNode(r) as target
    WHERE NOT type(r) = 'CITED_BY'
    RETURN DISTINCT
        neighbor.id as id,
        neighbor.name as name,
        neighbor.entity_type as type,
        neighbor.detail as description,
        source.id as edge_source,
        target.id as edge_target,
        type(r) as edge_type
    """

    params = _scoped_params(org_id, user, entity_id=entity_id)
    results = await GraphClient.run_query(query, params)

    # Build nodes and edges
    nodes = {}
    edges = []

    # Add center node
    center_query = f"""
    MATCH (e:Entity {{id: $entity_id, org_id: $org_id}})
    WHERE {_knowledge_scope('e')}
    RETURN e.id as id, coalesce(e.name, e.statement) as name,
           e.entity_type as type, e.detail as description
    """
    center = await GraphClient.run_query(center_query, params)

    if center:
        nodes[entity_id] = {
            "id": center[0]["id"],
            "name": center[0]["name"],
            "type": center[0]["type"],
            "description": center[0]["description"],
            "isCenter": True
        }

    for row in results:
        # Add neighbor node
        if row["id"] not in nodes:
            nodes[row["id"]] = {
                "id": row["id"],
                "name": row["name"],
                "type": row["type"],
                "description": row["description"],
                "isCenter": False
            }

        # Add edge
        edge = {
            "source": row["edge_source"],
            "target": row["edge_target"],
            "type": row["edge_type"]
        }
        if edge not in edges:
            edges.append(edge)

    return {
        "center": entity_id,
        "nodes": list(nodes.values()),
        "edges": edges
    }


# =============================================================================
# Chat API endpoint
# =============================================================================

from sse_starlette.sse import EventSourceResponse
from core.llm import get_llm
from core.embeddings import embed
from core.queries import BrainQueries


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str
    sources: Optional[List[Dict[str, Any]]] = None


class ChatRequest(BaseModel):
    message: str
    org_id: str = "default-org"
    conversation_id: Optional[str] = None
    conversation_history: List[ChatMessage] = Field(default_factory=list)
    stream: bool = True


class ChatResponse(BaseModel):
    response: str
    sources: List[Dict[str, Any]]
    conversation_id: Optional[str] = None


class ChatConversationUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=120)


_CHAT_STOP_WORDS = {
    "about", "all", "and", "are", "been", "der", "die", "das", "do",
    "does", "for", "from", "geht", "haben", "has", "ist", "it", "me", "our",
    "show", "the", "und", "use", "was", "what", "welche", "which",
    "who", "wie", "wir", "with",
}

_CHAT_ENTITY_TYPES = ["Decision", "Goal", "Constraint", "Project"]

_CHAT_QUERY_PLAN_SCHEMA = {
    "title": "Komponist chat retrieval plan",
    "type": "object",
    "properties": {
        "operation": {
            "type": "string",
            "enum": ["search", "list", "count", "overview"],
            "description": (
                "search for a factual question, list for an exhaustive set, "
                "count for aggregate quantities, overview for a broad summary"
            ),
        },
        "query": {
            "type": "string",
            "description": (
                "A standalone semantic search query with pronouns resolved from "
                "conversation history. Empty for count or unfiltered list operations."
            ),
        },
        "entity_types": {
            "type": "array",
            "items": {"type": "string", "enum": _CHAT_ENTITY_TYPES},
            "description": "Relevant graph entity types; empty means all types.",
        },
        "group_by": {
            "type": "string",
            "enum": ["none", "entity_type", "source"],
            "description": "Grouping for count operations; otherwise none.",
        },
        "sort": {
            "type": "string",
            "enum": ["relevance", "newest", "oldest"],
        },
        "limit": {
            "type": "integer",
            "description": "Requested result limit between 1 and 100.",
        },
        "language": {
            "type": "string",
            "enum": ["english", "german"],
            "description": "English unless the user explicitly requests German.",
        },
        "expand_graph": {
            "type": "boolean",
            "description": (
                "True only when relationships or connected implications are needed."
            ),
        },
    },
    "required": [
        "operation", "query", "entity_types", "group_by", "sort", "limit",
        "language", "expand_graph",
    ],
    "additionalProperties": False,
}

_GROUNDED_CHAT_ANSWER_SCHEMA = {
    "title": "Komponist grounded chat answer",
    "type": "object",
    "properties": {
        "blocks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["paragraph", "heading", "bullet"],
                    },
                    "text": {
                        "type": "string",
                        "description": "Plain text without Markdown or citation markers.",
                    },
                    "citations": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "One-based source numbers supporting this block.",
                    },
                },
                "required": ["kind", "text", "citations"],
                "additionalProperties": False,
            },
        },
        "insufficient_context": {
            "type": "boolean",
            "description": "True when the confirmed context cannot answer the question.",
        },
    },
    "required": ["blocks", "insufficient_context"],
    "additionalProperties": False,
}

_DURATION_PATTERN = re.compile(
    r"\b(?P<value>\d+|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"eins|eine|einen|zwei|drei|vier|fünf|sechs|sieben|acht|neun|zehn)"
    r"(?:-|\s)(?P<unit>day|days|week|weeks|month|months|year|years|"
    r"tag|tage|tagen|woche|wochen|monat|monate|monaten|jahr|jahre|jahren)\b",
    flags=re.IGNORECASE,
)

_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eins": 1, "eine": 1, "einen": 1, "zwei": 2, "drei": 3,
    "vier": 4, "fünf": 5, "sechs": 6, "sieben": 7, "acht": 8,
    "neun": 9, "zehn": 10,
}


def _chat_search_terms(message: str) -> List[str]:
    """Extract useful literal fallback terms from a natural-language question."""
    import re

    words = re.findall(r"[\w-]+", message.casefold(), flags=re.UNICODE)
    return list(dict.fromkeys(
        word for word in words if len(word) >= 3 and word not in _CHAT_STOP_WORDS
    ))[:12]


def _chat_history_text(history: List[ChatMessage]) -> str:
    if not history:
        return "No previous conversation."
    return "\n".join(
        f"{message.role}: {message.content}"
        for message in history[-6:]
    )


async def _plan_chat_query(
    llm: Any,
    message: str,
    history: List[ChatMessage],
) -> dict:
    """Turn arbitrary phrasing into a validated, allowlisted graph query plan."""
    plan = await llm.call_json(
        prompt=(
            f"Conversation:\n{_chat_history_text(history)}\n\n"
            f"Current user question:\n{message}"
        ),
        system="""You plan read-only retrieval from a company knowledge graph.

The confirmed graph has exactly four semantic entity types:
- Decision: a chosen direction, policy, or architecture choice
- Goal: an objective, target, desired outcome, or success criterion
- Constraint: a restriction, requirement, rule, or boundary
- Project: an initiative, pilot, program, or workstream

Resolve synonyms and references such as "it", "that project", or "those goals"
using the conversation. Choose count for totals or grouped quantities, list when
the user asks for every matching item, overview for broad company-brain summaries,
and search for focused factual questions. For requests covering several types,
include every relevant type. Use group_by entity_type for per-type counts and
source for counts by document/source. Never create Cypher or invent entity types.
For exhaustive words such as all, every, complete, or entire, set limit to 100.
Otherwise respect an explicitly requested number and use a focused default limit.
Set expand_graph only for relationship, dependency, impact, or connected-context questions.
English is the default response language; choose German only when explicitly asked.
Return only the structured plan.""",
        max_tokens=500,
        schema=_CHAT_QUERY_PLAN_SCHEMA,
    )
    plan["entity_types"] = list(dict.fromkeys(plan.get("entity_types") or []))
    plan["limit"] = max(1, min(int(plan.get("limit") or 12), 100))
    # Language is a product preference, not a retrieval inference: English stays
    # the default even when the question itself is written in German.
    plan["language"] = "german" if _answer_in_german(message) else "english"
    if plan["operation"] == "search" and not plan.get("query", "").strip():
        plan["query"] = message
    if plan["operation"] != "count":
        plan["group_by"] = "none"
    return plan


def _fallback_chat_plan(message: str, broad: bool = False) -> dict:
    """Safe retrieval fallback when the planner is unavailable."""
    return {
        "operation": "overview" if broad else "search",
        "query": message,
        "entity_types": [],
        "group_by": "none",
        "sort": "relevance",
        "limit": 100 if broad else 12,
        "language": "german" if _answer_in_german(message) else "english",
        "expand_graph": False,
    }


async def _browse_chat_entities(
    org_id: str,
    user: dict,
    entity_types: List[str],
    limit: int,
    sort: str = "newest",
) -> List[dict]:
    """Browse confirmed entities using only validated filters and sort modes."""
    order_by = {
        "oldest": "n.confirmed_at ASC, n.created_at ASC, n.id",
        "newest": "n.confirmed_at DESC, n.created_at DESC, n.id",
        "relevance": "n.confirmed_at DESC, n.created_at DESC, n.id",
    }[sort]
    return await GraphClient.run_query(
        f"""
        MATCH (n:Entity {{org_id: $org_id, status: 'confirmed'}})
        WHERE (size($entity_types) = 0 OR n.entity_type IN $entity_types)
          AND {_knowledge_scope('n')}
        RETURN n.id AS id, n.entity_type AS entity_type,
               n.statement AS statement, n.detail AS detail,
               n.status AS status, n.confidence AS confidence,
               1.0 AS score
        ORDER BY {order_by}
        LIMIT $limit
        """,
        _scoped_params(org_id, user, entity_types=entity_types, limit=limit),
    )


async def _count_chat_entities(
    org_id: str,
    user: dict,
    entity_types: List[str],
    group_by: str,
) -> List[dict]:
    """Run exact aggregate counts without letting the model generate database code."""
    if group_by == "source":
        return await GraphClient.run_query(
            f"""
            MATCH (n:Entity {{org_id: $org_id, status: 'confirmed'}})
            WHERE (size($entity_types) = 0 OR n.entity_type IN $entity_types)
              AND {_knowledge_scope('n')}
            MATCH (n)-[:CITED_BY]->(e:Evidence {{org_id: $org_id}})
            WHERE {_evidence_scope('e')}
            WITH coalesce(e.reference, e.source, 'Unknown source') AS group,
                 count(DISTINCT n) AS count
            RETURN group, count
            ORDER BY count DESC, group
            """,
            _scoped_params(org_id, user, entity_types=entity_types),
        )

    return await GraphClient.run_query(
        f"""
        MATCH (n:Entity {{org_id: $org_id, status: 'confirmed'}})
        WHERE (size($entity_types) = 0 OR n.entity_type IN $entity_types)
          AND {_knowledge_scope('n')}
        RETURN n.entity_type AS group, count(n) AS count
        ORDER BY group
        """,
        _scoped_params(org_id, user, entity_types=entity_types),
    )


async def _literal_chat_search(
    org_id: str,
    user: dict,
    message: str,
    k: int = 8,
    entity_types: Optional[List[str]] = None,
) -> List[dict]:
    """Search confirmed entities without relying on vector/full-text indexes."""
    terms = _chat_search_terms(message)
    if not terms:
        return []

    return await GraphClient.run_query(
        f"""
        MATCH (n:Entity {{org_id: $org_id, status: 'confirmed'}})
        WHERE (size($entity_types) = 0 OR n.entity_type IN $entity_types)
          AND {_knowledge_scope('n')}
        OPTIONAL MATCH (n)-[:CITED_BY]->(evidence:Evidence {{org_id: $org_id}})
        WHERE {_evidence_scope('evidence')}
        WITH n, collect(DISTINCT evidence) AS evidence_items
        WITH n, evidence_items, [term IN $terms WHERE
            toLower(coalesce(n.statement, '')) CONTAINS term OR
            toLower(coalesce(n.detail, '')) CONTAINS term OR
            toLower(coalesce(n.name, '')) CONTAINS term OR
            toLower(coalesce(n.entity_type, '')) CONTAINS term OR
            any(item IN evidence_items WHERE
                toLower(coalesce(item.reference, '')) CONTAINS term OR
                toLower(coalesce(item.excerpt, '')) CONTAINS term)
        ] AS matched_terms
        WHERE size(matched_terms) > 0
        WITH n, size(matched_terms) AS matches
        RETURN n.id AS id, n.entity_type AS entity_type,
               n.statement AS statement, n.detail AS detail,
               n.status AS status, n.confidence AS confidence,
               toFloat(matches) AS score
        ORDER BY matches DESC, n.confirmed_at DESC
        LIMIT $k
        """,
        _scoped_params(
            org_id,
            user,
            terms=terms,
            k=k,
            entity_types=entity_types or [],
        ),
    )


async def _expand_chat_graph_context(
    org_id: str,
    user: dict,
    seed_results: List[dict],
    limit: int = 20,
) -> List[dict]:
    """Add confirmed one-hop neighbors so relationship questions have graph context."""
    if not seed_results:
        return []
    return await GraphClient.run_query(
        f"""
        MATCH (seed:Entity {{org_id: $org_id, status: 'confirmed'}})
        WHERE seed.id IN $seed_ids AND {_knowledge_scope('seed')}
        MATCH (seed)-[relationship]-(neighbor:Entity {{
            org_id: $org_id, status: 'confirmed'
        }})
        WHERE NOT neighbor.id IN $seed_ids AND {_knowledge_scope('neighbor')}
        RETURN DISTINCT neighbor.id AS id,
               neighbor.entity_type AS entity_type,
               neighbor.statement AS statement,
               neighbor.detail AS detail,
               neighbor.status AS status,
               neighbor.confidence AS confidence,
               type(relationship) AS relationship_type,
               seed.id AS related_seed_id,
               0.0 AS score
        ORDER BY neighbor.confirmed_at DESC, neighbor.created_at DESC
        LIMIT $limit
        """,
        _scoped_params(
            org_id,
            user,
            seed_ids=[result["id"] for result in seed_results],
            limit=limit,
        ),
    )


def _answer_in_german(message: str) -> bool:
    """English is default; switch only when the user explicitly requests German."""
    return bool(re.search(
        r"\b(auf\s+deutsch|in\s+german|answer\s+in\s+german|"
        r"antworte(?:\s+bitte)?\s+(?:auf\s+)?deutsch)\b",
        message.casefold(),
    ))


def _extract_duration(text: str) -> Optional[tuple[int, str]]:
    match = _DURATION_PATTERN.search(text or "")
    if not match:
        return None
    raw_value = match.group("value").casefold()
    value = int(raw_value) if raw_value.isdigit() else _NUMBER_WORDS.get(raw_value)
    if value is None:
        return None
    unit = match.group("unit").casefold()
    if unit.startswith(("day", "tag")):
        normalized_unit = "day"
    elif unit.startswith(("week", "woch")):
        normalized_unit = "week"
    elif unit.startswith(("month", "monat")):
        normalized_unit = "month"
    else:
        normalized_unit = "year"
    return value, normalized_unit


def _format_duration(value: int, unit: str, german: bool) -> str:
    units = {
        False: {"day": ("day", "days"), "week": ("week", "weeks"),
                "month": ("month", "months"), "year": ("year", "years")},
        True: {"day": ("Tag", "Tage"), "week": ("Woche", "Wochen"),
               "month": ("Monat", "Monate"), "year": ("Jahr", "Jahre")},
    }
    singular, plural = units[german][unit]
    return f"{value} {singular if value == 1 else plural}"


def _duration_subject(statement: str, german: bool) -> str:
    if "northstar" in statement.casefold() and "pilot" in statement.casefold():
        return "Northstar-Labs-Pilot" if german else "Northstar Labs pilot"
    return "Projekt" if german else "project"


async def _attach_chat_evidence(
    org_id: str, user: dict, entities: List[dict]
) -> None:
    """Attach provenance owned by the same organization to selected entities."""
    if not entities:
        return

    rows = await GraphClient.run_query(
        f"""
        MATCH (entity:Entity {{org_id: $org_id, status: 'confirmed'}})
        WHERE entity.id IN $entity_ids AND {_knowledge_scope('entity')}
        OPTIONAL MATCH (entity)-[:CITED_BY]->(evidence:Evidence {{org_id: $org_id}})
        WHERE {_evidence_scope('evidence')}
        RETURN entity.id AS entity_id,
               collect(DISTINCT evidence{{.id, .source, .reference, .url,
                                          .excerpt, .source_date}}) AS evidence
        """,
        _scoped_params(
            org_id, user, entity_ids=[entity["id"] for entity in entities]
        ),
    )
    evidence_by_entity = {
        row["entity_id"]: [item for item in row["evidence"] if item.get("id")]
        for row in rows
    }
    for entity in entities:
        entity["evidence"] = evidence_by_entity.get(entity["id"], [])


def _chat_context_and_sources(search_results: List[dict]) -> tuple[str, List[dict]]:
    """Build grounded model context and flattened UI citations."""
    if not search_results:
        return "No relevant confirmed information was found in the knowledge graph.", []

    sources: List[dict] = []
    context_parts = []
    for result in search_results:
        citation_numbers = []
        evidence_lines = []
        for evidence in result.get("evidence", []):
            source_date = evidence.get("source_date")
            source_date = str(source_date) if source_date is not None else None
            sources.append({
                "id": evidence["id"],
                "entity_id": result["id"],
                "type": result["entity_type"],
                "statement": result["statement"],
                "source": evidence.get("source") or "unknown",
                "reference": evidence.get("reference") or "Unknown reference",
                "url": evidence.get("url"),
                "excerpt": evidence.get("excerpt"),
                "source_date": source_date,
            })
            citation_numbers.append(str(len(sources)))
            evidence_lines.append(
                f"Source [{len(sources)}]: {sources[-1]['source']} — "
                f"{sources[-1]['reference']}"
            )

        citations = " ".join(f"[{number}]" for number in citation_numbers)
        relationship = ""
        if result.get("relationship_type"):
            relationship = (
                f"\nGraph relation: {result['relationship_type']} with retrieved entity "
                f"{result.get('related_seed_id')}."
            )
        context_parts.append(
            f"[{result['entity_type']}] {result['statement']} {citations}\n"
            f"Detail: {result.get('detail') or 'N/A'}{relationship}\n"
            + "\n".join(evidence_lines)
        )
    return "\n\n".join(context_parts), sources


def _mock_chat_answer(message: str, search_results: List[dict], sources: List[dict]) -> str:
    """Return a useful grounded answer while no external model is configured."""
    if not search_results:
        return (
            "I couldn't find relevant confirmed information in the company brain yet. "
            "Add or confirm a source first, then ask again."
        )

    citation_by_entity: Dict[str, List[int]] = {}
    for index, source in enumerate(sources, 1):
        citation_by_entity.setdefault(source["entity_id"], []).append(index)

    primary = search_results[0]
    primary_citations = " ".join(
        f"[{index}]" for index in citation_by_entity.get(primary["id"], [])
    )
    primary_text = " ".join(filter(None, [
        primary.get("statement"), primary.get("detail"),
    ]))
    duration = _extract_duration(primary_text)
    german = _answer_in_german(message)
    asks_duration = bool(re.search(
        r"\b(wie\s+lange|dauer|dauert|how\s+long|duration)\b",
        message.casefold(),
    ))

    if asks_duration and duration:
        value, unit = duration
        formatted = _format_duration(value, unit, german)
        subject = _duration_subject(primary.get("statement") or "", german)
        if german:
            answer = f"Der {subject} dauert {formatted}."
        else:
            answer = f"The {subject} lasts {formatted}."
        return answer + (f" {primary_citations}" if primary_citations else "")

    answer = (primary.get("statement") or primary.get("detail") or "").strip()
    if primary_citations:
        answer = f"{answer} {primary_citations}"

    related_lines = []
    for result in search_results[1:4]:
        statement = (result.get("statement") or "").strip()
        if not statement:
            continue
        citations = " ".join(
            f"[{index}]" for index in citation_by_entity.get(result["id"], [])
        )
        related_lines.append(f"- {statement}" + (f" {citations}" if citations else ""))

    if related_lines:
        heading = "Relevanter Kontext:" if german else "Relevant context:"
        answer += f"\n\n{heading}\n" + "\n".join(related_lines)
    return answer


def _aggregate_count_answer(
    plan: dict,
    count_rows: List[dict],
    sources: List[dict],
) -> str:
    """Render exact database aggregates independently of model wording."""
    german = plan.get("language") == "german"
    citation_limit = min(len(sources), 20)
    citations = " ".join(f"[{index}]" for index in range(1, citation_limit + 1))

    if plan.get("group_by") == "source":
        source_types = plan.get("entity_types") or []
        if len(source_types) == 1:
            source_type = source_types[0]
            source_labels = {
                "Decision": ("Entscheidungen", "decisions"),
                "Goal": ("Ziele", "goals"),
                "Constraint": ("Vorgaben", "constraints"),
                "Project": ("Projekte", "projects"),
            }
            german_subject, english_subject = source_labels[source_type]
        else:
            german_subject, english_subject = "Einträge", "items"
        if not count_rows:
            answer = (
                f"Es gibt keine bestätigten {german_subject} mit Quellen."
                if german else f"There are no confirmed {english_subject} with sources."
            )
        else:
            items = [
                f"{_human_source_label(str(row['group']))}: {row['count']}"
                for row in count_rows
            ]
            heading = (
                f"Bestätigte {german_subject} nach Quelle"
                if german else f"Confirmed {english_subject} by source"
            )
            answer = f"{heading}: " + "; ".join(items) + "."
        return answer + (f" {citations}" if citations else "")

    counts = {str(row["group"]): int(row["count"]) for row in count_rows}
    requested_types = plan.get("entity_types") or _CHAT_ENTITY_TYPES
    selected = [(entity_type, counts.get(entity_type, 0)) for entity_type in requested_types]

    english_labels = {
        "Decision": ("decision", "decisions"),
        "Goal": ("goal", "goals"),
        "Constraint": ("constraint", "constraints"),
        "Project": ("project", "projects"),
    }
    german_labels = {
        "Decision": ("Entscheidung", "Entscheidungen"),
        "Goal": ("Ziel", "Ziele"),
        "Constraint": ("Vorgabe", "Vorgaben"),
        "Project": ("Projekt", "Projekte"),
    }

    if len(selected) == 1:
        entity_type, count = selected[0]
        singular, plural = (german_labels if german else english_labels)[entity_type]
        label = singular if count == 1 else plural
        answer = (
            f"Im Company Brain gibt es {count} bestätigte {label}."
            if german else
            f"There {'is' if count == 1 else 'are'} {count} confirmed {label} in the company brain."
        )
    else:
        labels = german_labels if german else english_labels
        parts = [
            f"{count} {labels[entity_type][0] if count == 1 else labels[entity_type][1]}"
            for entity_type, count in selected
        ]
        total = sum(count for _, count in selected)
        answer = (
            f"Im Company Brain gibt es insgesamt {total} bestätigte Einträge: "
            if german else
            f"There are {total} confirmed items in the company brain: "
        ) + ", ".join(parts) + "."

    return answer + (f" {citations}" if citations else "")


async def _generate_grounded_chat_answer(
    llm: Any,
    user_prompt: str,
    system_prompt: str,
    sources: List[dict],
) -> str:
    """Generate citation blocks and validate every source number server-side."""
    payload = await llm.call_json(
        prompt=user_prompt,
        system=(
            system_prompt
            + "\n\nReturn a structured answer made of plain-text blocks. Every factual "
            "paragraph or bullet must name at least one supporting source number. "
            "Headings have no citations. Do not put [1]-style markers in block text."
        ),
        max_tokens=2048,
        schema=_GROUNDED_CHAT_ANSWER_SCHEMA,
    )

    rendered: List[str] = []
    for block in payload.get("blocks", []):
        text = str(block.get("text") or "").strip()
        if not text:
            continue
        kind = block.get("kind")
        citations = list(dict.fromkeys(
            int(index) for index in block.get("citations", [])
            if isinstance(index, int) and 1 <= index <= len(sources)
        ))

        # Do not show factual prose whose claimed evidence does not exist.
        if sources and kind != "heading" and not citations:
            continue

        markers = " ".join(f"[{index}]" for index in citations)
        if kind == "heading":
            line = f"{text}:"
        elif kind == "bullet":
            line = f"- {text}" + (f" {markers}" if markers else "")
        else:
            line = text + (f" {markers}" if markers else "")
        rendered.append(line)

    if rendered:
        return "\n".join(rendered)

    return (
        "I couldn't find enough confirmed, cited information in the company brain "
        "to answer that yet."
    )


def _human_source_label(reference: str) -> str:
    value = reference or "Company source"
    if value.startswith("upload:"):
        parts = value.split(":")
        value = parts[1] if len(parts) > 1 else value
    elif value.startswith("local:"):
        value = value.removeprefix("local:")
    elif value.startswith("notion:"):
        return "Notion workspace"
    elif value.startswith("gdrive:"):
        return "Google Drive"

    stem = Path(value).stem
    stem = re.sub(r"^\d+[\s_-]*", "", stem)
    stem = re.sub(r"[_-]+", " ", stem).strip()
    return stem.title() or "Company source"


def _duration_question_subject(statement: str) -> str:
    if "northstar" in statement.casefold() and "pilot" in statement.casefold():
        return "the Northstar Labs pilot"
    cleaned = _DURATION_PATTERN.sub("", statement, count=1)
    cleaned = re.sub(r"^(run|launch|conduct|start|ship)\s+(a|an|the)?\s*", "", cleaned, flags=re.I)
    cleaned = re.split(r"\s+(?:with|including|that|which)\s+", cleaned, maxsplit=1)[0]
    cleaned = cleaned.strip(" .,-")
    return cleaned[:72] if cleaned else "this project"


def _chat_suggestion_from_entity(row: dict) -> dict:
    statement = (row.get("statement") or row.get("detail") or "").strip()
    entity_type = row.get("entity_type") or "Fact"
    reference = row.get("reference") or "Company source"
    source_label = _human_source_label(reference)
    duration = _extract_duration(statement)

    if duration:
        subject = _duration_question_subject(statement)
        title = "Pilot duration" if "pilot" in subject.casefold() else "Project duration"
        prompt = f"How long does {subject} run?"
    elif entity_type == "Decision":
        title = "Confirmed decision"
        prompt = f"What decision is documented in {source_label}?"
    elif entity_type == "Goal":
        title = "Primary goal"
        prompt = f"What goal is documented in {source_label}?"
    elif entity_type == "Constraint":
        title = "Key constraint"
        prompt = f"Which constraint is documented in {source_label}?"
    elif entity_type == "Project":
        title = "Project scope"
        prompt = f"What project is described in {source_label}, and what is its scope?"
    else:
        title = f"{entity_type} context"
        prompt = f"What confirmed information comes from {source_label}?"

    return {
        "id": row["id"],
        "category": source_label,
        "title": title,
        "prompt": prompt,
        "entity_type": entity_type,
        "reference": reference,
    }


def _chat_title(message: str) -> str:
    """Derive a readable deterministic title without another model call."""
    title = " ".join(message.split()).strip()
    if len(title) <= 72:
        return title
    return f"{title[:69].rstrip()}…"


@app.get("/chat/conversations")
async def get_chat_conversations(
    request: Request, org_id: str = Query(...)
):
    user = await _authorized_org_user(request, org_id)
    return {"conversations": await list_chat_conversations(org_id, user["id"])}


@app.get("/chat/conversations/{conversation_id}")
async def get_chat_conversation_history(
    conversation_id: str, request: Request, org_id: str = Query(...)
):
    user = await _authorized_org_user(request, org_id)
    conversation = await get_chat_conversation(org_id, user["id"], conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@app.patch("/chat/conversations/{conversation_id}")
async def update_chat_conversation(
    conversation_id: str,
    payload: ChatConversationUpdate,
    request: Request,
    org_id: str = Query(...),
):
    user = await _authorized_org_user(request, org_id)
    title = " ".join(payload.title.split()).strip()
    if not title:
        raise HTTPException(status_code=422, detail="Conversation title is required")
    conversation = await rename_chat_conversation(
        org_id, user["id"], conversation_id, title
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@app.delete("/chat/conversations/{conversation_id}", status_code=204)
async def remove_chat_conversation(
    conversation_id: str, request: Request, org_id: str = Query(...)
):
    user = await _authorized_org_user(request, org_id)
    if not await delete_chat_conversation(org_id, user["id"], conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return Response(status_code=204)


@app.get("/chat/suggestions")
async def get_chat_suggestions(
    request: Request,
    org_id: str = Query("default-org"),
    limit: int = Query(4, ge=1, le=8),
):
    """Build starter questions from confirmed, cited organization knowledge."""
    user = await _authorized_org_user(request, org_id)
    rows = await GraphClient.run_query(
        f"""
        MATCH (entity:Entity {{org_id: $org_id, status: 'confirmed'}})
        WHERE {_knowledge_scope('entity')}
        MATCH (entity)-[:CITED_BY]->(evidence:Evidence {{org_id: $org_id}})
        WHERE {_evidence_scope('evidence')}
        WITH entity, head(collect(DISTINCT evidence)) AS evidence
        RETURN entity.id AS id, entity.entity_type AS entity_type,
               entity.statement AS statement, entity.detail AS detail,
               evidence.source AS source, evidence.reference AS reference,
               evidence.source_date AS source_date
        ORDER BY evidence.source_date DESC, entity.confirmed_at DESC, entity.created_at DESC
        LIMIT 48
        """,
        _scoped_params(org_id, user),
    )

    rows.sort(key=lambda row: 0 if _extract_duration(
        " ".join(filter(None, [row.get("statement"), row.get("detail")]))
    ) else 1)

    suggestions = []
    seen_prompts = set()
    seen_references = set()
    deferred = []
    for row in rows:
        suggestion = _chat_suggestion_from_entity(row)
        if suggestion["prompt"] in seen_prompts:
            continue
        if suggestion["reference"] in seen_references:
            deferred.append(suggestion)
            continue
        suggestions.append(suggestion)
        seen_prompts.add(suggestion["prompt"])
        seen_references.add(suggestion["reference"])
        if len(suggestions) == limit:
            break

    for suggestion in deferred:
        if len(suggestions) == limit:
            break
        if suggestion["prompt"] in seen_prompts:
            continue
        suggestions.append(suggestion)
        seen_prompts.add(suggestion["prompt"])

    return {"suggestions": suggestions}


@app.post("/chat")
async def chat_with_brain(payload: ChatRequest, http_request: Request):
    """
    Chat interface for querying the knowledge graph.
    Uses RAG: embed query → hybrid search → LLM synthesis.
    """
    try:
        user = await _authorized_org_user(http_request, payload.org_id)
        stored_history: List[ChatMessage] = []
        if payload.conversation_id:
            stored = await get_chat_conversation(
                payload.org_id, user["id"], payload.conversation_id
            )
            if stored is None:
                raise HTTPException(status_code=404, detail="Conversation not found")
            conversation = stored["conversation"]
            stored_history = [
                ChatMessage(
                    role=message["role"],
                    content=message["content"],
                    sources=message.get("sources"),
                )
                for message in stored["messages"]
            ]
        else:
            conversation = await create_chat_conversation(
                payload.org_id, user["id"], _chat_title(payload.message)
            )

        conversation_id = conversation["id"]
        conversation_history = stored_history or payload.conversation_history
        persisted_user_message = await append_chat_message(
            payload.org_id,
            user["id"],
            conversation_id,
            "user",
            payload.message,
        )
        if persisted_user_message is None:
            raise HTTPException(status_code=404, detail="Conversation not found")

        mock_mode = os.getenv("KOMPONIST_AI_MODE", "live").lower() == "mock"
        llm = None if mock_mode else get_llm()
        if mock_mode:
            plan = _fallback_chat_plan(payload.message)
        else:
            try:
                plan = await _plan_chat_query(
                    llm, payload.message, conversation_history
                )
            except Exception as planner_error:
                print(f"Chat query planning failed: {planner_error}")
                plan = _fallback_chat_plan(payload.message, broad=True)

        operation = plan["operation"]
        retrieval_query = plan.get("query") or payload.message
        entity_types = plan.get("entity_types") or []

        # 1. Try to embed user query for semantic search
        query_embedding = None
        if not mock_mode and operation == "search":
            try:
                query_embedding = await embed(retrieval_query)
            except Exception as e:
                print(f"Embedding failed: {e}")

        # 2. Execute the allowlisted plan against confirmed organization data.
        count_rows: List[dict] = []
        if operation in {"list", "overview", "count"}:
            if operation in {"count", "overview"}:
                count_rows = await _count_chat_entities(
                    payload.org_id,
                    user,
                    entity_types,
                    plan.get("group_by", "none"),
                )
            search_results = await _browse_chat_entities(
                payload.org_id,
                user,
                entity_types,
                limit=100 if operation in {"overview", "count"} else plan["limit"],
                sort=plan.get("sort", "newest"),
            )
        else:
            search_results = []

        if not mock_mode and operation == "search":
            try:
                search_results = await BrainQueries.hybrid_search(
                    org_id=payload.org_id,
                    query_text=retrieval_query,
                    query_embedding=query_embedding,
                    # A model-inferred type is a ranking hint, not an irreversible
                    # pre-filter: preserving recall matters more for focused search.
                    entity_types=None,
                    k=min(plan["limit"], 20),
                    status="confirmed",
                    department_ids=user.get("department_ids") or [],
                    access_all_departments=bool(
                        user.get("access_all_departments")
                    ),
                )
            except Exception as search_error:
                print(f"Hybrid search failed: {search_error}")

        if operation == "search":
            try:
                literal_results: List[dict] = []
                seen_literal_ids = set()
                # Query expansion keeps named entities from the original wording
                # while the standalone rewrite resolves pronouns in follow-ups.
                for literal_query in dict.fromkeys([
                    retrieval_query, payload.message
                ]):
                    for result in await _literal_chat_search(
                        payload.org_id,
                        user,
                        literal_query,
                        k=min(plan["limit"], 20),
                        entity_types=None,
                    ):
                        if result["id"] not in seen_literal_ids:
                            literal_results.append(result)
                            seen_literal_ids.add(result["id"])
                merged = {result["id"]: result for result in literal_results}
                for result in search_results:
                    merged.setdefault(result["id"], result)
                search_results = list(merged.values())[:min(plan["limit"], 20)]
                if entity_types:
                    search_results.sort(
                        key=lambda result: result.get("entity_type") in entity_types,
                        reverse=True,
                    )
            except Exception as fallback_error:
                print(f"Literal fallback search failed: {fallback_error}")

            if plan.get("expand_graph"):
                try:
                    neighbors = await _expand_chat_graph_context(
                        payload.org_id, user, search_results, limit=8
                    )
                    expanded = {result["id"]: result for result in search_results}
                    for neighbor in neighbors:
                        expanded.setdefault(neighbor["id"], neighbor)
                    search_results = list(expanded.values())[:20]
                except Exception as expansion_error:
                    print(f"Graph context expansion failed: {expansion_error}")

        await _attach_chat_evidence(payload.org_id, user, search_results)

        # 3. Build context from results
        context, sources = _chat_context_and_sources(search_results)

        # 4. Build conversation context
        conversation_context = ""
        if conversation_history:
            history_parts = []
            for msg in conversation_history[-6:]:  # Last 3 user/assistant turns
                history_parts.append(f"{msg.role}: {msg.content}")
            conversation_context = "\n".join(history_parts) + "\n\n"

        # 5. Call LLM with RAG context
        system_prompt = """You are Komponist, an AI assistant that helps users query their company's knowledge graph.

You have access to confirmed facts, decisions, goals, and relationships from the knowledge graph.

When answering:
- Base your answers on the provided context from the knowledge graph
- Start with the direct answer in the first sentence; do not begin with a preamble such as "Based on the context"
- For duration, quantity, date, owner, or yes/no questions, state the exact value immediately
- Render quantities with digits when possible (for example, "four weeks" becomes "4 Wochen" in German)
- Prioritize the most relevant fact and only add context that helps answer the question
- Cite claims with the numbered evidence markers included in the context, such as [1]
- Never invent a citation or use information from proposed/rejected entities
- If the context is empty or doesn't contain the answer, explain that the knowledge graph is empty or doesn't have that information yet
- Suggest that the user should add sources to populate the knowledge graph (via the Onboard page)
- Be concise but complete; use bullets only when the question asks for a list or several distinct items
- The retrieval operation is {operation}; for a list, include every provided entity exactly once
- For an overview, accurately describe the supplied type counts before summarizing the knowledge
- Write the entire answer in {language}
- Answer in English by default, even when the question is written in another language
- Switch languages only when the user explicitly asks for a specific response language

Exact confirmed counts (empty unless relevant):
{counts}

Context from knowledge graph:
{context}"""

        user_prompt = f"{conversation_context}User question: {payload.message}"

        if operation == "count":
            answer = _aggregate_count_answer(plan, count_rows, sources)
        else:
            answer = _mock_chat_answer(
                payload.message, search_results, sources
            ) if mock_mode else None
        formatted_system_prompt = system_prompt.format(
            operation=operation,
            language=plan["language"],
            counts=json.dumps(count_rows, ensure_ascii=False),
            context=context,
        )

        if payload.stream:
            # Streaming response
            async def generate_stream():
                try:
                    yield {
                        "event": "conversation",
                        "data": json.dumps({
                            "conversation_id": conversation_id,
                            "title": conversation["title"],
                        }),
                    }
                    if answer is not None:
                        generated_answer = answer
                    else:
                        generated_answer = await _generate_grounded_chat_answer(
                            llm,
                            user_prompt,
                            formatted_system_prompt,
                            sources,
                        )
                    persisted_assistant_message = await append_chat_message(
                        payload.org_id,
                        user["id"],
                        conversation_id,
                        "assistant",
                        generated_answer,
                        sources,
                    )
                    if persisted_assistant_message is None:
                        raise RuntimeError("Conversation was removed while answering")
                    yield {
                        "event": "message",
                        "data": json.dumps({"content": generated_answer})
                    }
                    # Send sources at the end
                    yield {
                        "event": "sources",
                        "data": json.dumps({"sources": sources})
                    }
                    yield {"event": "done", "data": ""}
                except Exception as e:
                    yield {
                        "event": "error",
                        "data": json.dumps({"error": str(e)})
                    }

            return EventSourceResponse(generate_stream())
        else:
            # Non-streaming response
            if answer is None:
                answer = await _generate_grounded_chat_answer(
                    llm,
                    user_prompt,
                    formatted_system_prompt,
                    sources,
                )

            persisted_assistant_message = await append_chat_message(
                payload.org_id,
                user["id"],
                conversation_id,
                "assistant",
                answer,
                sources,
            )
            if persisted_assistant_message is None:
                raise HTTPException(
                    status_code=404, detail="Conversation was removed while answering"
                )

            return ChatResponse(
                response=answer,
                sources=sources,
                conversation_id=conversation_id,
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# =============================================================================
# Settings API endpoints
# =============================================================================

@app.get("/approvals")
async def get_approvals(
    request: Request,
    org_id: str = Query(...),
    status: Optional[str] = Query(None),
):
    """List durable agent approval requests for human review."""
    await _authorized_org_user(request, org_id, manage=True)
    if status not in {None, "pending", "approved", "denied"}:
        raise HTTPException(
            status_code=400, detail="status must be pending, approved, or denied"
        )
    approvals = await list_approval_requests(org_id, status)
    return {"approvals": approvals, "total": len(approvals)}


@app.post("/approvals/{approval_id}/resolve")
async def resolve_approval_endpoint(
    approval_id: str,
    payload: ApprovalResolutionRequest,
    request: Request,
    org_id: str = Query(...),
):
    """Approve or deny a pending MCP request exactly once."""
    user = await _authorized_org_user(request, org_id, manage=True)
    approval = await resolve_approval_request(
        org_id, approval_id, payload.approved, user["email"]
    )
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval request not found")
    return approval

@app.get("/settings")
async def get_settings(request: Request, org_id: str = Query(...)):
    """Get settings for an organization."""
    await _authorized_org_user(request, org_id)
    return await get_org_settings(org_id)


@app.put("/settings")
async def update_settings(
    request: Request,
    payload: Optional[OrgSettingsUpdate] = None,
    org_id: str = Query(...),
    auto_confirm: Optional[bool] = Query(None, description="Auto-confirm extracted entities"),
    parallel_batch_size: Optional[int] = Query(None, description="Parallel processing batch size")
):
    """Update settings for an organization."""
    await _authorized_org_user(request, org_id, manage=True)
    resolved_auto_confirm = payload.auto_confirm if payload else auto_confirm
    resolved_batch_size = payload.parallel_batch_size if payload else parallel_batch_size
    current = await get_org_settings(org_id)
    saved = await save_org_settings(
        org_id=org_id,
        auto_confirm=(
            resolved_auto_confirm
            if resolved_auto_confirm is not None
            else current["auto_confirm"]
        ),
        parallel_batch_size=(
            max(1, min(10, resolved_batch_size))
            if resolved_batch_size is not None
            else current["parallel_batch_size"]
        ),
    )
    return {**current, **saved}


@app.get("/settings/ai")
async def get_ai_settings(
    request: Request, org_id: str = Query(...)
):
    """Return only non-secret status for the centrally managed provider."""
    await _authorized_org_user(request, org_id)
    mode = os.getenv("KOMPONIST_AI_MODE", "live").lower()
    return {
        "mode": mode,
        "provider": "openai" if mode == "live" else "mock",
        "model": os.getenv("KOMPONIST_LLM_MODEL", "gpt-5.6-luna"),
        "embedding_model": "text-embedding-3-small",
        "configured": bool(os.getenv("OPENAI_API_KEY")) if mode == "live" else True,
        "managed_by": "komponist",
    }


@app.post("/settings/ai/test")
async def test_ai_settings(request: Request, org_id: str = Query(...)):
    """Test the server-managed provider without exposing its API key."""
    await _authorized_org_user(request, org_id, manage=True)
    try:
        if os.getenv("KOMPONIST_AI_MODE", "live").lower() == "mock":
            return {"status": "ok", "mode": "mock", "message": "Mock mode is ready"}
        from core.embeddings import get_embedder
        from core.llm import get_llm

        llm_client = get_llm()
        embedding_client = get_embedder()
        response = await llm_client.call(
            "Reply with exactly OK.", max_tokens=16, temperature=0, max_retries=1
        )
        vector = await embedding_client.embed("Komponist connection test")
        return {
            "status": "ok",
            "mode": "live",
            "model": response["model"],
            "embedding_dimensions": len(vector),
            "message": "OpenAI generation and embeddings are ready",
        }
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/auth/organizations/{org_id}/api-keys")
async def get_organization_api_keys(org_id: str, request: Request):
    await _authorized_org_user(request, org_id, manage=True)
    return {"keys": await list_api_keys(org_id)}


@app.post("/auth/organizations/{org_id}/api-keys", status_code=201)
async def add_organization_api_key(
    org_id: str, payload: ApiKeyCreateRequest, request: Request
):
    user = await _authorized_org_user(request, org_id, manage=True)
    return await create_api_key(org_id, payload.name.strip(), user["id"])


@app.delete("/auth/organizations/{org_id}/api-keys/{key_id}", status_code=204)
async def delete_organization_api_key(
    org_id: str, key_id: str, request: Request
):
    await _authorized_org_user(request, org_id, manage=True)
    if not await revoke_api_key(org_id, key_id):
        raise HTTPException(status_code=404, detail="API key not found")


async def _api_key_organization(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    scheme, _, raw_key = authorization.partition(" ")
    org_id = await authenticate_api_key(raw_key.strip()) if scheme.casefold() == "bearer" else None
    if not org_id:
        raise HTTPException(status_code=401, detail="Valid Bearer API key required")
    return org_id


@app.get("/v1/context")
async def api_context_search(
    request: Request,
    query: str = Query(..., min_length=1, max_length=500),
    types: Optional[List[str]] = Query(None),
    limit: int = Query(8, ge=1, le=20),
):
    """Search confirmed, cited context using an organization API key."""
    org_id = await _api_key_organization(request)
    requested_types = types or []
    invalid_types = sorted(set(requested_types) - set(_CHAT_ENTITY_TYPES))
    if invalid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported entity types: {', '.join(invalid_types)}",
        )
    terms = _chat_search_terms(query)[:12]
    candidate_ids: list[str] = []
    if terms:
        literal_rows = await GraphClient.run_query(
            """
            MATCH (e:Entity {org_id: $org_id, status: 'confirmed'})
            WHERE (size($types) = 0 OR e.entity_type IN $types)
              AND any(term IN $terms WHERE toLower(e.statement) CONTAINS term OR
                      toLower(coalesce(e.detail, '')) CONTAINS term)
            WITH e, size([term IN $terms WHERE
                toLower(e.statement) CONTAINS term OR
                toLower(coalesce(e.detail, '')) CONTAINS term]) AS relevance
            RETURN e.id AS id
            ORDER BY relevance DESC, e.confirmed_at DESC
            LIMIT $candidate_limit
            """,
            {
                "org_id": org_id,
                "terms": terms,
                "types": requested_types,
                "candidate_limit": limit * 2,
            },
        )
        candidate_ids.extend(row["id"] for row in literal_rows)

    if os.getenv("KOMPONIST_AI_MODE", "live").lower() != "mock":
        try:
            query_embedding = await embed(query)
            semantic_rows = await BrainQueries.hybrid_search(
                org_id=org_id,
                query_text=query,
                query_embedding=query_embedding,
                entity_types=requested_types or None,
                k=limit * 2,
                status="confirmed",
            )
            candidate_ids.extend(row["id"] for row in semantic_rows)
        except Exception as search_error:
            print(
                "[API] Semantic context search failed; using literal fallback: "
                f"{type(search_error).__name__}"
            )

    candidate_ids = list(dict.fromkeys(candidate_ids))
    if not candidate_ids:
        return {"items": [], "total": 0, "query": query}

    cited_rows = await GraphClient.run_query(
        """
        MATCH (e:Entity {org_id: $org_id, status: 'confirmed'})
        WHERE e.id IN $candidate_ids
          AND (size($types) = 0 OR e.entity_type IN $types)
        MATCH (e)-[:CITED_BY]->(ev:Evidence {org_id: $org_id})
        RETURN e.id AS id, e.entity_type AS type, e.statement AS statement,
               e.detail AS detail, e.confidence AS confidence,
               collect(DISTINCT ev{.id, .source, .reference, .url,
                                    .excerpt, .source_date}) AS evidence
        """,
        {
            "org_id": org_id,
            "candidate_ids": candidate_ids,
            "types": requested_types,
        },
    )
    by_id = {row["id"]: row for row in cited_rows}
    rows = [by_id[entity_id] for entity_id in candidate_ids if entity_id in by_id][
        :limit
    ]
    return {"items": rows, "total": len(rows), "query": query}


@app.get("/v1/brain")
async def api_brain_info(request: Request):
    """Return compact API-key-authenticated company-brain metadata."""
    org_id = await _api_key_organization(request)
    rows = await GraphClient.run_query(
        """
        MATCH (entity:Entity {org_id: $org_id})
        RETURN entity.status AS status, entity.entity_type AS type, count(entity) AS count
        ORDER BY status, type
        """,
        {"org_id": org_id},
    )
    counts_by_status: Dict[str, int] = {}
    counts_by_type: Dict[str, int] = {}
    for row in rows:
        counts_by_status[row["status"]] = counts_by_status.get(row["status"], 0) + row["count"]
        if row["status"] == "confirmed":
            counts_by_type[row["type"]] = row["count"]
    return {
        "organization_id": org_id,
        "confirmed": counts_by_status.get("confirmed", 0),
        "pending_review": counts_by_status.get("proposed", 0),
        "confirmed_by_type": counts_by_type,
    }


@app.get("/v1/decisions")
async def api_active_decisions(
    request: Request,
    project_id: Optional[str] = Query(None, max_length=100),
    limit: int = Query(20, ge=1, le=100),
):
    """Return active, cited decisions for an API-key organization."""
    org_id = await _api_key_organization(request)
    decisions = await BrainQueries.active_decisions(
        org_id=org_id, project_id=project_id, k=limit
    )
    return {"decisions": decisions, "total": len(decisions)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
