"""E2E check for the MCP search tool over Streamable HTTP.

Run inside the MCP container while the stack is healthy:
    python tests/search_context_e2e.py
"""

import asyncio

from fastmcp import Client

from helpers import create_test_api_key, delete_test_api_key
from core.graph import GraphClient


ORG_ID = "e2e-mcp-search"
OTHER_ORG_ID = "e2e-mcp-search-other"
NODE_IDS = [
    "e2e-mcp-decision",
    "e2e-mcp-goal",
    "e2e-mcp-proposed",
    "e2e-mcp-other",
    "e2e-mcp-orphan",
    "e2e-mcp-decision-evidence",
    "e2e-mcp-goal-evidence",
    "e2e-mcp-proposed-evidence",
    "e2e-mcp-other-evidence",
]


async def cleanup() -> None:
    await GraphClient.run_query(
        "MATCH (node) WHERE node.id IN $ids DETACH DELETE node",
        {"ids": NODE_IDS},
    )


async def seed() -> None:
    await cleanup()
    await GraphClient.run_query(
        """
        CREATE (decision:Entity:Decision {
            id: 'e2e-mcp-decision', org_id: $org_id, entity_type: 'Decision',
            statement: 'Use MCPQuasar7 for the verified context transport.',
            detail: 'This decision must carry only its architecture citation.',
            status: 'confirmed', confidence: 'high',
            created_at: datetime(), updated_at: datetime(), confirmed_at: datetime()
        })
        CREATE (goal:Entity:Goal {
            id: 'e2e-mcp-goal', org_id: $org_id, entity_type: 'Goal',
            statement: 'Document the MCPQuasar7 rollout.',
            status: 'confirmed', confidence: 'medium',
            created_at: datetime(), updated_at: datetime(), confirmed_at: datetime()
        })
        CREATE (proposed:Entity:Decision {
            id: 'e2e-mcp-proposed', org_id: $org_id, entity_type: 'Decision',
            statement: 'Replace MCPQuasar7 with an unreviewed transport.',
            status: 'proposed', confidence: 'medium',
            created_at: datetime(), updated_at: datetime()
        })
        CREATE (other:Entity:Decision {
            id: 'e2e-mcp-other', org_id: $other_org_id, entity_type: 'Decision',
            statement: 'MCPQuasar7 belongs to another organization.',
            status: 'confirmed', confidence: 'high',
            created_at: datetime(), updated_at: datetime(), confirmed_at: datetime()
        })
        CREATE (orphan:Entity:Project {
            id: 'e2e-mcp-orphan', org_id: $org_id, entity_type: 'Project',
            statement: 'MCPOrphan7 has no supporting source.',
            status: 'confirmed', confidence: 'low',
            created_at: datetime(), updated_at: datetime(), confirmed_at: datetime()
        })
        CREATE (decision_ev:Evidence {
            id: 'e2e-mcp-decision-evidence', org_id: $org_id,
            source: 'local_docs', reference: 'architecture.md',
            url: 'https://example.com/architecture',
            excerpt: 'Decision: Use MCPQuasar7 for verified context transport.',
            source_date: datetime('2026-07-16T10:00:00Z'), created_at: datetime()
        })
        CREATE (goal_ev:Evidence {
            id: 'e2e-mcp-goal-evidence', org_id: $org_id,
            source: 'local_docs', reference: 'goals.md',
            excerpt: 'Goal: Document the MCPQuasar7 rollout.',
            source_date: datetime(), created_at: datetime()
        })
        CREATE (proposed_ev:Evidence {
            id: 'e2e-mcp-proposed-evidence', org_id: $org_id,
            source: 'local_docs', reference: 'unreviewed.md',
            excerpt: 'This evidence must remain hidden.',
            source_date: datetime(), created_at: datetime()
        })
        CREATE (other_ev:Evidence {
            id: 'e2e-mcp-other-evidence', org_id: $other_org_id,
            source: 'local_docs', reference: 'other-org.md',
            excerpt: 'This evidence belongs to another organization.',
            source_date: datetime(), created_at: datetime()
        })
        CREATE (decision)-[:CITED_BY]->(decision_ev)
        CREATE (goal)-[:CITED_BY]->(goal_ev)
        CREATE (proposed)-[:CITED_BY]->(proposed_ev)
        CREATE (other)-[:CITED_BY]->(other_ev)
        """,
        {"org_id": ORG_ID, "other_org_id": OTHER_ORG_ID},
    )


def text_result(result) -> str:
    return "".join(getattr(item, "text", "") for item in result.content)


async def run() -> None:
    GraphClient.initialize()
    await seed()
    key_id, raw_key = await create_test_api_key(ORG_ID)

    try:
        async with Client("http://localhost:8080/mcp", auth=raw_key) as client:
            tools = await client.list_tools()
            assert "search_company_context" in {tool.name for tool in tools}, tools

            decision = await client.call_tool(
                "search_company_context",
                {"query": "MCPQuasar7 transport", "types": ["Decision"], "limit": 8},
            )
            decision_text = text_result(decision)
            assert "Use MCPQuasar7" in decision_text, decision_text
            assert "architecture.md" in decision_text, decision_text
            assert "https://example.com/architecture" in decision_text, decision_text
            assert "goals.md" not in decision_text, decision_text
            assert "unreviewed.md" not in decision_text, decision_text
            assert "other-org.md" not in decision_text, decision_text

            all_types = await client.call_tool(
                "search_company_context",
                {"query": "MCPQuasar7", "limit": 20},
            )
            all_text = text_result(all_types)
            assert "architecture.md" in all_text, all_text
            assert "goals.md" in all_text, all_text
            assert "unreviewed.md" not in all_text, all_text
            assert "other-org.md" not in all_text, all_text

            orphan = await client.call_tool(
                "search_company_context",
                {"query": "MCPOrphan7", "types": ["Project"]},
            )
            assert text_result(orphan) == "No cited confirmed context found for this query."

            invalid = await client.call_tool(
                "search_company_context",
                {"query": "MCPQuasar7", "types": ["Person"]},
            )
            assert "Unsupported entity type(s): Person" in text_result(invalid)

        print("MCP cited search E2E: OK")
    finally:
        await delete_test_api_key(key_id)
        await cleanup()
        await GraphClient.close()


if __name__ == "__main__":
    asyncio.run(run())
