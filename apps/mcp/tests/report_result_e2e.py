"""E2E check for safe, idempotent MCP result reporting.

Run inside the MCP container while the stack is healthy:
    python tests/report_result_e2e.py
"""

import asyncio

import httpx
from fastmcp import Client

from core.graph import GraphClient


ORG_ID = "default-org"
WORK_PACK_ID = "e2e-report-result-work-pack"
STATEMENT = "Use ResultNebula7 for deterministic agent writeback."
EXISTING_STATEMENT = "Keep ExistingNebula7 as the confirmed writeback rule."
INVALID_STATEMENT = "ResultNebula7 must not be written for an invalid Work Pack."


async def cleanup() -> None:
    await GraphClient.run_query(
        """
        MATCH (node)
        WHERE node.id = $work_pack_id
           OR node.statement IN $statements
           OR (node:Evidence AND node.excerpt CONTAINS 'ResultNebula7')
           OR (node:Evidence AND node.excerpt CONTAINS 'ExistingNebula7')
        DETACH DELETE node
        """,
        {
            "work_pack_id": WORK_PACK_ID,
            "statements": [STATEMENT, EXISTING_STATEMENT, INVALID_STATEMENT],
        },
    )


async def seed() -> None:
    await cleanup()
    await GraphClient.run_query(
        """
        CREATE (:WorkPack {
            id: $work_pack_id, org_id: $org_id, title: 'E2E report result',
            status: 'active', created_at: datetime(), updated_at: datetime()
        })
        CREATE (:Entity:Decision {
            id: 'e2e-report-existing', org_id: $org_id, entity_type: 'Decision',
            statement: $existing_statement, detail: 'Confirmed before the report.',
            status: 'confirmed', confidence: 'high',
            created_at: datetime(), updated_at: datetime(), confirmed_at: datetime()
        })
        """,
        {
            "work_pack_id": WORK_PACK_ID,
            "org_id": ORG_ID,
            "existing_statement": EXISTING_STATEMENT,
        },
    )


def text_result(result) -> str:
    return "".join(getattr(item, "text", "") for item in result.content)


async def run() -> None:
    GraphClient.initialize()
    await seed()

    report_arguments = {
        "summary": "Implemented deterministic ResultNebula7 writeback.",
        "new_decisions": [
            {"statement": STATEMENT, "detail": "Agent reports require human review."},
            {"statement": STATEMENT, "detail": "Agent reports require human review."},
            {"statement": EXISTING_STATEMENT, "detail": "New supporting evidence."},
        ],
        "deviations": ["Used deterministic persistence instead of another LLM call."],
        "unresolved_questions": ["Should reports later support Goals as well?"],
        "work_pack_id": WORK_PACK_ID,
    }

    try:
        async with Client("http://localhost:8080/mcp") as client:
            invalid = await client.call_tool(
                "report_result",
                {
                    "summary": "This must be rejected before any write.",
                    "new_decisions": [{"statement": INVALID_STATEMENT, "detail": ""}],
                    "work_pack_id": "missing-e2e-work-pack",
                },
            )
            assert "was not found in this organization" in text_result(invalid)

            first = await client.call_tool("report_result", report_arguments)
            first_text = text_result(first)
            assert "1 new decision proposal(s)" in first_text, first_text
            assert "(confirmed)" in first_text, first_text
            assert f"Linked to Work Pack `{WORK_PACK_ID}`" in first_text, first_text

            async with httpx.AsyncClient(base_url="http://api:8000") as api_client:
                queue_response = await api_client.get(
                    "/queue", params={"org_id": ORG_ID}
                )
            assert queue_response.status_code == 200, queue_response.text
            queued = [
                item for item in queue_response.json()["items"]
                if item["statement"] == STATEMENT
            ]
            assert len(queued) == 1, queued
            assert queued[0]["entity_type"] == "Decision", queued
            assert queued[0]["evidence"][0]["source"] == "agent_report", queued

            hidden = await client.call_tool(
                "search_company_context",
                {"query": "ResultNebula7 deterministic writeback", "types": ["Decision"]},
            )
            hidden_text = text_result(hidden)
            assert STATEMENT not in hidden_text, hidden_text

            second = await client.call_tool("report_result", report_arguments)
            second_text = text_result(second)
            assert "new decision proposal(s)" not in second_text, second_text
            assert "(proposed)" in second_text, second_text
            assert "(confirmed)" in second_text, second_text

        verification = await GraphClient.run_query(
            """
            MATCH (proposal:Entity {org_id: $org_id, statement: $statement})
            OPTIONAL MATCH (proposal)-[:CITED_BY]->(proposal_ev:Evidence)
            OPTIONAL MATCH (proposal)-[:REPORTED_IN]->(work_pack:WorkPack {id: $work_pack_id})
            WITH proposal, count(DISTINCT proposal_ev) AS proposal_evidence,
                 count(DISTINCT work_pack) AS work_pack_links
            MATCH (existing:Entity {org_id: $org_id, statement: $existing_statement})
            OPTIONAL MATCH (existing)-[:CITED_BY]->(existing_ev:Evidence)
            MATCH (stored_work_pack:WorkPack {id: $work_pack_id, org_id: $org_id})
            RETURN proposal.status AS status,
                   proposal.entity_type AS entity_type,
                   proposal_evidence,
                   work_pack_links,
                   count(DISTINCT existing) AS existing_entities,
                   count(DISTINCT existing_ev) AS existing_evidence,
                   stored_work_pack.deviations AS deviations,
                   stored_work_pack.unresolved_questions AS unresolved_questions
            """,
            {
                "org_id": ORG_ID,
                "statement": STATEMENT,
                "existing_statement": EXISTING_STATEMENT,
                "work_pack_id": WORK_PACK_ID,
            },
        )
        assert verification == [{
            "status": "proposed",
            "entity_type": "Decision",
            "proposal_evidence": 1,
            "work_pack_links": 1,
            "existing_entities": 1,
            "existing_evidence": 1,
            "deviations": ["Used deterministic persistence instead of another LLM call."],
            "unresolved_questions": ["Should reports later support Goals as well?"],
        }], verification

        invalid_count = await GraphClient.run_query(
            "MATCH (entity:Entity {statement: $statement}) RETURN count(entity) AS count",
            {"statement": INVALID_STATEMENT},
        )
        assert invalid_count == [{"count": 0}], invalid_count
        print("MCP report_result E2E: OK")
    finally:
        await cleanup()
        await GraphClient.close()


if __name__ == "__main__":
    asyncio.run(run())
