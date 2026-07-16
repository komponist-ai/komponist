"""E2E check for durable, org-isolated MCP approval requests.

Run the seed phase, restart the MCP container, then run the verify phase:
    python tests/approval_persistence_e2e.py seed
    python tests/approval_persistence_e2e.py verify
"""

import asyncio
import sys
from pathlib import Path

from fastmcp import Client
from sqlalchemy import delete, select

MCP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MCP_DIR))
sys.path.insert(0, str(MCP_DIR.parent / "api"))

from constraints import get_approval_status, resolve_approval
from core.graph import GraphClient
from database import ApprovalRequest, async_session


ORG_ID = "default-org"
OTHER_ORG_ID = "e2e-approval-other-org"
CONSTRAINT_ID = "e2e-persistent-approval-constraint"
ACTION = "Publish the persistent approval E2E release."


def text_result(result) -> str:
    return "".join(getattr(item, "text", "") for item in result.content)


async def cleanup() -> None:
    async with async_session() as session:
        await session.execute(
            delete(ApprovalRequest).where(
                ApprovalRequest.constraint_id == CONSTRAINT_ID
            )
        )
        await session.commit()

    await GraphClient.run_query(
        """
        MATCH (node)
        WHERE node.id IN [$constraint_id, $evidence_id]
        DETACH DELETE node
        """,
        {
            "constraint_id": CONSTRAINT_ID,
            "evidence_id": f"{CONSTRAINT_ID}-evidence",
        },
    )


async def seed() -> None:
    GraphClient.initialize()
    await cleanup()
    await GraphClient.run_query(
        """
        CREATE (constraint:Entity:Constraint {
            id: $constraint_id,
            org_id: $org_id,
            entity_type: 'Constraint',
            statement: 'Publishing an E2E release requires human approval.',
            detail: 'Approval state must survive an MCP restart.',
            enforcement: 'approve',
            status: 'confirmed',
            confidence: 'high',
            created_at: datetime(),
            updated_at: datetime(),
            confirmed_at: datetime()
        })
        CREATE (evidence:Evidence {
            id: $evidence_id,
            org_id: $org_id,
            source: 'e2e',
            reference: 'approval-persistence',
            excerpt: 'Publishing requires approval.',
            url: 'https://example.test/approval',
            created_at: datetime()
        })
        CREATE (constraint)-[:CITED_BY]->(evidence)
        """,
        {
            "constraint_id": CONSTRAINT_ID,
            "evidence_id": f"{CONSTRAINT_ID}-evidence",
            "org_id": ORG_ID,
        },
    )

    try:
        async with Client("http://localhost:8080/mcp") as client:
            created = await client.call_tool(
                "request_approval",
                {
                    "action": ACTION,
                    "constraint_id": CONSTRAINT_ID,
                    "context": "Verify durable approval workflow state.",
                },
            )
            created_text = text_result(created)
            assert "Approval request created" in created_text, created_text

        async with async_session() as session:
            result = await session.execute(
                select(ApprovalRequest).where(
                    ApprovalRequest.org_id == ORG_ID,
                    ApprovalRequest.constraint_id == CONSTRAINT_ID,
                )
            )
            approval = result.scalar_one()
            assert approval.action == ACTION
            assert approval.status == "pending"
            print(f"Approval persistence seed: OK ({approval.id})")
    except Exception:
        await cleanup()
        raise
    finally:
        await GraphClient.close()


async def verify() -> None:
    GraphClient.initialize()
    try:
        async with async_session() as session:
            result = await session.execute(
                select(ApprovalRequest).where(
                    ApprovalRequest.org_id == ORG_ID,
                    ApprovalRequest.constraint_id == CONSTRAINT_ID,
                )
            )
            approval_id = result.scalar_one().id

        async with Client("http://localhost:8080/mcp") as client:
            pending = await client.call_tool(
                "get_approval_status", {"approval_id": approval_id}
            )
            assert "Approval pending" in text_result(pending), text_result(pending)

            isolated = await get_approval_status(approval_id, org_id=OTHER_ORG_ID)
            assert isolated["status"] == "not_found", isolated

            approved = await resolve_approval(
                approval_id,
                approved=True,
                resolved_by="e2e-reviewer",
                org_id=ORG_ID,
            )
            assert approved["status"] == "approved", approved

            second_decision = await resolve_approval(
                approval_id,
                approved=False,
                resolved_by="late-reviewer",
                org_id=ORG_ID,
            )
            assert second_decision["status"] == "approved", second_decision
            assert second_decision["resolved_by"] == "e2e-reviewer", second_decision

            resolved = await client.call_tool(
                "get_approval_status", {"approval_id": approval_id}
            )
            resolved_text = text_result(resolved)
            assert "Approved" in resolved_text, resolved_text
            assert "e2e-reviewer" in resolved_text, resolved_text

        print("Approval persistence restart E2E: OK")
    finally:
        await cleanup()
        await GraphClient.close()


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in {"seed", "verify"}:
        raise SystemExit("Usage: approval_persistence_e2e.py seed|verify")
    asyncio.run(seed() if sys.argv[1] == "seed" else verify())
