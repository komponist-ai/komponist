"""E2E check for grounded chat and Evidence citations.

Run inside the API container while the stack is healthy:
    python tests/chat_e2e.py
"""

import asyncio

import httpx
from sqlalchemy import delete, select

from core.graph import GraphClient
from database import (
    AuthSession, AuthSessionContext, ChatConversation, ChatMessageRecord, Org,
    OrganizationMembership, PasswordCredential, User, async_session,
)


ORG_ID = "e2e-chat"
EMAIL = "grounded-chat-e2e@example.com"
PASSWORD = "correct horse battery staple"


async def cleanup_user() -> None:
    async with async_session() as session:
        user = (
            await session.execute(select(User).where(User.email == EMAIL))
        ).scalar_one_or_none()
        if user is None:
            return
        conversation_ids = (
            await session.execute(
                select(ChatConversation.id).where(ChatConversation.user_id == user.id)
            )
        ).scalars().all()
        if conversation_ids:
            await session.execute(
                delete(ChatMessageRecord).where(
                    ChatMessageRecord.conversation_id.in_(conversation_ids)
                )
            )
        await session.execute(
            delete(ChatConversation).where(ChatConversation.user_id == user.id)
        )
        session_ids = (
            await session.execute(
                select(AuthSession.id).where(AuthSession.user_id == user.id)
            )
        ).scalars().all()
        if session_ids:
            await session.execute(
                delete(AuthSessionContext).where(
                    AuthSessionContext.session_id.in_(session_ids)
                )
            )
        await session.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
        await session.execute(delete(PasswordCredential).where(PasswordCredential.user_id == user.id))
        await session.execute(delete(OrganizationMembership).where(OrganizationMembership.user_id == user.id))
        org = await session.get(Org, user.org_id)
        await session.delete(user)
        if org is not None:
            await session.delete(org)
        await session.commit()


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
        CREATE (pilot:Entity:Project {
            id: 'chat-northstar-pilot', org_id: $org_id, entity_type: 'Project',
            statement: 'Run a four-week Northstar Labs design-partner pilot with weekly feedback sessions.',
            detail: 'The platform engineering team participates in the pilot.',
            status: 'confirmed', confidence: 'high',
            created_at: datetime(), updated_at: datetime(), confirmed_at: datetime()
        })
        CREATE (pilot_evidence:Evidence {
            id: 'chat-pilot-evidence', org_id: $org_id, source: 'upload',
            reference: 'upload:03-customer-interview.txt:e2e',
            url: 'upload://03-customer-interview.txt',
            excerpt: 'Project: Run a four-week Northstar Labs design-partner pilot with weekly feedback sessions.',
            source_date: datetime('2026-07-15T09:00:00Z'), created_at: datetime()
        })
        CREATE (pilot)-[:CITED_BY]->(pilot_evidence)
        CREATE (goal_one:Entity:Goal {
            id: 'chat-goal-one', org_id: $org_id, entity_type: 'Goal',
            statement: 'Reduce repeated architecture questions by 50 percent.',
            status: 'confirmed', confidence: 'high',
            created_at: datetime(), updated_at: datetime(), confirmed_at: datetime()
        })
        CREATE (goal_two:Entity:Goal {
            id: 'chat-goal-two', org_id: $org_id, entity_type: 'Goal',
            statement: 'Recruit ten weekly design partners.',
            status: 'confirmed', confidence: 'high',
            created_at: datetime(), updated_at: datetime(), confirmed_at: datetime()
        })
        CREATE (goal_one_evidence:Evidence {
            id: 'chat-goal-one-evidence', org_id: $org_id, source: 'upload',
            reference: 'upload:03-customer-interview.txt:e2e',
            excerpt: 'Goal: Reduce repeated architecture questions by 50 percent.',
            created_at: datetime()
        })
        CREATE (goal_two_evidence:Evidence {
            id: 'chat-goal-two-evidence', org_id: $org_id, source: 'upload',
            reference: 'upload:01-product-strategy.md:e2e',
            excerpt: 'Goal: Recruit ten weekly design partners.',
            created_at: datetime()
        })
        CREATE (goal_one)-[:CITED_BY]->(goal_one_evidence)
        CREATE (goal_two)-[:CITED_BY]->(goal_two_evidence)
        """,
        {"org_id": ORG_ID, "other_org": f"{ORG_ID}-other"},
    )


async def run() -> None:
    global ORG_ID
    GraphClient.initialize()
    await cleanup_user()

    try:
        async with httpx.AsyncClient(
            base_url="http://localhost:8000",
            timeout=httpx.Timeout(120.0),
        ) as client:
            registration = await client.post(
                "/auth/register",
                json={"name": "Grounded Chat", "email": EMAIL, "password": PASSWORD},
            )
            assert registration.status_code == 201, registration.text
            ORG_ID = registration.json()["user"]["org_id"]
            await seed()

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

            duration = await client.post(
                "/chat",
                json={
                    "org_id": ORG_ID,
                    "message": "Wie lange geht der Northstar Pilot?",
                    "stream": False,
                },
            )
            assert duration.status_code == 200, duration.text
            duration_payload = duration.json()
            assert "4 weeks" in duration_payload["response"], duration_payload
            assert "[1]" in duration_payload["response"], duration_payload
            assert duration_payload["sources"][0]["id"] == "chat-pilot-evidence", duration_payload

            count_goals = await client.post(
                "/chat",
                json={
                    "org_id": ORG_ID,
                    "message": "Give me the total number of objectives in our brain.",
                    "stream": False,
                },
            )
            assert count_goals.status_code == 200, count_goals.text
            count_payload = count_goals.json()
            assert "2 confirmed goals" in count_payload["response"], count_payload
            assert len(count_payload["sources"]) == 2, count_payload
            assert "confidential" not in count_payload["response"], count_payload

            mixed_counts = await client.post(
                "/chat",
                json={
                    "org_id": ORG_ID,
                    "message": (
                        "How many decisions, goals, constraints, and projects do we have?"
                    ),
                    "stream": False,
                },
            )
            mixed_payload = mixed_counts.json()
            assert "1 decision" in mixed_payload["response"], mixed_payload
            assert "2 goals" in mixed_payload["response"], mixed_payload
            assert "0 constraints" in mixed_payload["response"], mixed_payload
            assert "1 project" in mixed_payload["response"], mixed_payload

            goals_by_source = await client.post(
                "/chat",
                json={
                    "org_id": ORG_ID,
                    "message": "Which documents contain the most objectives?",
                    "stream": False,
                },
            )
            source_count_payload = goals_by_source.json()
            assert "Confirmed goals by source" in source_count_payload["response"], source_count_payload
            assert "Customer Interview: 1" in source_count_payload["response"], source_count_payload
            assert "Product Strategy: 1" in source_count_payload["response"], source_count_payload

            all_goals = await client.post(
                "/chat",
                json={
                    "org_id": ORG_ID,
                    "message": "List every confirmed objective.",
                    "stream": False,
                },
            )
            all_goals_payload = all_goals.json()
            assert "50" in all_goals_payload["response"], all_goals_payload
            assert any(
                value in all_goals_payload["response"].lower()
                for value in ("10", "ten")
            ), all_goals_payload
            assert len(all_goals_payload["sources"]) == 2, all_goals_payload

            follow_up = await client.post(
                "/chat",
                json={
                    "org_id": ORG_ID,
                    "message": "How long is it?",
                    "conversation_history": [
                        {
                            "role": "user",
                            "content": "Tell me about the Northstar Labs pilot.",
                        },
                        {
                            "role": "assistant",
                            "content": "It is a design-partner pilot.",
                        },
                    ],
                    "stream": False,
                },
            )
            follow_up_payload = follow_up.json()
            assert "4 weeks" in follow_up_payload["response"], follow_up_payload
            assert follow_up_payload["sources"][0]["id"] == "chat-pilot-evidence"

            german_duration = await client.post(
                "/chat",
                json={
                    "org_id": ORG_ID,
                    "message": "Antworte auf Deutsch: Wie lange geht der Northstar Pilot?",
                    "stream": False,
                },
            )
            german_payload = german_duration.json()
            assert "4 Wochen" in german_payload["response"], german_payload

            suggestions = await client.get(
                "/chat/suggestions",
                params={"org_id": ORG_ID, "limit": 4},
            )
            assert suggestions.status_code == 200, suggestions.text
            suggestion_payload = suggestions.json()["suggestions"]
            assert any(
                "How long" in item["prompt"] and "Northstar" in item["prompt"]
                for item in suggestion_payload
            ), suggestion_payload

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
        await cleanup_user()
        await GraphClient.close()


if __name__ == "__main__":
    asyncio.run(run())
