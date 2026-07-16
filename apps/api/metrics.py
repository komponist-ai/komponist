"""
Metrics endpoint.

Internal metrics for traction, usage, and health monitoring.
"""

from typing import Dict, Any
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException
from sqlalchemy import select, func

import sys
sys.path.append("../../packages")

from core.graph import GraphClient
from database import async_session, ToolCall


router = APIRouter(prefix="/internal/metrics", tags=["metrics"])


@router.get("/")
async def get_metrics(org_id: str = "default-org") -> Dict[str, Any]:
    """
    Get metrics for an organization.

    Returns:
        Dict with usage stats, brain stats, governance stats
    """
    metrics = {}

    # Time windows
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    # Tool usage metrics (from Postgres)
    async with async_session() as session:
        # Weekly active (unique days with tool calls)
        weekly_result = await session.execute(
            select(func.count(func.distinct(func.date(ToolCall.created_at))))
            .where(ToolCall.org_id == org_id)
            .where(ToolCall.created_at >= week_ago)
        )
        weekly_active_days = weekly_result.scalar() or 0

        # Tool calls by tool (last 7 days)
        tool_calls_result = await session.execute(
            select(
                ToolCall.tool,
                func.count(ToolCall.id).label("count"),
                func.avg(ToolCall.latency_ms).label("avg_latency")
            )
            .where(ToolCall.org_id == org_id)
            .where(ToolCall.created_at >= week_ago)
            .group_by(ToolCall.tool)
        )
        tool_calls = [
            {
                "tool": row.tool,
                "count": row.count,
                "avg_latency_ms": int(row.avg_latency) if row.avg_latency else None
            }
            for row in tool_calls_result
        ]

        # Governance metrics (the killer metric)
        blocked_result = await session.execute(
            select(func.count(ToolCall.id))
            .where(ToolCall.org_id == org_id)
            .where(ToolCall.tool == "check_constraint")
            .where(ToolCall.verdict == "blocked")
            .where(ToolCall.created_at >= week_ago)
        )
        blocked_count = blocked_result.scalar() or 0

        approval_result = await session.execute(
            select(func.count(ToolCall.id))
            .where(ToolCall.org_id == org_id)
            .where(ToolCall.tool == "check_constraint")
            .where(ToolCall.verdict == "approval_required")
            .where(ToolCall.created_at >= week_ago)
        )
        approval_count = approval_result.scalar() or 0

        allowed_result = await session.execute(
            select(func.count(ToolCall.id))
            .where(ToolCall.org_id == org_id)
            .where(ToolCall.tool == "check_constraint")
            .where(ToolCall.verdict == "allowed")
            .where(ToolCall.created_at >= week_ago)
        )
        allowed_count = allowed_result.scalar() or 0

        metrics["tool_usage"] = {
            "weekly_active_days": weekly_active_days,
            "tool_calls_last_7d": tool_calls,
            "total_calls_last_7d": sum(t["count"] for t in tool_calls)
        }

        metrics["governance"] = {
            "blocked": blocked_count,
            "approval_required": approval_count,
            "allowed": allowed_count,
            "total_checks": blocked_count + approval_count + allowed_count,
            "block_rate": blocked_count / (blocked_count + approval_count + allowed_count) if (blocked_count + approval_count + allowed_count) > 0 else 0
        }

    # Brain metrics (from Neo4j)
    brain_query = """
    MATCH (e:Entity {org_id: $org_id})
    WITH count(e) as total,
         count(CASE WHEN e.status = 'confirmed' THEN 1 END) as confirmed,
         count(CASE WHEN e.status = 'proposed' THEN 1 END) as proposed,
         count(CASE WHEN e.status = 'superseded' THEN 1 END) as superseded
    MATCH (ev:Evidence {org_id: $org_id})
    WITH total, confirmed, proposed, superseded, count(ev) as evidence
    MATCH (w:WorkPack {org_id: $org_id})
    RETURN total, confirmed, proposed, superseded, evidence, count(w) as workpacks
    """

    brain_result = await GraphClient.run_query(brain_query, {"org_id": org_id})

    if brain_result:
        br = brain_result[0]
        metrics["brain"] = {
            "total_entities": br.get("total", 0),
            "confirmed": br.get("confirmed", 0),
            "proposed": br.get("proposed", 0),
            "superseded": br.get("superseded", 0),
            "evidence_nodes": br.get("evidence", 0),
            "work_packs": br.get("workpacks", 0)
        }
    else:
        metrics["brain"] = {
            "total_entities": 0,
            "confirmed": 0,
            "proposed": 0,
            "superseded": 0,
            "evidence_nodes": 0,
            "work_packs": 0
        }

    # Entity type breakdown
    type_query = """
    MATCH (e:Entity {org_id: $org_id, status: 'confirmed'})
    RETURN e.entity_type as type, count(e) as count
    ORDER BY count DESC
    """

    type_result = await GraphClient.run_query(type_query, {"org_id": org_id})
    metrics["brain"]["by_type"] = [
        {"type": r["type"], "count": r["count"]}
        for r in type_result
    ]

    metrics["org_id"] = org_id
    metrics["generated_at"] = now.isoformat()

    return metrics


@router.get("/violations")
async def get_violations_timeline(
    org_id: str = "default-org",
    days: int = 30
) -> Dict[str, Any]:
    """
    Get violations blocked over time (the killer metric).

    Args:
        org_id: Organization ID
        days: Days to look back

    Returns:
        Daily counts of blocked verdicts
    """
    cutoff = datetime.utcnow() - timedelta(days=days)

    async with async_session() as session:
        result = await session.execute(
            select(
                func.date(ToolCall.created_at).label("date"),
                func.count(ToolCall.id).label("count")
            )
            .where(ToolCall.org_id == org_id)
            .where(ToolCall.tool == "check_constraint")
            .where(ToolCall.verdict == "blocked")
            .where(ToolCall.created_at >= cutoff)
            .group_by(func.date(ToolCall.created_at))
            .order_by(func.date(ToolCall.created_at))
        )

        timeline = [
            {
                "date": row.date.isoformat(),
                "violations_blocked": row.count
            }
            for row in result
        ]

    return {
        "org_id": org_id,
        "days": days,
        "timeline": timeline,
        "total_blocked": sum(t["violations_blocked"] for t in timeline)
    }


@router.get("/health")
async def get_health_metrics() -> Dict[str, Any]:
    """
    Get system health metrics.

    Returns:
        Database health, queue sizes, error rates
    """
    from database import EventRaw

    async with async_session() as session:
        # Unprocessed events
        unprocessed_result = await session.execute(
            select(func.count(EventRaw.id))
            .where(EventRaw.processed_at.is_(None))
        )
        unprocessed = unprocessed_result.scalar() or 0

        # Events with errors
        errors_result = await session.execute(
            select(func.count(EventRaw.id))
            .where(EventRaw.error.isnot(None))
            .where(EventRaw.created_at >= datetime.utcnow() - timedelta(hours=24))
        )
        errors_24h = errors_result.scalar() or 0

    # Neo4j health
    neo4j_health = await GraphClient.health_check()

    # Postgres health
    from database import health_check_db
    postgres_health = await health_check_db()

    return {
        "databases": {
            "neo4j": neo4j_health,
            "postgres": postgres_health
        },
        "queue": {
            "unprocessed_events": unprocessed,
            "errors_last_24h": errors_24h
        },
        "status": "healthy" if neo4j_health["status"] == "healthy" and postgres_health["status"] == "healthy" else "degraded"
    }
