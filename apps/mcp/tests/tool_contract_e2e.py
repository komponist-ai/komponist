"""Authenticated MCP discovery, decision scope, resource, and governance E2E."""

import asyncio
import os

from fastmcp import Client

from helpers import create_test_api_key, delete_test_api_key
from constraints import check_constraint
from core.graph import GraphClient


ORG_ID = "e2e-mcp-contract"
OTHER_ORG_ID = "e2e-mcp-contract-other"
NODE_IDS = [
    "mcp-contract-project",
    "mcp-contract-scoped",
    "mcp-contract-global",
    "mcp-contract-orphan",
    "mcp-contract-other",
    "mcp-contract-block",
    "mcp-contract-approve",
    "mcp-contract-scoped-ev",
    "mcp-contract-global-ev",
    "mcp-contract-other-ev",
    "mcp-contract-block-ev",
    "mcp-contract-approve-ev",
]


def text_result(result) -> str:
    return "".join(getattr(item, "text", "") for item in result.content)


async def cleanup() -> None:
    await GraphClient.run_query(
        "MATCH (node) WHERE node.id IN $ids DETACH DELETE node", {"ids": NODE_IDS}
    )


async def seed() -> None:
    await cleanup()
    await GraphClient.run_query(
        """
        CREATE (project:Entity:Project {
            id: 'mcp-contract-project', org_id: $org_id, entity_type: 'Project',
            statement: 'Northstar release', status: 'confirmed', confirmed_at: datetime()
        })
        CREATE (scoped:Entity:Decision {
            id: 'mcp-contract-scoped', org_id: $org_id, entity_type: 'Decision',
            statement: 'Ship Northstar with guarded rollout.', status: 'confirmed',
            confidence: 'high', confirmed_at: datetime()
        })
        CREATE (global:Entity:Decision {
            id: 'mcp-contract-global', org_id: $org_id, entity_type: 'Decision',
            statement: 'Use weekly architecture reviews.', status: 'confirmed',
            confidence: 'medium', confirmed_at: datetime()
        })
        CREATE (orphan:Entity:Decision {
            id: 'mcp-contract-orphan', org_id: $org_id, entity_type: 'Decision',
            statement: 'Evidence-free decision.', status: 'confirmed', confirmed_at: datetime()
        })
        CREATE (other:Entity:Decision {
            id: 'mcp-contract-other', org_id: $other_org_id, entity_type: 'Decision',
            statement: 'Other organization decision.', status: 'confirmed', confirmed_at: datetime()
        })
        CREATE (block:Entity:Constraint {
            id: 'mcp-contract-block', org_id: $org_id, entity_type: 'Constraint',
            statement: 'Never delete the production customer database.',
            enforcement: 'block', status: 'confirmed', confirmed_at: datetime()
        })
        CREATE (approve:Entity:Constraint {
            id: 'mcp-contract-approve', org_id: $org_id, entity_type: 'Constraint',
            statement: 'Publishing the Northstar release requires human approval.',
            enforcement: 'approve', status: 'confirmed', confirmed_at: datetime()
        })
        CREATE (scoped_ev:Evidence {id: 'mcp-contract-scoped-ev', org_id: $org_id,
            source: 'e2e', reference: 'northstar.md', excerpt: 'Guarded rollout.'})
        CREATE (global_ev:Evidence {id: 'mcp-contract-global-ev', org_id: $org_id,
            source: 'e2e', reference: 'architecture.md', excerpt: 'Weekly reviews.'})
        CREATE (other_ev:Evidence {id: 'mcp-contract-other-ev', org_id: $other_org_id,
            source: 'e2e', reference: 'other.md', excerpt: 'Other organization.'})
        CREATE (block_ev:Evidence {id: 'mcp-contract-block-ev', org_id: $org_id,
            source: 'e2e', reference: 'safety.md', excerpt: 'Never delete production.'})
        CREATE (approve_ev:Evidence {id: 'mcp-contract-approve-ev', org_id: $org_id,
            source: 'e2e', reference: 'release.md', excerpt: 'Approval is required.'})
        CREATE (scoped)-[:AFFECTS]->(project)
        CREATE (approve)-[:CONSTRAINS]->(project)
        CREATE (scoped)-[:CITED_BY]->(scoped_ev)
        CREATE (global)-[:CITED_BY]->(global_ev)
        CREATE (other)-[:CITED_BY]->(other_ev)
        CREATE (block)-[:CITED_BY]->(block_ev)
        CREATE (approve)-[:CITED_BY]->(approve_ev)
        """,
        {"org_id": ORG_ID, "other_org_id": OTHER_ORG_ID},
    )


async def run() -> None:
    GraphClient.initialize()
    await seed()
    key_id, raw_key = await create_test_api_key(ORG_ID)
    previous_mode = os.environ.get("KOMPONIST_AI_MODE")
    os.environ["KOMPONIST_AI_MODE"] = "mock"
    try:
        async with Client("http://localhost:8080/mcp", auth=raw_key) as client:
            tools = {tool.name for tool in await client.list_tools()}
            assert tools == {
                "search_company_context",
                "get_active_decisions",
                "report_result",
                "check_constraint",
                "request_approval",
                "get_approval_status",
            }, tools

            resources = {str(resource.uri) for resource in await client.list_resources()}
            assert "company-brain://info" in resources, resources
            info = await client.read_resource("company-brain://info")
            info_text = "".join(getattr(item, "text", "") for item in info)
            assert f"Organization: {ORG_ID}" in info_text, info_text
            assert "Pending review: 0" in info_text, info_text

            scoped = await client.call_tool(
                "get_active_decisions", {"project": "mcp-contract-project"}
            )
            scoped_text = text_result(scoped)
            assert "Ship Northstar" in scoped_text, scoped_text
            assert "northstar.md" in scoped_text, scoped_text
            assert "weekly architecture" not in scoped_text.casefold(), scoped_text
            assert "Evidence-free" not in scoped_text, scoped_text
            assert "Other organization" not in scoped_text, scoped_text

        blocked = await check_constraint(
            "Delete the production customer database now.", org_id=ORG_ID
        )
        assert blocked["verdict"] == "blocked", blocked
        assert blocked["constraint_id"] == "mcp-contract-block", blocked

        approval = await check_constraint(
            "Publish the Northstar release.",
            project="mcp-contract-project",
            org_id=ORG_ID,
        )
        assert approval["verdict"] == "approval_required", approval
        assert approval["constraint_id"] == "mcp-contract-approve", approval

        allowed = await check_constraint(
            "Update local test documentation.", org_id=ORG_ID
        )
        assert allowed["verdict"] == "allowed", allowed
        print("MCP tool contract E2E: OK")
    finally:
        if previous_mode is None:
            os.environ.pop("KOMPONIST_AI_MODE", None)
        else:
            os.environ["KOMPONIST_AI_MODE"] = previous_mode
        await delete_test_api_key(key_id)
        await cleanup()
        await GraphClient.close()


if __name__ == "__main__":
    asyncio.run(run())
