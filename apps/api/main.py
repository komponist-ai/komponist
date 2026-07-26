"""
Komponist API

FastAPI application for webhooks, REST endpoints, and health checks.
The programmable company brain.
"""

import asyncio
import os
import hashlib
import ipaddress
import json
import re
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any, Literal
from urllib.parse import urlsplit, urlunsplit

import httpx
from fastapi import FastAPI, HTTPException, UploadFile, File, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import delete, select

import sys
sys.path.append("../../packages")

from core.graph import GraphClient
from core.schema import GraphSchema
from core.export import export_brain_yaml
from core.import_ import import_brain_yaml, parse_export_yaml
from core.versioning import (
    build_document_families,
    demo_document_versions,
    normalize_document_title,
)
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
    create_generated_artifact,
    delete_chat_conversation,
    delete_connected_source,
    delete_generated_artifact,
    get_chat_conversation,
    get_connected_source,
    artifact_record_dict,
    get_generated_artifact,
    list_chat_conversations,
    list_approval_requests,
    list_connected_sources,
    list_generated_artifacts,
    list_api_keys,
    load_org_settings,
    save_org_settings,
    revoke_api_key,
    resolve_approval_request,
    rename_chat_conversation,
    set_connected_source_department,
    update_connected_source,
    update_connected_source_config,
    upsert_single_source_type,
)
from artifacts import (
    ARTIFACT_SCHEMA,
    artifact_filename,
    artifact_markdown,
    artifact_pdf,
    artifact_pptx,
    generation_prompt,
    mock_artifact_content,
    sanitize_artifact_content,
    source_deep_link_path,
)
import workroom_queue
from workroom_artifacts import (
    artifact_sharing,
    get_org_artifact,
    list_room_artifacts,
    resolve_room_access as resolve_artifact_room_access,
    share_artifact,
    unshare_artifact,
)
from workroom_messages import (
    create_message as create_workroom_message,
    delete_message as delete_workroom_message,
    edit_message as edit_workroom_message_body,
    list_messages as list_workroom_messages,
    normalize_references as normalize_message_references,
    resolve_mentions as resolve_message_mentions,
)
from workroom_context import (
    build_context_preview,
    list_context_items as list_workroom_context_items,
    remove_context_item as remove_workroom_context_item,
    set_context_item as set_workroom_context_item,
)
from workroom_plans import (
    PlanGenerationError,
    PlanSpec,
    approve_draft as approve_plan_draft,
    create_plan_version,
    generate_plan_spec,
    list_plan_versions,
    reject_draft,
    replace_draft_spec,
)
from workroom_agent import (
    TERMINAL_STATES as WORKROOM_TERMINAL_STATES,
    enqueue_finalize,
    enqueue_research,
)
from workrooms import (
    add_member as add_workroom_member,
    archive_task as archive_workroom_task_record,
    edit_task as edit_workroom_task_details,
    list_runs_for_task,
    reorder_tasks as reorder_workroom_task_records,
    count_active_owners,
    effective_room_role,
    get_membership as get_workroom_membership,
    get_org_member,
    list_members as list_workroom_members,
    remove_member as remove_workroom_member,
    room_can,
    set_member_role as set_workroom_member_role,
    update_room_settings,
    append_event as append_workroom_event,
    create_room as create_workroom,
    create_run as create_workroom_run,
    create_task as create_workroom_task,
    get_room as load_workroom,
    get_room_record,
    get_run as load_workroom_run,
    list_events_after,
    list_rooms as load_workrooms,
    transition_run as transition_workroom_run,
    update_run as update_workroom_run,
    update_task as update_workroom_task,
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

def _cors_origins(value: str) -> list[str]:
    """Include the apex/www counterpart for configured web origins.

    Both hostnames can serve the web app during initial DNS setup. Allowing the
    counterpart prevents an opaque browser "Failed to fetch" during login while
    still keeping CORS restricted to explicitly related origins.
    """
    origins: list[str] = []
    for raw_origin in value.split(","):
        origin = raw_origin.strip().rstrip("/")
        if not origin:
            continue
        origins.append(origin)

        parsed = urlsplit(origin)
        hostname = parsed.hostname
        if not hostname or hostname == "localhost":
            continue
        try:
            ipaddress.ip_address(hostname)
            continue
        except ValueError:
            pass

        alias_hostname = hostname[4:] if hostname.startswith("www.") else f"www.{hostname}"
        alias_netloc = alias_hostname
        if parsed.port:
            alias_netloc = f"{alias_netloc}:{parsed.port}"
        origins.append(urlunsplit((parsed.scheme, alias_netloc, "", "", "")))

    return list(dict.fromkeys(origins))


# CORS
cors_origins = _cors_origins(
    os.getenv("CORS_ORIGINS", "http://localhost:3000")
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

# Registered after the app and its middleware exist. canvas_routes imports
# main lazily inside its handlers, so there is no import cycle.
from canvas_routes import router as canvas_router  # noqa: E402

app.include_router(canvas_router)

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
        "id": "demo-campus-forum",
        "type": "Project",
        "statement": "The Campus Forum project runs for 6 weeks and ends with the event on 14 November 2026.",
        "detail": "The Events, Partnerships, and Communications departments deliver the forum together.",
        "source": "08-campus-forum-plan-v2.md",
        "excerpt": "Project: The Campus Forum project runs for six weeks and ends with the event on 14 November 2026.",
    },
    {
        "id": "demo-board-confidentiality",
        "type": "Constraint",
        "statement": "Board minutes marked highly confidential are visible only to board members.",
        "detail": "Department members cannot access highly confidential board material.",
        "source": "04-data-and-access-policy.md",
        "excerpt": "Constraint: Board minutes marked highly confidential are visible only to board members.",
    },
    {
        "id": "demo-sponsor-package",
        "type": "Decision",
        "statement": "CampusKollektiv offers one main sponsorship package for €1,500.",
        "detail": "Partnerships owns sponsor outreach and Finance approves invoices.",
        "source": "06-sponsorship-policy.md",
        "excerpt": "Decision: CampusKollektiv offers one main sponsorship package for €1,500.",
    },
    {
        "id": "demo-membership-goal",
        "type": "Goal",
        "statement": "CampusKollektiv aims to recruit 40 active student members by 31 December 2026.",
        "detail": "The People department owns onboarding and retention.",
        "source": "02-semester-strategy.md",
        "excerpt": "Goal: CampusKollektiv recruits 40 active student members by 31 December 2026.",
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
        "workspace": "CampusKollektiv demo workspace",
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

    try:
        worker_health = await workroom_queue.queue_health()
    except Exception as error:  # noqa: BLE001 - never fail the health probe
        worker_health = {"status": "unknown", "error": str(error)[:200]}

    return {
        "status": "healthy" if overall_healthy else "degraded",
        "services": {
            "neo4j": neo4j_health,
            "postgres": postgres_health,
            # Reported separately: the API stays healthy and keeps accepting
            # work even when no Workroom worker is currently online.
            "workroom_worker": worker_health,
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
async def get_queue(
    request: Request,
    org_id: str = Query(...),
    entity_type: Optional[str] = Query(None),
    query: str = Query("", max_length=200),
    limit: int = Query(24, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Get review queue (proposed entities)."""
    user = await _authorized_org_user(request, org_id)
    normalized_query = " ".join(query.casefold().split())
    cypher = f"""
    MATCH (e:Entity {{org_id: $org_id, status: 'proposed'}})
    WHERE {_knowledge_scope('e')}
      AND ($entity_type IS NULL OR e.entity_type = $entity_type)
      AND (
        $query = ''
        OR toLower(coalesce(e.statement, '')) CONTAINS $query
        OR toLower(coalesce(e.detail, '')) CONTAINS $query
      )
    WITH e
    ORDER BY e.created_at DESC, e.id
    SKIP $offset
    LIMIT $limit
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

    params = _scoped_params(
        org_id,
        user,
        entity_type=entity_type,
        query=normalized_query,
        limit=limit,
        offset=offset,
    )
    results = await GraphClient.run_query(cypher, params)
    totals = await GraphClient.run_query(
        f"""
        MATCH (e:Entity {{org_id: $org_id, status: 'proposed'}})
        WHERE {_knowledge_scope('e')}
          AND ($entity_type IS NULL OR e.entity_type = $entity_type)
          AND (
            $query = ''
            OR toLower(coalesce(e.statement, '')) CONTAINS $query
            OR toLower(coalesce(e.detail, '')) CONTAINS $query
          )
        RETURN count(e) AS total
        """,
        params,
    )
    type_counts = await GraphClient.run_query(
        f"""
        MATCH (e:Entity {{org_id: $org_id, status: 'proposed'}})
        WHERE {_knowledge_scope('e')}
          AND (
            $query = ''
            OR toLower(coalesce(e.statement, '')) CONTAINS $query
            OR toLower(coalesce(e.detail, '')) CONTAINS $query
          )
        RETURN e.entity_type AS entity_type, count(e) AS count
        ORDER BY entity_type
        """,
        params,
    )
    pending_totals = await GraphClient.run_query(
        f"""
        MATCH (e:Entity {{org_id: $org_id, status: 'proposed'}})
        WHERE {_knowledge_scope('e')}
        RETURN count(e) AS total
        """,
        params,
    )

    # Filter out null evidence/related_to
    for r in results:
        r["evidence"] = [e for e in r.get("evidence", []) if e.get("id")]
        r["related_to"] = [rel for rel in r.get("related_to", []) if rel.get("id")]

    total = int(totals[0]["total"]) if totals else 0
    return {
        "items": results,
        "total": total,
        "pending_total": int(pending_totals[0]["total"]) if pending_totals else 0,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(results) < total,
        "counts_by_type": {
            row["entity_type"]: row["count"]
            for row in type_counts
            if row.get("entity_type")
        },
    }


@app.get("/entities")
async def list_entities(
    request: Request,
    org_id: str = Query(...),
    status: str = "confirmed",
    entity_type: Optional[str] = None,
    query: str = Query("", max_length=200),
    limit: int = Query(24, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List brain entities."""
    user = await _authorized_org_user(request, org_id)
    allowed_statuses = {"confirmed", "proposed", "rejected", "all"}
    if status not in allowed_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"status must be one of {sorted(allowed_statuses)}",
        )

    normalized_query = " ".join(query.casefold().split())
    cypher = f"""
    MATCH (e:Entity {{org_id: $org_id}})
    WHERE ($status = 'all' OR e.status = $status)
      AND ($entity_type IS NULL OR e.entity_type = $entity_type)
      AND (
        $query = ''
        OR toLower(coalesce(e.statement, '')) CONTAINS $query
        OR toLower(coalesce(e.detail, '')) CONTAINS $query
      )
      AND {_knowledge_scope('e')}
    WITH e
    ORDER BY e.confirmed_at DESC, e.created_at DESC, e.id
    SKIP $offset
    LIMIT $limit
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
    """

    params = _scoped_params(
        org_id,
        user,
        status=status,
        entity_type=entity_type,
        query=normalized_query,
        limit=limit,
        offset=offset,
    )

    results = await GraphClient.run_query(cypher, params)
    type_counts = await GraphClient.run_query(
        f"""
        MATCH (e:Entity {{org_id: $org_id}})
        WHERE ($status = 'all' OR e.status = $status)
          AND (
            $query = ''
            OR toLower(coalesce(e.statement, '')) CONTAINS $query
            OR toLower(coalesce(e.detail, '')) CONTAINS $query
          )
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
          AND (
            $query = ''
            OR toLower(coalesce(e.statement, '')) CONTAINS $query
            OR toLower(coalesce(e.detail, '')) CONTAINS $query
          )
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
    total = (
        counts_by_type.get(entity_type, 0)
        if entity_type
        else sum(counts_by_type.values())
    )

    return {
        "entities": results,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(results) < total,
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

    # A relationship becomes trusted only after both endpoint facts have passed
    # human review. This prevents proposed graph edges from influencing chat.
    await GraphClient.run_query(
        """
        MATCH (entity:Entity {id: $entity_id, org_id: $org_id})-[relation]-
              (other:Entity {org_id: $org_id, status: 'confirmed'})
        WHERE entity.status = 'confirmed'
          AND type(relation) IN [
              'ADVANCES', 'AFFECTS', 'DEPENDS_ON', 'SUPERSEDES',
              'CONSTRAINS', 'RELATES_TO'
          ]
        SET relation.status = 'confirmed',
            relation.confirmed_at = datetime()
        """,
        {"entity_id": entity_id, "org_id": org_id},
    )

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


class SlackChannelSelection(BaseModel):
    channel_ids: List[str] = Field(min_length=1, max_length=100)


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
    if not token.startswith(("ntn_", "secret_")):
        raise HTTPException(
            status_code=400,
            detail="Use a Notion Internal Integration token starting with ntn_ or secret_",
        )
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
    from integrations.slack import (
        SLACK_CLIENT_ID,
        SLACK_CLIENT_SECRET,
        get_oauth_url,
    )
    org = _validated_oauth_org(org)
    await _authorized_org_user(request, org, manage=True)
    if not SLACK_CLIENT_ID or not SLACK_CLIENT_SECRET:
        return {
            "error": (
                "Slack OAuth is not configured on this Komponist deployment"
            ),
        }
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
                "watched_channels": [],
                "channel_names": {},
                "oauth": True,
            },
        )
        return _oauth_redirect("slack", org_id, "connected")
    except Exception as error:
        print(f"[Slack OAuth] Callback failed for org {org_id}: {type(error).__name__}")
        return _oauth_redirect("slack", org_id, "error")


async def _slack_source(
    request: Request,
    org_id: str,
    source_id: str,
) -> dict:
    await _authorized_org_user(request, org_id, manage=True)
    source = await get_connected_source(org_id, source_id, include_config=True)
    if source is None or source.get("type") != "slack":
        raise HTTPException(status_code=404, detail="Slack source not found")
    if not source.get("config", {}).get("token"):
        raise HTTPException(status_code=409, detail="Reconnect Slack to refresh access")
    return source


@app.get("/sources/{source_id}/slack/channels")
async def slack_source_channels(
    source_id: str,
    request: Request,
    org_id: str = Query(...),
):
    """List readable Slack channels and the connector's explicit allowlist."""
    from integrations.slack import SlackApiError, list_channels

    source = await _slack_source(request, org_id, source_id)
    config = source["config"]
    try:
        channels = await list_channels(config["token"])
    except SlackApiError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {
        "channels": channels,
        "selected_channel_ids": config.get("watched_channels") or [],
    }


@app.put("/sources/{source_id}/slack/channels")
async def update_slack_source_channels(
    source_id: str,
    payload: SlackChannelSelection,
    request: Request,
    org_id: str = Query(...),
):
    """Persist a verified, organization-scoped Slack channel allowlist."""
    from integrations.slack import SlackApiError, list_channels

    source = await _slack_source(request, org_id, source_id)
    config = source["config"]
    try:
        available = await list_channels(config["token"])
    except SlackApiError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    available_by_id = {channel["id"]: channel for channel in available}
    selected_ids = list(dict.fromkeys(payload.channel_ids))
    unknown = [channel_id for channel_id in selected_ids if channel_id not in available_by_id]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail="One or more Slack channels are no longer available",
        )
    not_joined = [
        available_by_id[channel_id]["name"]
        for channel_id in selected_ids
        if not available_by_id[channel_id].get("is_member")
    ]
    if not_joined:
        raise HTTPException(
            status_code=400,
            detail=(
                "Invite the Komponist Slack app to these channels first: "
                + ", ".join(f"#{name}" for name in not_joined)
            ),
        )

    config["watched_channels"] = selected_ids
    config["channel_names"] = {
        channel_id: available_by_id[channel_id]["name"]
        for channel_id in selected_ids
    }
    updated = await update_connected_source_config(
        org_id,
        source_id,
        config,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Slack source not found")
    return {
        "status": "configured",
        "selected_channel_ids": selected_ids,
        "channels": [available_by_id[channel_id] for channel_id in selected_ids],
    }


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


def _connector_type_for_evidence(source_type: str) -> str:
    return {
        "manual": "local",
        "google_drive": "google",
        "gdrive": "google",
    }.get(source_type.casefold(), source_type.casefold())


def _evidence_location(source_type: str, row: dict) -> dict:
    page = row.get("page")
    line_start = row.get("line_start")
    line_end = row.get("line_end")
    if page is not None:
        return {"kind": "page", "label": f"Page {page}", "page": page}
    if line_start is not None:
        is_range = bool(line_end and line_end != line_start)
        return {
            "kind": "lines",
            "label": (
                f"Lines {line_start}–{line_end}"
                if is_range else f"Line {line_start}"
            ),
            "line_start": line_start,
            "line_end": line_end,
        }
    labels = {
        "slack": ("thread", "Highlighted thread passage"),
        "notion": ("page", "Highlighted Notion passage"),
        "google": ("document", "Highlighted Google Drive passage"),
        "google_drive": ("document", "Highlighted Google Drive passage"),
        "upload": ("passage", "Highlighted uploaded passage"),
        "manual": ("passage", "Highlighted local passage"),
    }
    kind, label = labels.get(source_type.casefold(), ("passage", "Highlighted passage"))
    return {"kind": kind, "label": label}


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


@app.get("/evidence/{evidence_id}")
async def get_evidence_passage(
    evidence_id: str,
    request: Request,
    org_id: str = Query(...),
):
    """Resolve one citation into a permission-checked source passage."""
    user = await _authorized_org_user(request, org_id)
    rows = await GraphClient.run_query(
        f"""
        MATCH (entity:Entity {{
            org_id: $org_id,
            status: 'confirmed'
        }})-[:CITED_BY]->(evidence:Evidence {{
            org_id: $org_id,
            id: $evidence_id
        }})
        WHERE {_knowledge_scope('entity')} AND {_evidence_scope('evidence')}
        RETURN
            evidence.id AS id,
            evidence.source AS source,
            evidence.reference AS reference,
            evidence.title AS title,
            evidence.url AS url,
            evidence.excerpt AS excerpt,
            evidence.document_id AS document_id,
            evidence.kind AS document_kind,
            evidence[$page_property] AS page,
            evidence[$line_start_property] AS line_start,
            evidence[$line_end_property] AS line_end,
            toString(evidence.source_date) AS source_date,
            collect(DISTINCT entity.entity_type) AS entity_types,
            collect(DISTINCT entity.statement) AS statements
        LIMIT 1
        """,
        _scoped_params(
            org_id,
            user,
            evidence_id=evidence_id,
            page_property="page",
            line_start_property="line_start",
            line_end_property="line_end",
        ),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Source passage not found")

    row = rows[0]
    source_type = str(row.get("source") or "unknown")
    reference = str(row.get("reference") or "Unknown reference")
    return {
        "id": row["id"],
        "source": source_type,
        "source_type": _connector_type_for_evidence(source_type),
        "reference": reference,
        "title": row.get("title") or _document_title(reference),
        "url": row.get("url"),
        "excerpt": row.get("excerpt") or "",
        "document_id": row.get("document_id"),
        "document_kind": row.get("document_kind"),
        "source_date": row.get("source_date"),
        "entity_types": [item for item in row.get("entity_types", []) if item],
        "statements": [item for item in row.get("statements", []) if item],
        "location": _evidence_location(source_type, row),
    }


@app.get("/sources/{source_id}/documents")
async def list_source_documents(
    request: Request,
    source_id: str,
    org_id: str = Query(...),
    query: str = Query("", max_length=200),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List document-level evidence stored by Komponist for one connector."""
    user = await _authorized_org_user(request, org_id)
    source = await get_connected_source(org_id, source_id)
    if not source or not _source_visible_to_user(source, user):
        raise HTTPException(status_code=404, detail="Source not found")

    normalized_query = " ".join(query.casefold().split())
    params = _scoped_params(
        org_id,
        user,
        source_types=_source_evidence_types(source["type"]),
        query=normalized_query,
        limit=limit,
        offset=offset,
    )
    rows = await GraphClient.run_query(
        f"""
        MATCH (ev:Evidence {{org_id: $org_id}})
        WHERE toLower(ev.source) IN $source_types
          AND {_evidence_scope('ev')}
          AND (
            $query = ''
            OR toLower(coalesce(ev.title, '')) CONTAINS $query
            OR toLower(coalesce(ev.reference, '')) CONTAINS $query
          )
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
        SKIP $offset
        LIMIT $limit
        """,
        params,
    )
    totals = await GraphClient.run_query(
        f"""
        MATCH (ev:Evidence {{org_id: $org_id}})
        WHERE toLower(ev.source) IN $source_types
          AND {_evidence_scope('ev')}
          AND (
            $query = ''
            OR toLower(coalesce(ev.title, '')) CONTAINS $query
            OR toLower(coalesce(ev.reference, '')) CONTAINS $query
          )
        RETURN count(DISTINCT ev.reference) AS total
        """,
        params,
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

    total = int(totals[0]["total"]) if totals else 0
    return {
        "documents": documents,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(documents) < total,
    }


@app.get("/versions")
async def list_document_versions(
    request: Request,
    org_id: str = Query(...),
    include_demo: bool = Query(True),
    scope: str = Query("all"),
    query: str = Query("", max_length=200),
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
):
    """Build cross-source document families and semantic claim diffs.

    Evidence remains the source of truth for access control. New ingestions
    also carry a DocumentVersion node, while this query keeps older evidence
    useful by deriving a legacy version identity from its reference.
    """
    user = await _authorized_org_user(request, org_id)
    if scope not in {"all", "workspace", "example"}:
        raise HTTPException(
            status_code=400,
            detail="scope must be one of all, workspace, example",
        )
    rows = await GraphClient.run_query(
        f"""
        MATCH (evidence:Evidence {{org_id: $org_id}})
        WHERE {_evidence_scope('evidence')}
        OPTIONAL MATCH (document:DocumentVersion {{org_id: $org_id}})-[:HAS_EVIDENCE]->(evidence)
        OPTIONAL MATCH (entity:Entity {{org_id: $org_id}})-[:CITED_BY]->(evidence)
        WHERE entity IS NULL OR {_knowledge_scope('entity')}
        WITH
            evidence.reference AS reference,
            evidence.source AS source,
            head([value IN collect(DISTINCT coalesce(document.id, evidence.document_id)) WHERE value IS NOT NULL]) AS document_id,
            head([value IN collect(DISTINCT coalesce(document.title, evidence.title)) WHERE value IS NOT NULL]) AS title,
            head([value IN collect(DISTINCT coalesce(document.url, evidence.url)) WHERE value IS NOT NULL]) AS url,
            head([value IN collect(DISTINCT coalesce(document.author, evidence.author)) WHERE value IS NOT NULL]) AS author,
            head([value IN collect(DISTINCT coalesce(document.kind, evidence.kind)) WHERE value IS NOT NULL]) AS kind,
            head([value IN collect(DISTINCT coalesce(document.content_hash, evidence.content_hash)) WHERE value IS NOT NULL]) AS content_hash,
            head([value IN collect(DISTINCT coalesce(document.family_key, evidence.family_key)) WHERE value IS NOT NULL]) AS family_key,
            head([value IN collect(DISTINCT coalesce(document.department_id, evidence.department_id)) WHERE value IS NOT NULL]) AS department_id,
            max(coalesce(document.source_date, evidence.source_date)) AS source_date,
            collect(DISTINCT CASE WHEN entity IS NULL THEN null ELSE entity{{
                .id, .entity_type, .statement, .status, .confidence
            }} END) AS claims
        RETURN reference, document_id, title, source, url, author, kind,
               content_hash, family_key, department_id,
               toString(source_date) AS source_date, claims
        ORDER BY source_date DESC
        """,
        _scoped_params(org_id, user),
    )

    documents = []
    for row in rows:
        reference = row.get("reference")
        if not reference:
            continue
        source = str(row.get("source") or "unknown")
        title = row.get("title") or _document_title(reference)
        document_id = row.get("document_id") or (
            "legacy-" + hashlib.sha256(
                f"{org_id}\0{source}\0{reference}".encode("utf-8")
            ).hexdigest()[:24]
        )
        claims = [
            claim for claim in (row.get("claims") or [])
            if claim and claim.get("id") and claim.get("statement")
        ]
        documents.append({
            "id": document_id,
            "title": title,
            "source": source,
            "reference": reference,
            "url": row.get("url"),
            "author": row.get("author"),
            "kind": row.get("kind"),
            "content_hash": row.get("content_hash"),
            "family_key": row.get("family_key") or normalize_document_title(title, reference),
            "department_id": row.get("department_id"),
            "source_date": row.get("source_date"),
            "claims": claims,
            "is_demo": False,
        })

    workspace_families = build_document_families(documents)
    demo_families = (
        build_document_families(demo_document_versions()) if include_demo else []
    )
    families = demo_families + workspace_families
    normalized_query = " ".join(query.casefold().split())
    matching_families = [
        family
        for family in families
        if (scope == "all"
            or (scope == "example" and family["is_demo"])
            or (scope == "workspace" and not family["is_demo"]))
        and (
            not normalized_query
            or any(
                normalized_query in str(value).casefold()
                for value in [
                    family.get("title", ""),
                    *(family.get("contributors") or []),
                    *(family.get("sources") or []),
                ]
            )
        )
    ]
    page = matching_families[offset:offset + limit]
    conflicts = sum(
        family["diff"]["counts"]["conflicts"]
        for family in workspace_families
    )
    return {
        "families": page,
        "total": len(matching_families),
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(page) < len(matching_families),
        "stats": {
            "workspace_families": len(workspace_families),
            "workspace_versions": len(documents),
            "contributors": len({
                document["author"] for document in documents if document.get("author")
            }),
            "unresolved_conflicts": conflicts,
        },
        "methodology": {
            "identity": "SHA-256 content identity",
            "lineage": "W3C PROV-style revision and attribution",
            "matching": "normalized titles + ontology-aligned graph claims",
            "truth": "latest candidate with evidence, never an unqualified truth claim",
        },
    }


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
    await GraphClient.run_query(
        """
        MATCH (document:DocumentVersion {org_id: $org_id})
        WHERE NOT (document)-[:HAS_EVIDENCE]->(:Evidence)
        DETACH DELETE document
        """,
        {"org_id": org_id},
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

            await GraphClient.run_query(
                """
                MATCH (document:DocumentVersion {org_id: $org_id})
                WHERE NOT (document)-[:HAS_EVIDENCE]->(:Evidence)
                DETACH DELETE document
                """,
                {"org_id": org_id},
            )

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
        elif source["type"] == "slack":
            result = await sync_slack_source(org_id, source)
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
    failed_pages = []

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
            page_id = str(page.get("id") or "unknown")
            print(f"[Notion Sync] Error for {page_id}: {type(e).__name__}")
            return {
                "success": False,
                "entities": 0,
                "relationships": 0,
                "page_id": page_id,
                "error": str(e),
            }

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
            else:
                failed_pages.append({
                    "page_id": r["page_id"],
                    "error": r["error"],
                })

    print(f"[Notion Sync] Complete: {pages_processed} pages, {total_entities} entities, {total_relationships} relationships")

    return {
        "status": "partial" if failed_pages else "complete",
        "items_processed": pages_processed,
        "entities_created": total_entities,
        "relationships_created": total_relationships,
        "items_failed": len(failed_pages),
        "failed_pages": failed_pages,
    }


async def sync_slack_source(org_id: str, source: dict) -> dict:
    """Sync explicitly selected Slack channels through the extraction pipeline."""
    from integrations.slack import SlackApiError, fetch_slack_threads

    config = source.get("config", {})
    token = str(config.get("token") or "")
    channel_ids = config.get("watched_channels") or []
    if not token:
        raise ValueError("Reconnect Slack to refresh its access token")
    if not channel_ids:
        raise ValueError("Choose at least one Slack channel before syncing")

    try:
        source_items = await fetch_slack_threads(
            org_id,
            access_token=token,
            channel_ids=channel_ids,
            channel_names=config.get("channel_names") or {},
            department_id=source.get("departmentId"),
        )
    except SlackApiError as error:
        raise ValueError(str(error)) from error

    settings = await get_org_settings(org_id)
    auto_confirm = settings.get("auto_confirm", True)
    batch_size = settings.get("parallel_batch_size", 5)
    total_entities = 0
    total_relationships = 0
    items_processed = 0
    errors: list[str] = []

    async def process_thread(source_item):
        try:
            result = await run_extraction(
                source_item,
                auto_confirm=auto_confirm,
            )
            return result, None
        except Exception as error:  # keep one bad thread from aborting the sync
            return None, f"{source_item.title}: {error}"

    for index in range(0, len(source_items), batch_size):
        batch = source_items[index:index + batch_size]
        results = await asyncio.gather(
            *(process_thread(source_item) for source_item in batch)
        )
        for result, error in results:
            if error:
                errors.append(error)
                continue
            items_processed += 1
            total_entities += result.get("entities_created", 0)
            total_relationships += result.get("relationships_created", 0)

    return {
        "status": "complete" if not errors else "partial",
        "items_processed": items_processed,
        "entities_created": total_entities,
        "relationships_created": total_relationships,
        "errors": errors[:10],
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
        "reused_existing_extraction": result.get("reused_existing_extraction", False),
        "reused_from_document_id": result.get("reused_from_document_id"),
        "document_id": result.get("document_id"),
        "provenance_created": result.get("provenance_created", True),
    }


UPLOAD_EXTENSIONS = {".md", ".markdown", ".txt", ".yaml", ".yml"}
MAX_UPLOAD_FILES = 20
MAX_UPLOAD_BYTES = 1024 * 1024


def _uploaded_document_date(content: str) -> datetime:
    """Use an ISO date from Markdown front matter when one is available."""
    if not content.startswith("---"):
        return datetime.utcnow()
    match = re.search(
        r"(?m)^date:\s*[\"']?(\d{4}-\d{2}-\d{2})(?:[T ][^\"'\\n]+)?[\"']?\s*$",
        content[:3000],
    )
    if not match:
        return datetime.utcnow()
    try:
        return datetime.fromisoformat(match.group(1))
    except ValueError:
        return datetime.utcnow()


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
            author=user.get("name") or user.get("email"),
            url=f"upload://{filename}",
            reference=f"upload:{filename}:{digest[:12]}",
            source_date=_uploaded_document_date(content),
        )
        try:
            extraction = await run_extraction(source_item, auto_confirm=auto_confirm)
            created = extraction["entities_created"]
            total_entities += created
            reused = extraction.get("reused_existing_extraction", False)
            results.append({
                "filename": filename,
                "status": "reused" if reused else "processed",
                "entities_created": created,
                "entities_reused": len(extraction.get("entity_ids", [])) if reused else 0,
                "entity_ids": extraction["entity_ids"],
                "reused_from_document_id": extraction.get("reused_from_document_id"),
                "document_id": extraction.get("document_id"),
                "provenance_created": extraction.get("provenance_created", True),
            })
        except Exception as error:
            results.append({
                "filename": filename,
                "status": "error",
                "error": str(error),
            })

    processed = sum(item["status"] in {"processed", "reused"} for item in results)
    new_documents = sum(
        item["status"] in {"processed", "reused"}
        and item.get("provenance_created", True)
        for item in results
    )
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
            item_count=source.get("itemCount", 0) + new_documents,
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
    entity_types: Optional[str] = Query(None, description="Comma-separated entity types to filter"),
    status: str = Query("all", description="all, confirmed, or proposed"),
    query: Optional[str] = Query(None, max_length=160, description="Search entity text"),
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
    normalized_status = status.strip().lower()
    if normalized_status not in {"all", "confirmed", "proposed"}:
        raise HTTPException(
            status_code=400,
            detail="status must be one of: all, confirmed, proposed",
        )
    normalized_query = (query or "").strip().lower()

    # Get nodes
    nodes_query = f"""
    MATCH (e:Entity {{org_id: $org_id}})
    WHERE e.status IN ['proposed', 'confirmed']
      AND (size($entity_types) = 0 OR e.entity_type IN $entity_types)
      AND ($status = 'all' OR e.status = $status)
      AND (
        $query = ''
        OR toLower(coalesce(e.name, '')) CONTAINS $query
        OR toLower(coalesce(e.statement, '')) CONTAINS $query
        OR toLower(coalesce(e.detail, '')) CONTAINS $query
      )
      AND {_knowledge_scope('e')}
    CALL {{
      WITH e
      OPTIONAL MATCH (e)-[relationship]-(neighbor:Entity {{org_id: $org_id}})
      WHERE NOT type(relationship) = 'CITED_BY'
      RETURN count(DISTINCT neighbor) AS degree
    }}
    CALL {{
      WITH e
      OPTIONAL MATCH (e)-[:CITED_BY]->(evidence:Evidence {{org_id: $org_id}})
      RETURN count(DISTINCT evidence) AS evidence_count
    }}
    RETURN
        e.id as id,
        coalesce(e.name, e.statement) as name,
        e.entity_type as type,
        e.detail as description,
        e.status as status,
        e.confidence as confidence,
        degree,
        evidence_count
    ORDER BY degree DESC, e.created_at DESC
    LIMIT $limit
    """

    nodes = await GraphClient.run_query(
        nodes_query,
        _scoped_params(
            org_id,
            user,
            limit=limit,
            entity_types=types,
            status=normalized_status,
            query=normalized_query,
        ),
    )
    total_rows = await GraphClient.run_query(
        f"""
        MATCH (e:Entity {{org_id: $org_id}})
        WHERE e.status IN ['proposed', 'confirmed']
          AND (size($entity_types) = 0 OR e.entity_type IN $entity_types)
          AND ($status = 'all' OR e.status = $status)
          AND (
            $query = ''
            OR toLower(coalesce(e.name, '')) CONTAINS $query
            OR toLower(coalesce(e.statement, '')) CONTAINS $query
            OR toLower(coalesce(e.detail, '')) CONTAINS $query
          )
          AND {_knowledge_scope('e')}
        RETURN count(e) AS total
        """,
        _scoped_params(
            org_id,
            user,
            entity_types=types,
            status=normalized_status,
            query=normalized_query,
        ),
    )
    total = int(total_rows[0]["total"]) if total_rows else 0

    # Get all node IDs for edge filtering
    node_ids = [n["id"] for n in nodes]

    if not node_ids:
        return {
            "nodes": [],
            "edges": [],
            "total": total,
            "limit": limit,
            "truncated": False,
        }

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
        "edges": edges,
        "total": total,
        "limit": limit,
        "truncated": total > len(nodes),
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


class ArtifactGenerateRequest(BaseModel):
    artifact_type: Literal["presentation", "briefing", "summary"]
    topic: str = Field(min_length=3, max_length=500)
    audience: str = Field(default="Leadership team", min_length=1, max_length=120)
    instructions: str = Field(default="", max_length=1200)
    language: Literal["english", "german"] = "english"


class WorkroomCreateRequest(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    objective: str = Field(min_length=5, max_length=2000)
    department_ids: List[str] = Field(default_factory=list, max_length=12)
    visibility: Literal["organization", "departments", "private"] = "organization"


class WorkroomSettingsRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=2, max_length=160)
    objective: Optional[str] = Field(default=None, min_length=5, max_length=2000)
    visibility: Optional[Literal["organization", "departments", "private"]] = None
    department_ids: Optional[List[str]] = Field(default=None, max_length=12)


class WorkroomMemberAddRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=36)
    room_role: Literal["owner", "editor", "approver", "viewer"] = "viewer"


class WorkroomMemberRoleRequest(BaseModel):
    room_role: Literal["owner", "editor", "approver", "viewer"]


class WorkroomPlanGenerateRequest(BaseModel):
    guidance: str = Field(default="", max_length=1200)


class WorkroomPlanTaskInput(BaseModel):
    client_key: str = Field(min_length=1, max_length=60)
    title: str = Field(min_length=3, max_length=180)
    description: str = Field(min_length=3, max_length=1200)
    assignee_type: Literal["agent", "human"] = "agent"
    depends_on: List[str] = Field(default_factory=list, max_length=12)
    requires_approval: bool = False


class WorkroomPlanEditRequest(BaseModel):
    summary: str = Field(min_length=3, max_length=1200)
    tasks: List[WorkroomPlanTaskInput] = Field(min_length=1, max_length=12)


class WorkroomTaskUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=2, max_length=180)
    description: Optional[str] = Field(default=None, max_length=2000)
    status: Optional[Literal["todo", "in_progress", "completed", "blocked"]] = None
    assignee_type: Optional[Literal["agent", "human"]] = None
    assignee_user_id: Optional[str] = Field(default=None, max_length=36)
    requires_approval: Optional[bool] = None
    depends_on: Optional[List[str]] = Field(default=None, max_length=12)


class WorkroomTaskReorderRequest(BaseModel):
    task_ids: List[str] = Field(min_length=1, max_length=60)


class WorkroomMessageReference(BaseModel):
    kind: Literal["task", "run", "source", "artifact"]
    id: str = Field(min_length=1, max_length=120)
    label: str = Field(default="", max_length=200)


class WorkroomMessageCreateRequest(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    reply_to_message_id: Optional[str] = Field(default=None, max_length=36)
    references: List[WorkroomMessageReference] = Field(
        default_factory=list, max_length=8
    )
    mentions: List[str] = Field(default_factory=list, max_length=12)


class WorkroomMessageEditRequest(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class WorkroomContextItemRequest(BaseModel):
    item_kind: Literal["source", "entity"]
    reference_id: str = Field(min_length=1, max_length=120)
    mode: Literal["include", "exclude"] = "include"
    label: Optional[str] = Field(default=None, max_length=200)


class WorkroomTaskCreateRequest(BaseModel):
    title: str = Field(min_length=2, max_length=180)
    description: str = Field(default="", max_length=2000)
    assignee_type: Literal["agent", "human"] = "agent"
    assignee_name: str = Field(default="Komponist Analyst", min_length=1, max_length=120)


class WorkroomRunStartRequest(BaseModel):
    task_id: Optional[str] = None
    instruction: str = Field(default="", max_length=2400)


class WorkroomRedirectRequest(BaseModel):
    instruction: str = Field(min_length=3, max_length=2400)


class WorkroomApprovalRequest(BaseModel):
    approved: bool


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


def _fallback_chat_plan(
    message: str,
    broad: bool = False,
    history: Optional[List[ChatMessage]] = None,
) -> dict:
    """Build a conservative retrieval plan when no model planner is available."""
    normalized = message.casefold()
    aliases = {
        "Decision": (
            "decision", "decisions", "choice", "choices", "entscheidung",
            "entscheidungen",
        ),
        "Goal": (
            "goal", "goals", "objective", "objectives", "target", "targets",
            "aim", "aims", "ziel", "ziele", "zielen",
        ),
        "Constraint": (
            "constraint", "constraints", "requirement", "requirements", "rule",
            "rules", "boundary", "boundaries", "vorgabe", "vorgaben",
            "anforderung", "anforderungen",
        ),
        "Project": (
            "project", "projects", "initiative", "initiatives", "pilot", "pilots",
            "program", "programs", "projekt", "projekte", "projekten",
        ),
    }
    entity_types = [
        entity_type
        for entity_type, words in aliases.items()
        if any(re.search(rf"\b{re.escape(word)}\b", normalized) for word in words)
    ]
    asks_count = bool(re.search(
        r"\b(how many|total number|number of|count|wie viele|anzahl)\b",
        normalized,
    ))
    source_words = bool(re.search(
        r"\b(source|sources|document|documents|file|files|page|pages|quelle|quellen|dokument|dokumente)\b",
        normalized,
    ))
    if source_words and re.search(r"\b(most|fewest|per|by|meisten|wenigsten|pro|nach)\b", normalized):
        asks_count = True
    asks_all = bool(re.search(
        r"\b(list|every|all|complete|entire|liste|alle|sämtliche|vollständig)\b",
        normalized,
    ))

    if asks_count:
        operation = "count"
    elif asks_all:
        operation = "list"
    elif broad:
        operation = "overview"
    else:
        operation = "search"

    group_by = "none"
    if operation == "count":
        if source_words:
            group_by = "source"
        elif len(entity_types) != 1:
            group_by = "entity_type"

    history_context = _chat_history_text(history or [])
    query = "" if operation in {"count", "list", "overview"} else (
        f"{history_context}\n{message}" if history else message
    )
    return {
        "operation": operation,
        "query": query,
        "entity_types": entity_types,
        "group_by": group_by,
        "sort": "relevance",
        "limit": 100 if operation in {"list", "count", "overview"} else 12,
        "language": "german" if _answer_in_german(message) else "english",
        "expand_graph": bool(re.search(
            r"\b(related|relationship|relationships|depends|dependency|impact|connected|"
            r"zusammenhang|abhängig|abhängigkeit|auswirkung|verbunden)\b",
            normalized,
        )),
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
               coalesce(n.department_ids, []) AS department_ids,
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
               coalesce(n.department_ids, []) AS department_ids,
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
        WHERE coalesce(relationship.status, 'confirmed') = 'confirmed'
          AND NOT neighbor.id IN $seed_ids AND {_knowledge_scope('neighbor')}
        RETURN DISTINCT neighbor.id AS id,
               neighbor.entity_type AS entity_type,
               neighbor.statement AS statement,
               neighbor.detail AS detail,
               neighbor.status AS status,
               neighbor.confidence AS confidence,
               coalesce(neighbor.department_ids, []) AS department_ids,
               neighbor.confirmed_at AS confirmed_at,
               neighbor.created_at AS created_at,
               type(relationship) AS relationship_type,
               seed.id AS related_seed_id,
               0.0 AS score
        ORDER BY confirmed_at DESC, created_at DESC
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
               collect(DISTINCT evidence{{.id, .source, .reference, .title,
                                          .url, .excerpt, .source_date,
                                          .document_id, .kind,
                                          page: evidence[$page_property],
                                          line_start: evidence[$line_start_property],
                                          line_end: evidence[$line_end_property],
                                          .department_id}}) AS evidence
        """,
        _scoped_params(
            org_id,
            user,
            entity_ids=[entity["id"] for entity in entities],
            page_property="page",
            line_start_property="line_start",
            line_end_property="line_end",
        ),
    )
    evidence_by_entity = {
        row["entity_id"]: [item for item in row["evidence"] if item.get("id")]
        for row in rows
    }
    for entity in entities:
        entity["evidence"] = evidence_by_entity.get(entity["id"], [])


_RETRIEVAL_STOPWORDS = {
    "a", "an", "and", "are", "be", "for", "from", "how", "in", "is", "of",
    "on", "or", "the", "to", "what", "when", "where", "which", "who", "why",
    "wie", "was", "wer", "wo", "wann", "warum", "der", "die", "das", "den",
    "dem", "des", "ein", "eine", "einer", "einem", "einen", "und", "oder",
}


def _rerank_chat_results(
    query: str, results: List[dict], limit: int
) -> List[dict]:
    """Combine semantic rank with grounded lexical evidence coverage."""
    query_terms = {
        token for token in re.findall(r"[a-z0-9äöüß]+", query.casefold())
        if len(token) > 1 and token not in _RETRIEVAL_STOPWORDS
    }
    reranked = []
    for index, result in enumerate(results):
        evidence_text = " ".join(
            str(item.get("excerpt") or "") for item in result.get("evidence", [])
        )
        haystack = " ".join(filter(None, [
            str(result.get("statement") or ""),
            str(result.get("detail") or ""),
            evidence_text,
        ])).casefold()
        haystack_terms = set(re.findall(r"[a-z0-9äöüß]+", haystack))
        lexical_coverage = (
            len(query_terms & haystack_terms) / len(query_terms)
            if query_terms else 0.0
        )
        vector_score = float(result.get("vector_score") or 0.0)
        text_score = float(result.get("text_score") or 0.0)
        fused_score = float(result.get("score") or 0.0)
        # Vector similarity carries paraphrases; evidence overlap rewards precise
        # answers. The tiny position term makes ties deterministic.
        result["retrieval_score"] = (
            lexical_coverage * 0.55
            + max(0.0, vector_score) * 0.35
            + min(max(text_score, fused_score), 1.0) * 0.10
            - index * 0.000001
        )
        reranked.append(result)
    reranked.sort(key=lambda item: item["retrieval_score"], reverse=True)
    return reranked[:limit]


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
                "title": evidence.get("title"),
                "url": evidence.get("url"),
                "excerpt": evidence.get("excerpt"),
                "source_date": source_date,
                "document_id": evidence.get("document_id"),
                "document_kind": evidence.get("kind"),
                "page": evidence.get("page"),
                "line_start": evidence.get("line_start"),
                "line_end": evidence.get("line_end"),
                "department_id": evidence.get("department_id"),
                "department_ids": result.get("department_ids") or [],
            })
            citation_numbers.append(str(len(sources)))
            evidence_lines.append(
                f"Source [{len(sources)}]: {sources[-1]['source']} — "
                f"{sources[-1]['reference']}\n"
                f"Verbatim evidence [{len(sources)}]: "
                f"{sources[-1]['excerpt'] or 'No excerpt available'}"
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
    request: Request,
    org_id: str = Query(...),
    query: str = Query("", max_length=120),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    user = await _authorized_org_user(request, org_id)
    conversations, total = await list_chat_conversations(
        org_id,
        user["id"],
        query=" ".join(query.split()),
        limit=limit,
        offset=offset,
    )
    return {
        "conversations": conversations,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(conversations) < total,
    }


@app.get("/chat/conversations/{conversation_id}")
async def get_chat_conversation_history(
    conversation_id: str,
    request: Request,
    org_id: str = Query(...),
    before: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=200),
):
    user = await _authorized_org_user(request, org_id)
    conversation = await get_chat_conversation(
        org_id,
        user["id"],
        conversation_id,
        before_id=before,
        message_limit=limit,
    )
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


def _artifact_scope(user: dict) -> tuple[list[str], bool]:
    return (
        user.get("department_ids") or [],
        bool(user.get("access_all_departments")),
    )


async def _artifact_context(
    org_id: str, user: dict, topic: str
) -> tuple[list[dict], list[dict]]:
    """Retrieve only confirmed, visible, cited knowledge for a deliverable."""
    broad_topic = bool(re.search(
        r"\b(all|company|overview|everything|entire|gesamte|überblick|alles)\b",
        topic.casefold(),
    ))
    selected: list[dict] = []
    if not broad_topic:
        selected = await _literal_chat_search(org_id, user, topic, k=24)
        if selected:
            neighbors = await _expand_chat_graph_context(
                org_id, user, selected, limit=max(0, 24 - len(selected))
            )
            by_id = {entity["id"]: entity for entity in selected}
            for neighbor in neighbors:
                by_id.setdefault(neighbor["id"], neighbor)
            selected = list(by_id.values())[:24]

    if not selected:
        selected = await _browse_chat_entities(
            org_id, user, [], limit=24, sort="newest"
        )

    await _attach_chat_evidence(org_id, user, selected)
    selected = [entity for entity in selected if entity.get("evidence")]
    _, raw_sources = _chat_context_and_sources(selected)
    sources: list[dict] = []
    seen_evidence = set()
    for source in raw_sources:
        if source["id"] in seen_evidence:
            continue
        seen_evidence.add(source["id"])
        sources.append(source)
    return selected, sources


async def _create_grounded_artifact(
    *,
    org_id: str,
    user: dict,
    artifact_type: Literal["presentation", "briefing", "summary"],
    topic: str,
    audience: str,
    instructions: str,
    language: Literal["english", "german"],
) -> dict:
    """Create one cited deliverable for browser and Workroom callers alike."""
    entities, sources = await _artifact_context(org_id, user, topic)
    if not entities or not sources:
        raise HTTPException(
            status_code=400,
            detail=(
                "No confirmed, cited knowledge is available for this topic. "
                "Review at least one extracted item before generating a deliverable."
            ),
        )

    fallback = mock_artifact_content(
        artifact_type,
        topic,
        audience,
        language,
        entities,
    )
    content = fallback
    if os.getenv("KOMPONIST_AI_MODE", "live").lower() != "mock":
        prompt, system = generation_prompt(
            artifact_type,
            topic,
            audience,
            instructions,
            language,
            entities,
        )
        try:
            candidate = await get_llm().call_json(
                prompt=prompt,
                system=system,
                max_tokens=8000,
                schema=ARTIFACT_SCHEMA,
            )
            content = sanitize_artifact_content(candidate, fallback, entities)
        except Exception as generation_error:
            print(f"Artifact generation fell back to grounded template: {generation_error}")

    source_entity_ids = list(dict.fromkeys(
        entity["id"] for entity in entities if entity.get("evidence")
    ))
    for source in sources:
        source["komponist_path"] = source_deep_link_path(org_id, source["id"])
    department_ids = sorted({
        department_id
        for entity in entities
        for department_id in (entity.get("department_ids") or [])
        if department_id
    } | {
        str(source["department_id"])
        for source in sources
        if source.get("department_id")
    })
    return await create_generated_artifact(
        org_id=org_id,
        user_id=user["id"],
        artifact_type=artifact_type,
        title=content["title"],
        topic=topic,
        audience=audience,
        language=language,
        content=content,
        sources=sources,
        source_entity_ids=source_entity_ids,
        department_ids=department_ids,
    )


@app.post("/artifacts/generate", status_code=201)
async def generate_artifact(
    payload: ArtifactGenerateRequest,
    request: Request,
    org_id: str = Query(...),
):
    """Generate a private, cited deliverable from the caller's visible graph."""
    user = await _authorized_org_user(request, org_id)
    return await _create_grounded_artifact(
        org_id=org_id,
        artifact_type=payload.artifact_type,
        user=user,
        topic=payload.topic,
        audience=payload.audience,
        instructions=payload.instructions,
        language=payload.language,
    )


@app.get("/artifacts")
async def get_artifacts(
    request: Request,
    org_id: str = Query(...),
    query: str = Query("", max_length=160),
    limit: int = Query(24, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    user = await _authorized_org_user(request, org_id)
    department_ids, access_all = _artifact_scope(user)
    artifacts, total = await list_generated_artifacts(
        org_id,
        user["id"],
        department_ids,
        access_all,
        query=" ".join(query.split()),
        limit=limit,
        offset=offset,
    )
    return {
        "artifacts": artifacts,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(artifacts) < total,
    }


async def _readable_artifact(
    request: Request,
    org_id: str,
    artifact_id: str,
    *,
    permission: str = "view",
) -> tuple[dict, dict, Optional[dict]]:
    """Resolve a deliverable the caller may read, privately or via a room.

    Ownership is checked first so private deliverables keep working exactly
    as before. Only if that fails does Workroom sharing apply.
    """
    user = await _authorized_org_user(request, org_id)
    department_ids, access_all = _artifact_scope(user)
    owned = await get_generated_artifact(
        org_id, user["id"], artifact_id, department_ids, access_all
    )
    if owned is not None:
        return user, owned, None

    grant = await resolve_artifact_room_access(
        org_id=org_id, artifact_id=artifact_id, user=user, permission=permission
    )
    if grant is None:
        raise HTTPException(status_code=404, detail="Deliverable not found")

    record = await get_org_artifact(org_id, artifact_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Deliverable not found")
    return user, artifact_record_dict(record), grant


@app.get("/artifacts/{artifact_id}")
async def get_artifact(
    artifact_id: str, request: Request, org_id: str = Query(...)
):
    user, artifact, grant = await _readable_artifact(request, org_id, artifact_id)
    return {
        **artifact,
        "shared_with_workrooms": await artifact_sharing(org_id, artifact_id),
        "access_via_workroom": grant,
    }


@app.get("/artifacts/{artifact_id}/download")
async def download_artifact(
    artifact_id: str,
    request: Request,
    org_id: str = Query(...),
    export_format: Optional[Literal["pptx", "pdf", "markdown"]] = Query(
        None, alias="format"
    ),
):
    # A room viewer may download what they are allowed to read.
    _, artifact, _ = await _readable_artifact(request, org_id, artifact_id)

    selected_format = export_format or (
        "pptx" if artifact["artifact_type"] == "presentation" else "markdown"
    )
    if selected_format == "pptx" and artifact["artifact_type"] != "presentation":
        raise HTTPException(
            status_code=400,
            detail="PowerPoint is available for presentations only",
        )

    filename = artifact_filename(artifact, selected_format)
    if selected_format == "pptx":
        try:
            content = artifact_pptx(artifact)
        except ImportError as error:
            raise HTTPException(
                status_code=503,
                detail="PowerPoint export is not installed on this server",
            ) from error
        media_type = (
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        )
    elif selected_format == "pdf":
        try:
            content = artifact_pdf(artifact)
        except ImportError as error:
            raise HTTPException(
                status_code=503,
                detail="PDF export is not installed on this server",
            ) from error
        media_type = "application/pdf"
    else:
        content = artifact_markdown(artifact).encode("utf-8")
        media_type = "text/markdown; charset=utf-8"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.delete("/artifacts/{artifact_id}", status_code=204)
async def remove_artifact(
    artifact_id: str, request: Request, org_id: str = Query(...)
):
    user = await _authorized_org_user(request, org_id)
    if not await delete_generated_artifact(org_id, user["id"], artifact_id):
        raise HTTPException(status_code=404, detail="Deliverable not found")
    return Response(status_code=204)


async def _authorized_workroom(
    request: Request,
    org_id: str,
    room_id: str,
    *,
    permission: str = "view",
    allow_archived: bool = False,
) -> tuple[dict, Any, str]:
    """Resolve the caller's room role and enforce one room permission.

    A caller who cannot see the room gets 404 rather than 403, so a private
    room's existence is not disclosed. A caller who can see it but lacks the
    permission gets 403.
    """
    user = await _authorized_org_user(request, org_id)
    room = await get_room_record(org_id, room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Workroom not found")

    membership = await get_workroom_membership(room_id, user["id"])
    role = effective_room_role(
        room,
        membership,
        department_ids=user.get("department_ids") or [],
        access_all=bool(user.get("access_all_departments")),
        org_role=user.get("role", "member"),
    )
    if role is None:
        raise HTTPException(status_code=404, detail="Workroom not found")
    if not room_can(role, permission):
        raise HTTPException(
            status_code=403,
            detail=f"Your role in this Workroom cannot {permission} here",
        )
    if (
        not allow_archived
        and room.status == "archived"
        and permission != "view"
    ):
        raise HTTPException(
            status_code=409,
            detail="This Workroom is archived. Reopen it before making changes.",
        )
    return user, room, role


def _workroom_scoped_user(user: dict, room: Any) -> dict:
    """Compile room context, never the owner's unrestricted context."""
    return {
        **user,
        "access_all_departments": False,
        "department_ids": room.department_ids or [],
    }


@app.get("/workrooms")
async def get_workrooms(
    request: Request,
    org_id: str = Query(...),
    include_archived: bool = Query(False),
    limit: int = Query(24, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    user = await _authorized_org_user(request, org_id)
    rooms, total = await load_workrooms(
        org_id,
        user.get("department_ids") or [],
        bool(user.get("access_all_departments")),
        user_id=user["id"],
        org_role=user.get("role", "member"),
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return {
        "workrooms": rooms,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(rooms) < total,
    }


@app.post("/workrooms", status_code=201)
async def add_workroom(
    payload: WorkroomCreateRequest,
    request: Request,
    org_id: str = Query(...),
):
    user = await _authorized_org_user(request, org_id, write=True)
    department_ids: list[str] = []
    for department_id in dict.fromkeys(payload.department_ids):
        validated = await _validate_department_scope(org_id, user, department_id)
        if validated:
            department_ids.append(validated)
    if payload.visibility == "departments" and not department_ids:
        raise HTTPException(
            status_code=400,
            detail="Choose at least one department for a department-scoped Workroom",
        )
    return await create_workroom(
        org_id=org_id,
        user_id=user["id"],
        user_name=user["name"],
        title=" ".join(payload.title.split()),
        objective=" ".join(payload.objective.split()),
        department_ids=department_ids,
        visibility=payload.visibility,
    )


@app.get("/workrooms/{room_id}")
async def get_workroom(
    room_id: str, request: Request, org_id: str = Query(...)
):
    user, _, _ = await _authorized_workroom(request, org_id, room_id)
    room = await load_workroom(
        org_id,
        room_id,
        user.get("department_ids") or [],
        bool(user.get("access_all_departments")),
        user_id=user["id"],
        org_role=user.get("role", "member"),
    )
    if room is None:
        raise HTTPException(status_code=404, detail="Workroom not found")
    return room


@app.get("/workrooms/{room_id}/members")
async def get_workroom_members(
    room_id: str, request: Request, org_id: str = Query(...)
):
    await _authorized_workroom(request, org_id, room_id)
    members = await list_workroom_members(org_id, room_id)
    return {"members": members, "total": len(members)}


@app.post("/workrooms/{room_id}/members", status_code=201)
async def add_workroom_participant(
    room_id: str,
    payload: WorkroomMemberAddRequest,
    request: Request,
    org_id: str = Query(...),
):
    """Add an existing organization member to this Workroom.

    Room membership never grants knowledge the person could not already read:
    the agent's context stays bounded by the room's own scope.
    """
    user, _, _ = await _authorized_workroom(
        request, org_id, room_id, permission="manage"
    )
    invitee = await get_org_member(org_id, payload.user_id)
    if invitee is None:
        raise HTTPException(
            status_code=400,
            detail="That person is not an active member of this organization",
        )
    member = await add_workroom_member(
        org_id=org_id,
        room_id=room_id,
        user_id=payload.user_id,
        room_role=payload.room_role,
        invited_by_user_id=user["id"],
    )
    await append_workroom_event(
        org_id=org_id,
        room_id=room_id,
        actor_type="human",
        actor_name=user["name"],
        event_type="member_added",
        message=f"Added {member['name']} to the Workroom as {payload.room_role}.",
        payload={"user_id": payload.user_id, "room_role": payload.room_role},
    )
    return member


@app.patch("/workrooms/{room_id}/members/{member_user_id}")
async def change_workroom_member_role(
    room_id: str,
    member_user_id: str,
    payload: WorkroomMemberRoleRequest,
    request: Request,
    org_id: str = Query(...),
):
    user, _, _ = await _authorized_workroom(
        request, org_id, room_id, permission="manage"
    )
    # A room must keep at least one owner who can administer it.
    if payload.room_role != "owner":
        current = await get_workroom_membership(room_id, member_user_id)
        if (
            current is not None
            and current.status == "active"
            and current.room_role == "owner"
            and await count_active_owners(room_id) <= 1
        ):
            raise HTTPException(
                status_code=409,
                detail="A Workroom needs at least one owner",
            )
    member = await set_workroom_member_role(
        org_id, room_id, member_user_id, payload.room_role
    )
    if member is None:
        raise HTTPException(status_code=404, detail="Participant not found")
    await append_workroom_event(
        org_id=org_id,
        room_id=room_id,
        actor_type="human",
        actor_name=user["name"],
        event_type="member_role_changed",
        message=f"Changed {member['name']}'s room role to {payload.room_role}.",
        payload={"user_id": member_user_id, "room_role": payload.room_role},
    )
    return member


@app.delete("/workrooms/{room_id}/members/{member_user_id}")
async def remove_workroom_participant(
    room_id: str,
    member_user_id: str,
    request: Request,
    org_id: str = Query(...),
):
    user, _, _ = await _authorized_workroom(
        request, org_id, room_id, permission="manage"
    )
    current = await get_workroom_membership(room_id, member_user_id)
    if (
        current is not None
        and current.status == "active"
        and current.room_role == "owner"
        and await count_active_owners(room_id) <= 1
    ):
        raise HTTPException(
            status_code=409, detail="A Workroom needs at least one owner"
        )
    member = await remove_workroom_member(org_id, room_id, member_user_id)
    if member is None:
        raise HTTPException(status_code=404, detail="Participant not found")
    await append_workroom_event(
        org_id=org_id,
        room_id=room_id,
        actor_type="human",
        actor_name=user["name"],
        event_type="member_removed",
        message=f"Removed {member['name']} from the Workroom.",
        payload={"user_id": member_user_id},
    )
    return member


@app.patch("/workrooms/{room_id}")
async def update_workroom(
    room_id: str,
    payload: WorkroomSettingsRequest,
    request: Request,
    org_id: str = Query(...),
):
    user, room, _ = await _authorized_workroom(
        request, org_id, room_id, permission="manage"
    )
    department_ids: Optional[list[str]] = None
    if payload.department_ids is not None:
        department_ids = []
        for department_id in dict.fromkeys(payload.department_ids):
            validated = await _validate_department_scope(org_id, user, department_id)
            if validated:
                department_ids.append(validated)

    visibility = payload.visibility
    effective_departments = (
        department_ids if department_ids is not None else (room.department_ids or [])
    )
    if (
        (visibility or room.visibility) == "departments"
        and not effective_departments
    ):
        raise HTTPException(
            status_code=400,
            detail="Choose at least one department for a department-scoped Workroom",
        )

    updated = await update_room_settings(
        org_id,
        room_id,
        title=" ".join(payload.title.split()) if payload.title else None,
        objective=(
            " ".join(payload.objective.split()) if payload.objective else None
        ),
        visibility=visibility,
        department_ids=department_ids,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Workroom not found")

    changes: list[str] = []
    if payload.title:
        changes.append("title")
    if payload.objective:
        changes.append("objective")
    if visibility:
        changes.append(f"visibility to {visibility}")
    if department_ids is not None:
        changes.append("knowledge scope")
    if changes:
        await append_workroom_event(
            org_id=org_id,
            room_id=room_id,
            actor_type="human",
            actor_name=user["name"],
            event_type="room_settings_changed",
            message=f"Updated the Workroom {', '.join(changes)}.",
            payload={
                "visibility": updated["visibility"],
                "department_ids": updated["department_ids"],
            },
        )
    return updated


@app.post("/workrooms/{room_id}/archive")
async def archive_workroom(
    room_id: str, request: Request, org_id: str = Query(...)
):
    """Archive rather than delete, so the record and its citations survive."""
    user, room, _ = await _authorized_workroom(
        request, org_id, room_id, permission="manage"
    )
    if room.status == "archived":
        raise HTTPException(status_code=409, detail="This Workroom is already archived")
    updated = await update_room_settings(org_id, room_id, status="archived")
    await append_workroom_event(
        org_id=org_id,
        room_id=room_id,
        actor_type="human",
        actor_name=user["name"],
        event_type="room_archived",
        message="Archived the Workroom.",
    )
    return updated


@app.post("/workrooms/{room_id}/reopen")
async def reopen_workroom(
    room_id: str, request: Request, org_id: str = Query(...)
):
    user, room, _ = await _authorized_workroom(
        request, org_id, room_id, permission="manage", allow_archived=True
    )
    if room.status != "archived":
        raise HTTPException(status_code=409, detail="This Workroom is not archived")
    updated = await update_room_settings(org_id, room_id, status="active")
    await append_workroom_event(
        org_id=org_id,
        room_id=room_id,
        actor_type="human",
        actor_name=user["name"],
        event_type="room_reopened",
        message="Reopened the Workroom.",
    )
    return updated


@app.post("/workrooms/{room_id}/tasks", status_code=201)
async def add_workroom_task(
    room_id: str,
    payload: WorkroomTaskCreateRequest,
    request: Request,
    org_id: str = Query(...),
):
    user, _, _ = await _authorized_workroom(
        request, org_id, room_id, permission="edit"
    )
    return await create_workroom_task(
        org_id=org_id,
        room_id=room_id,
        user_id=user["id"],
        user_name=user["name"],
        title=" ".join(payload.title.split()),
        description=" ".join(payload.description.split()),
        assignee_type=payload.assignee_type,
        assignee_name=payload.assignee_name,
    )


def _first_plan_error(error: ValidationError) -> str:
    """Turn a Pydantic failure into one sentence a person can act on."""
    problems = error.errors()
    if not problems:
        return "The plan is not valid."
    first = problems[0]
    location = ".".join(str(part) for part in first.get("loc", ()) if part != "tasks")
    message = first.get("msg", "is not valid")
    message = message.removeprefix("Value error, ")
    return f"{location or 'plan'}: {message}"


async def _room_context_lines(org_id: str, user: dict, room: Any) -> list[str]:
    """Confirmed statements inside the room's scope, for grounding a plan."""
    scoped_user = _workroom_scoped_user(user, room)
    try:
        entities, _ = await _artifact_context(org_id, scoped_user, room.objective)
    except Exception:  # noqa: BLE001 - planning still works without context
        return []
    lines: list[str] = []
    for entity in entities[:24]:
        statement = entity.get("statement") or entity.get("detail")
        if statement:
            lines.append(f"{entity.get('entity_type') or 'Fact'}: {statement}")
    return lines


@app.get("/workrooms/{room_id}/deliverables")
async def get_workroom_deliverables(
    room_id: str, request: Request, org_id: str = Query(...)
):
    """Deliverables shared with this room, readable by every participant."""
    await _authorized_workroom(request, org_id, room_id)
    deliverables = await list_room_artifacts(org_id, room_id)
    return {"deliverables": deliverables, "total": len(deliverables)}


@app.delete("/workrooms/{room_id}/deliverables/{artifact_id}")
async def withdraw_workroom_deliverable(
    room_id: str, artifact_id: str, request: Request, org_id: str = Query(...)
):
    """Withdraw a deliverable from the room. The artifact itself survives."""
    user, _, _ = await _authorized_workroom(
        request, org_id, room_id, permission="manage"
    )
    link = await unshare_artifact(org_id, room_id, artifact_id)
    if link is None:
        raise HTTPException(status_code=404, detail="Shared deliverable not found")
    await append_workroom_event(
        org_id=org_id,
        room_id=room_id,
        actor_type="human",
        actor_name=user["name"],
        event_type="deliverable_withdrawn",
        message="Withdrew a shared deliverable from the Workroom.",
        payload={"artifact_id": artifact_id},
    )
    return link


@app.get("/workrooms/{room_id}/messages")
async def get_workroom_messages(
    room_id: str,
    request: Request,
    org_id: str = Query(...),
    after: Optional[str] = Query(None),
    before: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=200),
):
    await _authorized_workroom(request, org_id, room_id)
    return await list_workroom_messages(
        org_id,
        room_id,
        after_id=after,
        before_id=before,
        limit=limit,
    )


@app.post("/workrooms/{room_id}/messages", status_code=201)
async def post_workroom_message(
    room_id: str,
    payload: WorkroomMessageCreateRequest,
    request: Request,
    org_id: str = Query(...),
):
    """Post to the shared conversation.

    Posting never instructs the agent. Changing what a run is doing is a
    separate, explicit redirect action.
    """
    user, _, _ = await _authorized_workroom(
        request, org_id, room_id, permission="comment"
    )
    message = await create_workroom_message(
        org_id=org_id,
        room_id=room_id,
        author_type="human",
        author_user_id=user["id"],
        author_name=user["name"],
        body=payload.body.strip(),
        reply_to_message_id=payload.reply_to_message_id,
        references=normalize_message_references(
            [reference.model_dump() for reference in payload.references]
        ),
        mentions=await resolve_message_mentions(org_id, room_id, payload.mentions),
    )
    if message is None:
        raise HTTPException(status_code=404, detail="Workroom not found")
    # Emitted so open room streams see the message without polling.
    await append_workroom_event(
        org_id=org_id,
        room_id=room_id,
        actor_type="human",
        actor_name=user["name"],
        event_type="message_posted",
        message=f"{user['name']} posted in the conversation.",
        payload={"message_id": message["id"]},
    )
    return message


@app.patch("/workrooms/{room_id}/messages/{message_id}")
async def edit_workroom_message(
    room_id: str,
    message_id: str,
    payload: WorkroomMessageEditRequest,
    request: Request,
    org_id: str = Query(...),
):
    user, _, _ = await _authorized_workroom(
        request, org_id, room_id, permission="comment"
    )
    message = await edit_workroom_message_body(
        org_id, room_id, message_id, user_id=user["id"], body=payload.body.strip()
    )
    if message is None:
        raise HTTPException(
            status_code=404, detail="No message of yours was found to edit"
        )
    return message


@app.delete("/workrooms/{room_id}/messages/{message_id}")
async def remove_workroom_message(
    room_id: str, message_id: str, request: Request, org_id: str = Query(...)
):
    user, _, role = await _authorized_workroom(
        request, org_id, room_id, permission="comment"
    )
    message = await delete_workroom_message(
        org_id,
        room_id,
        message_id,
        user_id=user["id"],
        can_manage=room_can(role, "manage"),
    )
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found")
    return message


@app.get("/workrooms/{room_id}/context")
async def get_workroom_context(
    room_id: str, request: Request, org_id: str = Query(...)
):
    """Preview exactly what the agent may read, before starting any run."""
    user, room, _ = await _authorized_workroom(request, org_id, room_id)
    scoped_user = _workroom_scoped_user(user, room)
    try:
        entities, sources = await _artifact_context(
            org_id, scoped_user, room.objective
        )
    except Exception:  # noqa: BLE001 - an empty preview beats a broken page
        entities, sources = [], []
    for source in sources:
        source["komponist_path"] = source_deep_link_path(org_id, source["id"])

    items = await list_workroom_context_items(org_id, room_id)
    return await build_context_preview(
        org_id=org_id,
        room=room,
        entities=entities,
        sources=sources,
        items=items,
        accessible_department_ids=(
            user.get("department_ids") or []
            if not user.get("access_all_departments")
            else (room.department_ids or [])
        ),
    )


@app.post("/workrooms/{room_id}/context", status_code=201)
async def add_workroom_context_item(
    room_id: str,
    payload: WorkroomContextItemRequest,
    request: Request,
    org_id: str = Query(...),
):
    """Pin or exclude a source or fact for every future run in this room."""
    user, _, _ = await _authorized_workroom(
        request, org_id, room_id, permission="edit"
    )
    item = await set_workroom_context_item(
        org_id=org_id,
        room_id=room_id,
        item_kind=payload.item_kind,
        reference_id=payload.reference_id,
        mode=payload.mode,
        label=" ".join(payload.label.split()) if payload.label else None,
        user_id=user["id"],
    )
    await append_workroom_event(
        org_id=org_id,
        room_id=room_id,
        actor_type="human",
        actor_name=user["name"],
        event_type="context_changed",
        message=(
            f"{'Pinned' if payload.mode == 'include' else 'Excluded'} a "
            f"{payload.item_kind} in the Workroom context."
        ),
        payload={
            "item_kind": payload.item_kind,
            "mode": payload.mode,
            "reference_id": payload.reference_id,
        },
    )
    return item


@app.delete("/workrooms/{room_id}/context/{item_id}")
async def delete_workroom_context_item(
    room_id: str, item_id: str, request: Request, org_id: str = Query(...)
):
    user, _, _ = await _authorized_workroom(
        request, org_id, room_id, permission="edit"
    )
    item = await remove_workroom_context_item(org_id, room_id, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Context item not found")
    await append_workroom_event(
        org_id=org_id,
        room_id=room_id,
        actor_type="human",
        actor_name=user["name"],
        event_type="context_changed",
        message="Removed a Workroom context rule.",
        payload={"item_kind": item["item_kind"], "reference_id": item["reference_id"]},
    )
    return item


@app.post("/workrooms/{room_id}/plans", status_code=201)
async def generate_workroom_plan(
    room_id: str,
    payload: WorkroomPlanGenerateRequest,
    request: Request,
    org_id: str = Query(...),
):
    """Ask the configured provider for a draft plan. A person must approve it."""
    user, room, _ = await _authorized_workroom(
        request, org_id, room_id, permission="edit"
    )
    context_lines = await _room_context_lines(org_id, user, room)
    try:
        spec, metadata = await generate_plan_spec(
            objective=room.objective,
            title=room.title,
            context_lines=context_lines,
            guidance=" ".join(payload.guidance.split()),
        )
    except PlanGenerationError as error:
        # 502 for provider trouble, 422 when the model's output was rejected.
        status = 422 if error.code in {"schema_rejected", "unreadable"} else 502
        raise HTTPException(status_code=status, detail=str(error)) from error

    version = await create_plan_version(
        org_id=org_id,
        room_id=room_id,
        spec=spec,
        provider=metadata.get("provider"),
        model=metadata.get("model"),
        usage={},
        created_by_user_id=user["id"],
    )
    await append_workroom_event(
        org_id=org_id,
        room_id=room_id,
        actor_type="agent",
        actor_name="Komponist Analyst",
        event_type="plan_generated",
        message=(
            f"Proposed plan v{version['version']} with "
            f"{len(spec.tasks)} tasks. Approval required."
        ),
        payload={"plan_id": version["id"], "version": version["version"]},
    )
    return version


@app.get("/workrooms/{room_id}/plans")
async def get_workroom_plans(
    room_id: str, request: Request, org_id: str = Query(...)
):
    await _authorized_workroom(request, org_id, room_id)
    versions = await list_plan_versions(org_id, room_id)
    current = next(
        (item for item in versions if item["status"] == "approved"), None
    )
    draft = next((item for item in versions if item["status"] == "draft"), None)
    return {"plans": versions, "current": current, "draft": draft}


@app.patch("/workrooms/{room_id}/plans/{plan_id}")
async def edit_workroom_plan(
    room_id: str,
    plan_id: str,
    payload: WorkroomPlanEditRequest,
    request: Request,
    org_id: str = Query(...),
):
    """Save human edits to a draft, held to the same rules as generated output."""
    user, _, _ = await _authorized_workroom(
        request, org_id, room_id, permission="edit"
    )
    try:
        spec = PlanSpec.model_validate(payload.model_dump())
    except ValidationError as error:
        raise HTTPException(
            status_code=422,
            detail=_first_plan_error(error),
        ) from error
    updated = await replace_draft_spec(org_id, room_id, plan_id, spec)
    if updated is None:
        raise HTTPException(
            status_code=404, detail="No editable plan draft was found"
        )
    await append_workroom_event(
        org_id=org_id,
        room_id=room_id,
        actor_type="human",
        actor_name=user["name"],
        event_type="plan_edited",
        message=f"Edited plan draft v{updated['version']}.",
        payload={"plan_id": plan_id},
    )
    return updated


@app.post("/workrooms/{room_id}/plans/{plan_id}/approval")
async def approve_workroom_plan(
    room_id: str,
    plan_id: str,
    payload: WorkroomApprovalRequest,
    request: Request,
    org_id: str = Query(...),
):
    """Approve a draft into the active plan, or reject it."""
    user, _, _ = await _authorized_workroom(
        request, org_id, room_id, permission="approve"
    )
    if not payload.approved:
        rejected = await reject_draft(org_id, room_id, plan_id)
        if rejected is None:
            raise HTTPException(
                status_code=409, detail="No editable plan draft was found"
            )
        await append_workroom_event(
            org_id=org_id,
            room_id=room_id,
            actor_type="human",
            actor_name=user["name"],
            event_type="plan_rejected",
            message=f"Rejected plan draft v{rejected['version']}.",
            payload={"plan_id": plan_id},
        )
        return rejected

    result = await approve_plan_draft(
        org_id=org_id, room_id=room_id, plan_id=plan_id, user_id=user["id"]
    )
    if result is None:
        raise HTTPException(
            status_code=409, detail="No editable plan draft was found"
        )
    approved, task_ids = result
    await append_workroom_event(
        org_id=org_id,
        room_id=room_id,
        actor_type="human",
        actor_name=user["name"],
        event_type="plan_approved",
        message=(
            f"Approved plan v{approved['version']}. "
            f"{len(task_ids)} tasks are now active."
        ),
        payload={"plan_id": plan_id, "task_ids": task_ids},
    )
    return approved


@app.patch("/workrooms/{room_id}/tasks/{task_id}")
async def update_workroom_task_details(
    room_id: str,
    task_id: str,
    payload: WorkroomTaskUpdateRequest,
    request: Request,
    org_id: str = Query(...),
):
    user, _, _ = await _authorized_workroom(
        request, org_id, room_id, permission="edit"
    )
    assignee_name: Optional[str] = None
    if payload.assignee_user_id:
        assignee = await get_org_member(org_id, payload.assignee_user_id)
        if assignee is None:
            raise HTTPException(
                status_code=400,
                detail="That person is not an active member of this organization",
            )
        assignee_name = assignee["name"]

    task = await edit_workroom_task_details(
        org_id,
        room_id,
        task_id,
        title=" ".join(payload.title.split()) if payload.title else None,
        description=(
            " ".join(payload.description.split())
            if payload.description is not None
            else None
        ),
        status=payload.status,
        assignee_type=payload.assignee_type,
        assignee_user_id=payload.assignee_user_id,
        assignee_name=assignee_name,
        requires_approval=payload.requires_approval,
        depends_on=payload.depends_on,
    )
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    await append_workroom_event(
        org_id=org_id,
        room_id=room_id,
        actor_type="human",
        actor_name=user["name"],
        event_type="task_updated",
        message=f"Updated the task “{task['title']}”.",
        payload={"task_id": task_id},
    )
    return task


@app.delete("/workrooms/{room_id}/tasks/{task_id}")
async def archive_workroom_task(
    room_id: str, task_id: str, request: Request, org_id: str = Query(...)
):
    user, _, _ = await _authorized_workroom(
        request, org_id, room_id, permission="edit"
    )
    task = await archive_workroom_task_record(org_id, room_id, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    await append_workroom_event(
        org_id=org_id,
        room_id=room_id,
        actor_type="human",
        actor_name=user["name"],
        event_type="task_archived",
        message=f"Archived the task “{task['title']}”.",
        payload={"task_id": task_id},
    )
    return task


@app.post("/workrooms/{room_id}/tasks/reorder")
async def reorder_workroom_tasks(
    room_id: str,
    payload: WorkroomTaskReorderRequest,
    request: Request,
    org_id: str = Query(...),
):
    await _authorized_workroom(request, org_id, room_id, permission="edit")
    tasks = await reorder_workroom_task_records(org_id, room_id, payload.task_ids)
    if tasks is None:
        raise HTTPException(status_code=404, detail="Workroom has no tasks")
    return {"tasks": tasks, "total": len(tasks)}


@app.get("/workrooms/{room_id}/tasks/{task_id}/runs")
async def get_workroom_task_runs(
    room_id: str, task_id: str, request: Request, org_id: str = Query(...)
):
    """Every attempt for one task, so redirect lineage stays inspectable."""
    await _authorized_workroom(request, org_id, room_id)
    runs = await list_runs_for_task(org_id, task_id)
    return {"runs": runs, "total": len(runs)}


@app.post("/workrooms/{room_id}/runs", status_code=202)
async def start_workroom_run(
    room_id: str,
    payload: WorkroomRunStartRequest,
    request: Request,
    org_id: str = Query(...),
):
    user, room, _ = await _authorized_workroom(
        request, org_id, room_id, permission="edit"
    )
    room_bundle = await load_workroom(
        org_id,
        room_id,
        user.get("department_ids") or [],
        bool(user.get("access_all_departments")),
        user_id=user["id"],
        org_role=user.get("role", "member"),
    )
    if room_bundle is None:
        raise HTTPException(status_code=404, detail="Workroom not found")
    task_id = payload.task_id
    tasks_by_id = {task["id"]: task for task in room_bundle["tasks"]}
    completed_ids = {
        task["id"] for task in room_bundle["tasks"]
        if task["status"] == "completed"
    }

    def runnable(task: dict) -> bool:
        return (
            task["status"] != "completed"
            and task["assignee_type"] == "agent"
            and all(dependency in completed_ids for dependency in task["depends_on"])
        )

    if task_id is None:
        task_id = next(
            (
                task["id"]
                for task in room_bundle["tasks"]
                if runnable(task)
            ),
            None,
        )
        if room_bundle["tasks"] and task_id is None:
            raise HTTPException(
                status_code=409,
                detail=(
                    "No agent task is ready. Complete its dependencies or assign "
                    "a runnable task to an agent first."
                ),
            )
    selected_task = tasks_by_id.get(task_id) if task_id else None
    if task_id and selected_task is None:
        raise HTTPException(status_code=404, detail="Task not found in this Workroom")
    if selected_task and selected_task["assignee_type"] != "agent":
        raise HTTPException(
            status_code=409, detail="This task is assigned to a person, not the agent"
        )
    if selected_task and selected_task["status"] == "completed":
        raise HTTPException(status_code=409, detail="This task is already complete")
    if selected_task and not runnable(selected_task):
        blocked_by = [
            tasks_by_id[dependency]["title"]
            for dependency in selected_task["depends_on"]
            if dependency in tasks_by_id and dependency not in completed_ids
        ]
        raise HTTPException(
            status_code=409,
            detail=(
                "Complete the dependencies first"
                + (f": {', '.join(blocked_by)}" if blocked_by else "")
            ),
        )
    instruction = " ".join(payload.instruction.split()).strip()
    if not instruction:
        instruction = (
            selected_task["description"]
            if selected_task and selected_task["description"]
            else room.objective
        )
    try:
        run = await create_workroom_run(
            org_id=org_id,
            room_id=room_id,
            task_id=task_id,
            user_id=user["id"],
            instruction=instruction,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    await enqueue_research(
        org_id=org_id,
        room_id=room_id,
        run_id=run["id"],
        user_id=user["id"],
        user_name=user["name"],
    )
    return run


@app.post("/workroom-runs/{run_id}/pause")
async def pause_workroom_run(
    run_id: str, request: Request, org_id: str = Query(...)
):
    """Request a pause.

    A run that has not started yet pauses immediately. A running agent cannot
    be interrupted mid model call, so it enters ``pause_requested`` and the
    worker settles it to ``paused`` at the next safe step.
    """
    run = await load_workroom_run(org_id, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Agent run not found")
    user, _, _ = await _authorized_workroom(
        request, org_id, run["workroom_id"], permission="edit"
    )
    if run["current_step"] == "creating_compose_briefing":
        raise HTTPException(
            status_code=409,
            detail="The approved Compose handoff is already being created",
        )
    if run["status"] not in {"queued", "running", "awaiting_approval"}:
        raise HTTPException(status_code=409, detail="This run cannot be paused")

    deferred = run["status"] == "running"
    updated = await transition_workroom_run(
        org_id,
        run_id,
        from_statuses=["running"] if deferred else ["queued", "awaiting_approval"],
        status="pause_requested" if deferred else "paused",
        current_step="pause_requested" if deferred else "paused",
    )
    if updated is None:
        raise HTTPException(status_code=409, detail="This run changed state")
    await append_workroom_event(
        org_id=org_id,
        room_id=run["workroom_id"],
        run_id=run_id,
        actor_type="human",
        actor_name=user["name"],
        event_type="run_paused",
        message=(
            "Requested a pause. The agent stops after the current step."
            if deferred
            else "Paused the agent run."
        ),
    )
    return updated


@app.post("/workroom-runs/{run_id}/resume")
async def resume_workroom_run(
    run_id: str, request: Request, org_id: str = Query(...)
):
    run = await load_workroom_run(org_id, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Agent run not found")
    user, _, _ = await _authorized_workroom(
        request, org_id, run["workroom_id"], permission="edit"
    )
    if run["status"] not in {"paused", "pause_requested"}:
        raise HTTPException(status_code=409, detail="This run is not paused")

    if run["status"] == "pause_requested":
        # The worker never reached a safe step, so simply withdraw the request.
        updated = await transition_workroom_run(
            org_id,
            run_id,
            from_statuses=["pause_requested"],
            status="running",
            current_step="searching_company_brain",
        )
        if updated is None:
            raise HTTPException(status_code=409, detail="This run changed state")
        await append_workroom_event(
            org_id=org_id,
            room_id=run["workroom_id"],
            run_id=run_id,
            actor_type="human",
            actor_name=user["name"],
            event_type="run_resumed",
            message="Withdrew the pause request before the agent stopped.",
        )
        return updated

    has_context = bool((run.get("context_snapshot") or {}).get("findings"))
    updated = await transition_workroom_run(
        org_id,
        run_id,
        from_statuses=["paused"],
        status="awaiting_approval" if has_context else "queued",
        current_step="approval_required" if has_context else "queued",
    )
    if updated is None:
        raise HTTPException(status_code=409, detail="This run changed state")
    await append_workroom_event(
        org_id=org_id,
        room_id=run["workroom_id"],
        run_id=run_id,
        actor_type="human",
        actor_name=user["name"],
        event_type="run_resumed",
        message="Resumed the agent run.",
    )
    if not has_context:
        await enqueue_research(
            org_id=org_id,
            room_id=run["workroom_id"],
            run_id=run_id,
            user_id=user["id"],
            user_name=user["name"],
        )
    return updated


@app.post("/workroom-runs/{run_id}/cancel")
async def cancel_workroom_run(
    run_id: str, request: Request, org_id: str = Query(...)
):
    """Cancel a run, stopping a running agent at its next safe step."""
    run = await load_workroom_run(org_id, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Agent run not found")
    user, _, _ = await _authorized_workroom(
        request, org_id, run["workroom_id"], permission="edit"
    )
    if run["status"] in WORKROOM_TERMINAL_STATES:
        raise HTTPException(status_code=409, detail="This run already finished")

    deferred = run["status"] == "running"
    updated = await transition_workroom_run(
        org_id,
        run_id,
        from_statuses=(
            ["running"]
            if deferred
            else ["queued", "paused", "pause_requested", "awaiting_approval"]
        ),
        status="cancel_requested" if deferred else "cancelled",
        current_step="cancel_requested" if deferred else "cancelled",
    )
    if updated is None:
        raise HTTPException(status_code=409, detail="This run changed state")
    await workroom_queue.cancel_jobs_for_run(run_id)
    if not deferred and run.get("task_id"):
        await update_workroom_task(org_id, run["task_id"], status="todo")
    await append_workroom_event(
        org_id=org_id,
        room_id=run["workroom_id"],
        run_id=run_id,
        actor_type="human",
        actor_name=user["name"],
        event_type="run_cancelled",
        message=(
            "Requested cancellation. The agent stops after the current step."
            if deferred
            else "Cancelled the agent run."
        ),
    )
    return updated


@app.post("/workroom-runs/{run_id}/retry", status_code=202)
async def retry_workroom_run(
    run_id: str, request: Request, org_id: str = Query(...)
):
    """Queue a fresh attempt for a failed run without losing its history."""
    run = await load_workroom_run(org_id, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Agent run not found")
    user, _, _ = await _authorized_workroom(
        request, org_id, run["workroom_id"], permission="edit"
    )
    if run["status"] != "failed":
        raise HTTPException(status_code=409, detail="Only a failed run can be retried")
    updated = await transition_workroom_run(
        org_id,
        run_id,
        from_statuses=["failed"],
        status="queued",
        current_step="queued",
        result={},
    )
    if updated is None:
        raise HTTPException(status_code=409, detail="This run changed state")
    if run.get("task_id"):
        await update_workroom_task(org_id, run["task_id"], status="in_progress")
    await append_workroom_event(
        org_id=org_id,
        room_id=run["workroom_id"],
        run_id=run_id,
        actor_type="human",
        actor_name=user["name"],
        event_type="run_retried",
        message="Queued another attempt for the failed agent run.",
    )
    await enqueue_research(
        org_id=org_id,
        room_id=run["workroom_id"],
        run_id=run_id,
        user_id=user["id"],
        user_name=user["name"],
    )
    return updated


@app.post("/workroom-runs/{run_id}/redirect", status_code=202)
async def redirect_workroom_run(
    run_id: str,
    payload: WorkroomRedirectRequest,
    request: Request,
    org_id: str = Query(...),
):
    run = await load_workroom_run(org_id, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Agent run not found")
    user, _, _ = await _authorized_workroom(
        request, org_id, run["workroom_id"], permission="edit"
    )
    if run["status"] in WORKROOM_TERMINAL_STATES:
        raise HTTPException(status_code=409, detail="This run cannot be redirected")
    redirected = await transition_workroom_run(
        org_id,
        run_id,
        from_statuses=[
            "queued", "running", "awaiting_approval", "paused",
            "pause_requested", "cancel_requested", "failed",
        ],
        status="redirected",
        current_step="redirected",
    )
    if redirected is None:
        raise HTTPException(status_code=409, detail="This run changed state")
    instruction = " ".join(payload.instruction.split())
    await append_workroom_event(
        org_id=org_id,
        room_id=run["workroom_id"],
        run_id=run_id,
        actor_type="human",
        actor_name=user["name"],
        event_type="run_redirected",
        message=f"Changed direction: {instruction}",
    )
    # A redirect is an explicit instruction, so it belongs in the conversation
    # as well as the audit trail. Ordinary messages never do this.
    await create_workroom_message(
        org_id=org_id,
        room_id=run["workroom_id"],
        author_type="human",
        author_user_id=user["id"],
        author_name=user["name"],
        body=f"Redirected the agent: {instruction}",
        reply_to_message_id=None,
        references=[{"kind": "run", "id": run_id, "label": "Superseded attempt"}],
        mentions=[],
    )
    replacement = await create_workroom_run(
        org_id=org_id,
        room_id=run["workroom_id"],
        task_id=run.get("task_id"),
        user_id=user["id"],
        instruction=instruction,
        redirected_from_run_id=run_id,
    )
    # The superseded run's queued work must not race the replacement.
    await workroom_queue.cancel_jobs_for_run(run_id, reason="redirected")
    await enqueue_research(
        org_id=org_id,
        room_id=run["workroom_id"],
        run_id=replacement["id"],
        user_id=user["id"],
        user_name=user["name"],
    )
    return replacement


@app.post("/workroom-runs/{run_id}/approval")
async def approve_workroom_run(
    run_id: str,
    payload: WorkroomApprovalRequest,
    request: Request,
    org_id: str = Query(...),
):
    run = await load_workroom_run(org_id, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Agent run not found")
    # Signing off on a governed output is the approver's job, deliberately
    # separate from editing the plan.
    user, _, _ = await _authorized_workroom(
        request, org_id, run["workroom_id"], permission="approve"
    )
    if run["status"] != "awaiting_approval":
        raise HTTPException(status_code=409, detail="This run is not awaiting approval")
    if not payload.approved:
        updated = await transition_workroom_run(
            org_id,
            run_id,
            from_statuses=["awaiting_approval"],
            status="cancelled",
            current_step="approval_denied",
            approved_by_user_id=user["id"],
        )
        if updated is None:
            raise HTTPException(status_code=409, detail="This run changed state")
        if run.get("task_id"):
            await update_workroom_task(org_id, run["task_id"], status="todo")
        await append_workroom_event(
            org_id=org_id,
            room_id=run["workroom_id"],
            run_id=run_id,
            actor_type="human",
            actor_name=user["name"],
            event_type="approval_denied",
            message="Rejected the proposed Compose handoff.",
        )
        return updated

    updated = await transition_workroom_run(
        org_id,
        run_id,
        from_statuses=["awaiting_approval"],
        status="running",
        current_step="creating_compose_briefing",
        approved_by_user_id=user["id"],
    )
    if updated is None:
        raise HTTPException(status_code=409, detail="This run changed state")
    await append_workroom_event(
        org_id=org_id,
        room_id=run["workroom_id"],
        run_id=run_id,
        actor_type="human",
        actor_name=user["name"],
        event_type="approval_granted",
        message="Approved the agent's Compose handoff.",
    )
    await enqueue_finalize(
        org_id=org_id,
        room_id=run["workroom_id"],
        run_id=run_id,
        user_id=user["id"],
        user_name=user["name"],
    )
    return updated


@app.get("/workrooms/{room_id}/events")
async def stream_workroom_events(
    room_id: str,
    request: Request,
    org_id: str = Query(...),
    after: int = Query(0, ge=0),
):
    await _authorized_workroom(request, org_id, room_id)

    # Events are persisted, so a dropped connection resumes exactly where it
    # left off. The browser replays its position via Last-Event-ID; the
    # `after` parameter serves clients that track the cursor themselves.
    resume_from = after
    last_event_id = request.headers.get("last-event-id")
    if last_event_id:
        try:
            resume_from = max(resume_from, int(last_event_id))
        except ValueError:
            pass

    async def event_stream():
        cursor = resume_from
        idle_ticks = 0
        while idle_ticks < 55 and not await request.is_disconnected():
            events = await list_events_after(org_id, room_id, cursor)
            if events:
                idle_ticks = 0
                for event in events:
                    # Monotonic ids make replay after a reconnect duplicate-free.
                    if int(event["id"]) <= cursor:
                        continue
                    cursor = int(event["id"])
                    yield f"id: {event['id']}\ndata: {json.dumps(event)}\n\n"
            else:
                idle_ticks += 1
                if idle_ticks % 15 == 0:
                    yield ": keep-alive\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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
                payload.org_id,
                user["id"],
                payload.conversation_id,
                message_limit=40,
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
            plan = _fallback_chat_plan(
                payload.message, history=conversation_history
            )
        else:
            try:
                plan = await _plan_chat_query(
                    llm, payload.message, conversation_history
                )
            except Exception as planner_error:
                print(f"Chat query planning failed: {planner_error}")
                plan = _fallback_chat_plan(
                    payload.message, broad=True, history=conversation_history
                )

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
                merged = {result["id"]: dict(result) for result in search_results}
                for result in literal_results:
                    if result["id"] in merged:
                        merged[result["id"]].update({
                            key: value for key, value in result.items()
                            if key not in {"vector_score", "text_score"}
                        })
                    else:
                        merged[result["id"]] = result
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
        if operation == "search":
            search_results = _rerank_chat_results(
                retrieval_query,
                search_results,
                limit=min(plan["limit"], 8),
            )

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
