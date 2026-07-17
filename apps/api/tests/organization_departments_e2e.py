"""E2E coverage for department organization and knowledge isolation."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from sqlalchemy import delete, select

import auth
import main
from core.graph import GraphClient
from database import (
    AuthIdentity,
    AuthSession,
    AuthSessionContext,
    ChatConversation,
    ChatMessageRecord,
    Department,
    DepartmentMembership,
    Org,
    OrganizationInvitation,
    OrganizationMembership,
    User,
    async_session,
    init_db,
)


OWNER_EMAIL = "department-owner-e2e@example.com"
MEMBER_EMAIL = "department-member-e2e@example.com"


def identity(subject: str, email: str, name: str) -> dict:
    return {
        "sub": subject,
        "email": email,
        "email_verified": True,
        "name": name,
    }


async def cleanup() -> None:
    async with async_session() as session:
        users = list(
            (
                await session.execute(
                    select(User).where(User.email.in_([OWNER_EMAIL, MEMBER_EMAIL]))
                )
            ).scalars()
        )
        user_ids = [user.id for user in users]
        org_ids = [user.org_id for user in users]
        if user_ids:
            session_ids = list(
                (
                    await session.execute(
                        select(AuthSession.id).where(AuthSession.user_id.in_(user_ids))
                    )
                ).scalars()
            )
            conversation_ids = list(
                (
                    await session.execute(
                        select(ChatConversation.id).where(
                            ChatConversation.user_id.in_(user_ids)
                        )
                    )
                ).scalars()
            )
            if conversation_ids:
                await session.execute(
                    delete(ChatMessageRecord).where(
                        ChatMessageRecord.conversation_id.in_(conversation_ids)
                    )
                )
            await session.execute(
                delete(ChatConversation).where(ChatConversation.user_id.in_(user_ids))
            )
            await session.execute(
                delete(DepartmentMembership).where(
                    DepartmentMembership.user_id.in_(user_ids)
                )
            )
            if session_ids:
                await session.execute(
                    delete(AuthSessionContext).where(
                        AuthSessionContext.session_id.in_(session_ids)
                    )
                )
            await session.execute(
                delete(AuthSession).where(AuthSession.user_id.in_(user_ids))
            )
            await session.execute(
                delete(AuthIdentity).where(AuthIdentity.user_id.in_(user_ids))
            )
            await session.execute(
                delete(OrganizationMembership).where(
                    OrganizationMembership.user_id.in_(user_ids)
                )
            )
            await session.execute(delete(User).where(User.id.in_(user_ids)))
        if org_ids:
            await session.execute(
                delete(DepartmentMembership).where(
                    DepartmentMembership.org_id.in_(org_ids)
                )
            )
            await session.execute(
                delete(Department).where(Department.org_id.in_(org_ids))
            )
            await session.execute(
                delete(OrganizationInvitation).where(
                    OrganizationInvitation.org_id.in_(org_ids)
                )
            )
            await session.execute(delete(Org).where(Org.id.in_(org_ids)))
        await session.commit()


async def seed_graph(org_id: str, department_a: str, department_b: str) -> None:
    await GraphClient.run_query(
        "MATCH (node) WHERE node.org_id = $org_id DETACH DELETE node",
        {"org_id": org_id},
    )
    await GraphClient.run_query(
        """
        CREATE (global:Entity:Goal {
            id: 'dept-global', org_id: $org_id, entity_type: 'Goal',
            statement: 'Organization-wide annual goal', status: 'confirmed',
            department_ids: [], created_at: datetime(), confirmed_at: datetime()
        })
        CREATE (a:Entity:Goal {
            id: 'dept-a', org_id: $org_id, entity_type: 'Goal',
            statement: 'Partnerships private goal', status: 'confirmed',
            department_ids: [$department_a], created_at: datetime(), confirmed_at: datetime()
        })
        CREATE (b:Entity:Goal {
            id: 'dept-b', org_id: $org_id, entity_type: 'Goal',
            statement: 'Events private goal', status: 'confirmed',
            department_ids: [$department_b], created_at: datetime(), confirmed_at: datetime()
        })
        CREATE (gev:Evidence {
            id: 'dept-global-evidence', org_id: $org_id, source: 'upload',
            reference: 'upload:global.md:test', excerpt: 'Global evidence',
            source_date: datetime()
        })
        CREATE (aev:Evidence {
            id: 'dept-a-evidence', org_id: $org_id, source: 'upload',
            reference: 'upload:partnerships.md:test', excerpt: 'Partnerships evidence',
            department_id: $department_a, source_date: datetime()
        })
        CREATE (bev:Evidence {
            id: 'dept-b-evidence', org_id: $org_id, source: 'upload',
            reference: 'upload:events.md:test', excerpt: 'Events evidence',
            department_id: $department_b, source_date: datetime()
        })
        CREATE (global)-[:CITED_BY]->(gev)
        CREATE (a)-[:CITED_BY]->(aev)
        CREATE (b)-[:CITED_BY]->(bev)
        """,
        {
            "org_id": org_id,
            "department_a": department_a,
            "department_b": department_b,
        },
    )


async def run() -> None:
    await init_db()
    GraphClient.initialize()
    await cleanup()
    owner = await auth.upsert_google_user(
        identity("department-owner-e2e", OWNER_EMAIL, "Initiative Owner")
    )
    member = await auth.upsert_google_user(
        identity("department-member-e2e", MEMBER_EMAIL, "Initiative Member")
    )
    owner_token, _ = await auth.create_session(owner.id)
    member_token, _ = await auth.create_session(member.id)
    transport = httpx.ASGITransport(app=main.app)

    try:
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as owner_client, httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as member_client:
            owner_client.cookies.set(auth.SESSION_COOKIE, owner_token)
            member_client.cookies.set(auth.SESSION_COOKIE, member_token)

            department_a_response = await owner_client.post(
                f"/auth/organizations/{owner.org_id}/departments",
                json={
                    "name": "Partnerships",
                    "description": "External relations",
                    "color": "orange",
                },
            )
            department_b_response = await owner_client.post(
                f"/auth/organizations/{owner.org_id}/departments",
                json={
                    "name": "Events",
                    "description": "Event delivery",
                    "color": "teal",
                },
            )
            assert department_a_response.status_code == 201, department_a_response.text
            assert department_b_response.status_code == 201, department_b_response.text
            department_a = department_a_response.json()["id"]
            department_b = department_b_response.json()["id"]

            invitation_response = await owner_client.post(
                f"/auth/organizations/{owner.org_id}/invitations",
                json={
                    "email": MEMBER_EMAIL,
                    "role": "member",
                    "department_ids": [department_a],
                },
            )
            assert invitation_response.status_code == 201, invitation_response.text
            accepted = await member_client.post(
                "/auth/invitations/accept",
                json={"token": invitation_response.json()["token"]},
            )
            assert accepted.status_code == 200, accepted.text
            assert accepted.json()["user"]["department_ids"] == [department_a]
            assert accepted.json()["user"]["access_all_departments"] is False

            await seed_graph(owner.org_id, department_a, department_b)

            owner_entities = await owner_client.get(
                "/entities", params={"org_id": owner.org_id, "status": "confirmed"}
            )
            assert owner_entities.status_code == 200, owner_entities.text
            assert {row["id"] for row in owner_entities.json()["entities"]} == {
                "dept-global", "dept-a", "dept-b"
            }

            member_entities = await member_client.get(
                "/entities", params={"org_id": owner.org_id, "status": "confirmed"}
            )
            assert member_entities.status_code == 200, member_entities.text
            assert {row["id"] for row in member_entities.json()["entities"]} == {
                "dept-global", "dept-a"
            }
            hidden_entity = await member_client.get(
                "/entities/dept-b", params={"org_id": owner.org_id}
            )
            assert hidden_entity.status_code == 404, hidden_entity.text
            member_graph = await member_client.get(
                "/graph", params={"org_id": owner.org_id}
            )
            assert member_graph.status_code == 200, member_graph.text
            assert {row["id"] for row in member_graph.json()["nodes"]} == {
                "dept-global", "dept-a"
            }
            member_graph_stats = await member_client.get(
                "/graph/stats", params={"org_id": owner.org_id}
            )
            assert member_graph_stats.status_code == 200, member_graph_stats.text
            assert member_graph_stats.json()["total_nodes"] == 2
            suggestions = await member_client.get(
                "/chat/suggestions", params={"org_id": owner.org_id, "limit": 8}
            )
            assert suggestions.status_code == 200, suggestions.text
            assert {
                item["reference"] for item in suggestions.json()["suggestions"]
            } <= {"upload:global.md:test", "upload:partnerships.md:test"}

            conversation = await main.create_chat_conversation(
                owner.org_id, member.id, "Scoped history"
            )
            await main.append_chat_message(
                owner.org_id,
                member.id,
                conversation["id"],
                "assistant",
                "Partnerships private goal",
            )

            members = await owner_client.get(
                f"/auth/organizations/{owner.org_id}/members"
            )
            member_row = next(
                row for row in members.json()["members"] if row["email"] == MEMBER_EMAIL
            )
            reorganized = await owner_client.patch(
                f"/auth/organizations/{owner.org_id}/members/{member_row['id']}",
                json={"role": "member", "department_ids": [department_b]},
            )
            assert reorganized.status_code == 200, reorganized.text

            member_entities = await member_client.get(
                "/entities", params={"org_id": owner.org_id, "status": "confirmed"}
            )
            assert {row["id"] for row in member_entities.json()["entities"]} == {
                "dept-global", "dept-b"
            }
            history = await member_client.get(
                "/chat/conversations", params={"org_id": owner.org_id}
            )
            assert history.json()["conversations"] == [], history.text

            merged = await owner_client.delete(
                f"/auth/organizations/{owner.org_id}/departments/{department_a}",
                params={"reassign_to": department_b},
            )
            assert merged.status_code == 200, merged.text
            moved = await GraphClient.run_query(
                """
                MATCH (evidence:Evidence {id: 'dept-a-evidence', org_id: $org_id})
                MATCH (entity:Entity {id: 'dept-a', org_id: $org_id})
                RETURN evidence.department_id AS department_id,
                       entity.department_ids AS department_ids
                """,
                {"org_id": owner.org_id},
            )
            assert moved[0]["department_id"] == department_b, moved
            assert moved[0]["department_ids"] == [department_b], moved

            removed = await owner_client.delete(
                f"/auth/organizations/{owner.org_id}/members/{member_row['id']}"
            )
            assert removed.status_code == 204, removed.text
            forbidden = await member_client.get(
                "/entities", params={"org_id": owner.org_id, "status": "confirmed"}
            )
            assert forbidden.status_code == 403, forbidden.text

        print("Organization departments and knowledge isolation E2E: OK")
    finally:
        await GraphClient.run_query(
            "MATCH (node) WHERE node.org_id = $org_id DETACH DELETE node",
            {"org_id": owner.org_id},
        )
        await cleanup()
        await GraphClient.close()


if __name__ == "__main__":
    asyncio.run(run())
