"""
Constraint checking tools for MCP server.

check_constraint, request_approval, get_approval_status
"""

import os
import sys
import time
from datetime import datetime
from typing import Optional, Dict, Any
from uuid import uuid4

sys.path.append("../../packages")
sys.path.append("../api")

from core.graph import GraphClient
from core.queries import BrainQueries
from core.embeddings import embed
from core.llm import call_llm_json, Model
from database import ApprovalRequest, async_session

import httpx
from sqlalchemy import select


# Slack configuration
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_APPROVALS_CHANNEL = os.getenv("SLACK_APPROVALS_CHANNEL", "")  # Channel ID


async def check_constraint(
    intended_action: str,
    project: Optional[str] = None,
    org_id: str = "default-org"
) -> Dict[str, Any]:
    """
    Check if an intended action violates any constraints.

    Uses vector similarity to find relevant constraints, then LLM adjudication
    to determine if the constraint applies. Biased toward "allowed" (ADR-010).

    Args:
        intended_action: Description of what the agent wants to do
        project: Optional project ID for scoped constraints
        org_id: Organization ID

    Returns:
        Dict with verdict, constraint (if applicable), reasoning
    """
    start_time = time.time()

    try:
        # Get applicable constraints
        constraints = await BrainQueries.applicable_constraints(
            org_id=org_id,
            project_id=project
        )

        if not constraints:
            return {
                "verdict": "allowed",
                "constraint_id": None,
                "reasoning": "No constraints apply to this action.",
                "latency_ms": int((time.time() - start_time) * 1000)
            }

        # Embed the intended action
        action_embedding = await embed(intended_action)

        # Find top-10 most relevant constraints by vector similarity
        from core.graph import GraphClient

        similarity_query = """
        MATCH (c:Constraint {org_id: $org_id, status: 'confirmed'})
        WHERE c.id IN $constraint_ids AND c.embedding IS NOT NULL
        WITH c,
             reduce(s = 0.0, i IN range(0, size($action_embedding)-1) |
                 s + (c.embedding[i] * $action_embedding[i])
             ) / (
                 sqrt(reduce(s = 0.0, i IN range(0, size(c.embedding)-1) | s + c.embedding[i] * c.embedding[i])) *
                 sqrt(reduce(s = 0.0, i IN range(0, size($action_embedding)-1) | s + $action_embedding[i] * $action_embedding[i]))
             ) AS similarity
        WHERE similarity > 0.5
        RETURN c.id as id, c.statement as statement, c.detail as detail,
               c.enforcement as enforcement, similarity
        ORDER BY similarity DESC
        LIMIT 10
        """

        constraint_ids = [c["id"] for c in constraints]
        relevant = await GraphClient.run_query(similarity_query, {
            "org_id": org_id,
            "constraint_ids": constraint_ids,
            "action_embedding": action_embedding
        })

        if not relevant:
            return {
                "verdict": "allowed",
                "constraint_id": None,
                "reasoning": "No relevant constraints found for this action.",
                "latency_ms": int((time.time() - start_time) * 1000)
            }

        # LLM adjudication
        constraints_text = "\n\n".join([
            f"Constraint ID: {c['id']}\nStatement: {c['statement']}\nDetail: {c.get('detail', '')}\nEnforcement: {c.get('enforcement', 'approve')}"
            for c in relevant
        ])

        system_prompt = """You are a constraint adjudicator for a coding agent governance system.

Your job: determine if the intended action violates any of the provided constraints.

CRITICAL BIAS RULE (ADR-010): Default to "allowed" unless a constraint CLEARLY and EXPLICITLY applies.
- Ambiguity -> allowed
- Uncertain -> allowed
- "Might violate" -> allowed
- Only block/require approval if the constraint unambiguously forbids the action

Respond with JSON:
{
  "verdict": "allowed" | "blocked" | "approval_required",
  "constraint_id": "id of the matching constraint (if any)",
  "reasoning": "one sentence explaining why"
}

Map enforcement:
- enforcement="block" + applies -> verdict="blocked"
- enforcement="approve" + applies -> verdict="approval_required"
- doesn't apply or uncertain -> verdict="allowed"
"""

        prompt = f"""Intended action:
{intended_action}

Constraints to check:
{constraints_text}

Does the intended action violate any constraint?"""

        adjudication = await call_llm_json(
            prompt=prompt,
            system=system_prompt,
            model=Model.SONNET,
            max_tokens=500
        )

        verdict = adjudication.get("verdict", "allowed")
        constraint_id = adjudication.get("constraint_id")
        reasoning = adjudication.get("reasoning", "")

        # Get full constraint details if matched
        matched_constraint = None
        if constraint_id:
            matched_constraint = next((c for c in relevant if c["id"] == constraint_id), None)

        result = {
            "verdict": verdict,
            "constraint_id": constraint_id,
            "constraint": matched_constraint,
            "reasoning": reasoning,
            "latency_ms": int((time.time() - start_time) * 1000)
        }

        return result

    except Exception as e:
        return {
            "verdict": "error",
            "constraint_id": None,
            "reasoning": f"Error checking constraints: {e}",
            "latency_ms": int((time.time() - start_time) * 1000)
        }


async def request_approval(
    action: str,
    constraint_id: str,
    context: str,
    org_id: str = "default-org"
) -> Dict[str, Any]:
    """
    Persist a human approval request and optionally notify Slack.

    Slack delivery is best-effort; the durable database request is authoritative.

    Args:
        action: Action requiring approval
        constraint_id: Constraint that triggered approval requirement
        context: Additional context for approver
        org_id: Organization ID

    Returns:
        Dict with approval_id and status (pending)
    """
    action = action.strip()
    constraint_id = constraint_id.strip()
    context = context.strip()
    if not action or len(action) > 4000:
        return {
            "approval_id": None,
            "status": "error",
            "error": "Action must be 1-4000 characters",
        }
    if not constraint_id or len(constraint_id) > 64:
        return {
            "approval_id": None,
            "status": "error",
            "error": "Invalid constraint ID",
        }
    if len(context) > 8000:
        return {
            "approval_id": None,
            "status": "error",
            "error": "Context must be at most 8000 characters",
        }

    # Get constraint details
    constraint_query = """
    MATCH (c:Constraint {id: $constraint_id, org_id: $org_id})
    OPTIONAL MATCH (c)-[:CITED_BY]->(e:Evidence {org_id: $org_id})
    RETURN c.statement as statement, c.detail as detail,
           collect(e{.source, .reference, .url}) as evidence
    """

    constraint_result = await GraphClient.run_query(constraint_query, {
        "constraint_id": constraint_id,
        "org_id": org_id
    })

    if not constraint_result:
        return {
            "approval_id": None,
            "status": "error",
            "error": "Constraint not found"
        }

    constraint = constraint_result[0]

    # Generate approval ID
    approval_id = f"approval-{uuid4().hex[:12]}"

    async with async_session() as session:
        session.add(ApprovalRequest(
            id=approval_id,
            org_id=org_id,
            action=action,
            constraint_id=constraint_id,
            constraint_statement=constraint["statement"],
            context=context,
            status="pending",
        ))
        await session.commit()

    # Post to Slack
    delivery = "not_configured"
    if SLACK_BOT_TOKEN and SLACK_APPROVALS_CHANNEL:
        delivery = "failed"
        try:
            # Build citation text
            citations = ""
            for e in constraint["evidence"]:
                if e.get("url"):
                    citations += f"<{e['url']}|{e['source']} · {e['reference']}>\n"
                else:
                    citations += f"{e['source']} · {e['reference']}\n"

            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "🚦 Agent Approval Required"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Action:*\n{action}"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Blocked by constraint:*\n_{constraint['statement']}_\n\n{constraint.get('detail', '')}"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Citations:*\n{citations}"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Context:*\n{context}"
                    }
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "✅ Approve"
                            },
                            "style": "primary",
                            "value": approval_id,
                            "action_id": f"approve_{approval_id}"
                        },
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "❌ Deny"
                            },
                            "style": "danger",
                            "value": approval_id,
                            "action_id": f"deny_{approval_id}"
                        }
                    ]
                }
            ]

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={
                        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "channel": SLACK_APPROVALS_CHANNEL,
                        "blocks": blocks,
                        "text": f"Approval required: {action[:100]}"
                    }
                )

                slack_result = response.json()
                if slack_result.get("ok"):
                    async with async_session() as session:
                        approval = await session.get(ApprovalRequest, approval_id)
                        if approval and approval.org_id == org_id:
                            approval.slack_ts = slack_result["ts"]
                            approval.updated_at = datetime.utcnow()
                            await session.commit()
                    delivery = "slack"
                else:
                    print(f"[Approval] Slack post failed: {slack_result}")

        except Exception as e:
            print(f"[Approval] Error posting to Slack: {e}")

    return {
        "approval_id": approval_id,
        "status": "pending",
        "delivery": delivery,
    }


async def get_approval_status(
    approval_id: str,
    org_id: str = "default-org",
) -> Dict[str, Any]:
    """
    Get status of a pending approval.

    Args:
        approval_id: Approval ID from request_approval

    Returns:
        Dict with status (pending/approved/denied) and metadata
    """
    async with async_session() as session:
        result = await session.execute(
            select(ApprovalRequest).where(
                ApprovalRequest.id == approval_id,
                ApprovalRequest.org_id == org_id,
            )
        )
        approval = result.scalar_one_or_none()

    if not approval:
        return {
            "approval_id": approval_id,
            "status": "not_found",
            "error": "Approval ID not found"
        }

    return {
        "approval_id": approval_id,
        "status": approval.status,
        "resolved_by": approval.resolved_by,
        "resolved_at": approval.resolved_at.isoformat() if approval.resolved_at else None,
    }


async def resolve_approval(
    approval_id: str,
    approved: bool,
    resolved_by: str,
    org_id: str = "default-org",
) -> Dict[str, Any]:
    """
    Resolve an approval (called by Slack webhook).

    Args:
        approval_id: Approval ID
        approved: True if approved, False if denied
        resolved_by: User who resolved (Slack user ID)
    """
    async with async_session() as session:
        result = await session.execute(
            select(ApprovalRequest)
            .where(
                ApprovalRequest.id == approval_id,
                ApprovalRequest.org_id == org_id,
            )
            .with_for_update()
        )
        approval = result.scalar_one_or_none()
        if not approval:
            return {"approval_id": approval_id, "status": "not_found"}

        if approval.status == "pending":
            approval.status = "approved" if approved else "denied"
            approval.resolved_at = datetime.utcnow()
            approval.resolved_by = (resolved_by or "unknown")[:255]
            approval.updated_at = datetime.utcnow()
            await session.commit()

        result = {
            "approval_id": approval.id,
            "status": approval.status,
            "resolved_by": approval.resolved_by,
            "resolved_at": approval.resolved_at.isoformat() if approval.resolved_at else None,
        }

    status = result["status"]
    print(f"[Approval] {approval_id} {status} by {result['resolved_by']}")
    return result


# TODO: Slack interaction webhook handler
# This would be added to the FastAPI app to handle button clicks
async def handle_slack_interaction(
    payload: Dict[str, Any],
    org_id: str = "default-org",
) -> Dict[str, Any]:
    """
    Handle Slack button interaction.

    Called by FastAPI webhook endpoint.
    """
    action = payload.get("actions", [{}])[0]
    action_id = action.get("action_id", "")
    approval_id = action.get("value")
    user = payload.get("user", {}).get("id")

    if action_id.startswith("approve_"):
        return await resolve_approval(
            approval_id, approved=True, resolved_by=user, org_id=org_id
        )
    elif action_id.startswith("deny_"):
        return await resolve_approval(
            approval_id, approved=False, resolved_by=user, org_id=org_id
        )
    return {"approval_id": approval_id, "status": "ignored"}
