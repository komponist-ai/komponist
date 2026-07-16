"""E2E check for grounded chat and Evidence citations.

Run inside the API container while the stack is healthy:
    python tests/chat_e2e.py
"""

import asyncio

import httpx

from core.graph import GraphClient


ORG_ID = "e2e-chat"


async def seed() -> None:
    await GraphClient.run_query(
        "MATCH (n) WHERE n.org_id IN [$org_id, $other_org] DETACH DELETE n",
        {"org_id": ORG_ID, "other_org": f"{ORG_ID}-other"},
    )
    await GraphClient.run_query(
        """
        CREATE (confirmed:Entity:Decision {
            id: 'chat-confirmed', org_id: $org_id, entity_type: 'Decision',
            statement: 'Use Neo4j as the company brain database.',
            detail: 'Neo4j stores reviewed company knowledge.',
            status: 'confirmed', confidence: 'high',
            created_at: datetime(), updated_at: datetime(), confirmed_at: datetime()
        })
        CREATE (proposed:Entity:Goal {
            id: 'chat-proposed', org_id: $org_id, entity_type: 'Goal',
            statement: 'Launch the confidential Firefly initiative.',
            status: 'proposed', confidence: 'medium',
            created_at: datetime(), updated_at: datetime()
        })
        CREATE (other:Entity:Decision {
            id: 'chat-other-org', org_id: $other_org, entity_type: 'Decision',
            statement: 'Use Firestore as the company brain database.',
            status: 'confirmed', confidence: 'high',
            created_at: datetime(), updated_at: datetime(), confirmed_at: datetime()
        })
        CREATE (evidence:Evidence {
            id: 'chat-evidence', org_id: $org_id, source: 'local_docs',
            reference: 'architecture.md',
            url: 'https://example.com/architecture',
            excerpt: 'Decision: Use Neo4j as the company brain database.',
            source_date: datetime('2026-07-16T09:00:00Z'), created_at: datetime()
        })
        CREATE (confirmed)-[:CITED_BY]->(evidence)
        """,
        {"org_id": ORG_ID, "other_org": f"{ORG_ID}-other"},
    )


async def run() -> None:
    GraphClient.initialize()
    await seed()

    try:
        async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
            response = await client.post(
                "/chat",
                json={
                    "org_id": ORG_ID,
                    "message": "Which database do we use for the company brain?",
                    "stream": False,
                },
            )
            assert response.status_code == 200, response.text
            payload = response.json()
            assert "Neo4j" in payload["response"], payload
            assert "Firestore" not in payload["response"], payload
            assert len(payload["sources"]) == 1, payload
            source = payload["sources"][0]
            assert source["id"] == "chat-evidence", source
            assert source["entity_id"] == "chat-confirmed", source
            assert source["reference"] == "architecture.md", source
            assert source["url"] == "https://example.com/architecture", source

            proposed_only = await client.post(
                "/chat",
                json={
                    "org_id": ORG_ID,
                    "message": "What is the Firefly initiative?",
                    "stream": False,
                },
            )
            assert proposed_only.status_code == 200, proposed_only.text
            proposed_payload = proposed_only.json()
            assert proposed_payload["sources"] == [], proposed_payload
            assert "confidential" not in proposed_payload["response"], proposed_payload

            streamed = await client.post(
                "/chat",
                json={
                    "org_id": ORG_ID,
                    "message": "Tell me about Neo4j",
                    "stream": True,
                },
            )
            assert streamed.status_code == 200, streamed.text
            assert "event: message" in streamed.text, streamed.text
            assert "Neo4j" in streamed.text, streamed.text
            assert "event: sources" in streamed.text, streamed.text
            assert "chat-evidence" in streamed.text, streamed.text

        print("grounded chat E2E: OK")
    finally:
        await GraphClient.run_query(
            "MATCH (n) WHERE n.org_id IN [$org_id, $other_org] DETACH DELETE n",
            {"org_id": ORG_ID, "other_org": f"{ORG_ID}-other"},
        )
        await GraphClient.close()


if __name__ == "__main__":
    asyncio.run(run())
