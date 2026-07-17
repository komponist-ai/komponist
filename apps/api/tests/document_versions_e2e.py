"""Authenticated document lineage, demo, and semantic diff contract."""

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
    AuthSession, AuthSessionContext, ConnectedSource, Org,
    OrganizationMembership, PasswordCredential, User, async_session, init_db,
)


EMAIL = "document-versions-e2e@example.com"


async def cleanup() -> None:
    async with async_session() as session:
        user = (await session.execute(select(User).where(User.email == EMAIL))).scalar_one_or_none()
        if user is None:
            return
        await GraphClient.run_query(
            "MATCH (node) WHERE node.org_id = $org_id DETACH DELETE node",
            {"org_id": user.org_id},
        )
        session_ids = (await session.execute(select(AuthSession.id).where(AuthSession.user_id == user.id))).scalars().all()
        if session_ids:
            await session.execute(delete(AuthSessionContext).where(AuthSessionContext.session_id.in_(session_ids)))
        await session.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
        await session.execute(delete(PasswordCredential).where(PasswordCredential.user_id == user.id))
        await session.execute(delete(ConnectedSource).where(ConnectedSource.org_id == user.org_id))
        await session.execute(delete(OrganizationMembership).where(OrganizationMembership.user_id == user.id))
        await session.execute(delete(Org).where(Org.id == user.org_id))
        await session.execute(delete(User).where(User.id == user.id))
        await session.commit()


async def run() -> None:
    await init_db()
    await cleanup()
    user = await auth.register_password_user("Versions E2E", EMAIL, "document-versions-password")
    raw_session, _ = await auth.create_session(user.id)

    await GraphClient.run_query(
        """
        CREATE (project:Entity {
            id: 'versions-project', org_id: $org_id, entity_type: 'Project',
            statement: 'The Northstar pilot runs in Q3.', status: 'confirmed',
            confidence: 'high', created_at: datetime()
        })
        CREATE (oldGoal:Entity {
            id: 'versions-goal-old', org_id: $org_id, entity_type: 'Goal',
            statement: 'The Northstar pilot will run for six weeks.', status: 'confirmed',
            confidence: 'high', created_at: datetime()
        })
        CREATE (newGoal:Entity {
            id: 'versions-goal-new', org_id: $org_id, entity_type: 'Goal',
            statement: 'The Northstar pilot will run for four weeks.', status: 'proposed',
            confidence: 'medium', created_at: datetime()
        })
        CREATE (oldProjectEvidence:Evidence {
            id: 'versions-ev-1', org_id: $org_id, source: 'notion',
            title: 'Northstar Pilot Draft v1', reference: 'notion:northstar',
            author: 'Lena', content_hash: 'old-hash', family_key: 'northstar pilot',
            source_date: datetime('2026-07-01T10:00:00Z')
        })
        CREATE (oldGoalEvidence:Evidence {
            id: 'versions-ev-2', org_id: $org_id, source: 'notion',
            title: 'Northstar Pilot Draft v1', reference: 'notion:northstar',
            author: 'Lena', content_hash: 'old-hash', family_key: 'northstar pilot',
            source_date: datetime('2026-07-01T10:00:00Z')
        })
        CREATE (newProjectEvidence:Evidence {
            id: 'versions-ev-3', org_id: $org_id, source: 'google',
            title: 'Northstar Pilot FINAL v2', reference: 'gdrive:northstar',
            author: 'Alex', content_hash: 'new-hash', family_key: 'northstar pilot',
            source_date: datetime('2026-07-08T14:00:00Z')
        })
        CREATE (newGoalEvidence:Evidence {
            id: 'versions-ev-4', org_id: $org_id, source: 'google',
            title: 'Northstar Pilot FINAL v2', reference: 'gdrive:northstar',
            author: 'Alex', content_hash: 'new-hash', family_key: 'northstar pilot',
            source_date: datetime('2026-07-08T14:00:00Z')
        })
        CREATE (project)-[:CITED_BY]->(oldProjectEvidence)
        CREATE (project)-[:CITED_BY]->(newProjectEvidence)
        CREATE (oldGoal)-[:CITED_BY]->(oldGoalEvidence)
        CREATE (newGoal)-[:CITED_BY]->(newGoalEvidence)
        """,
        {"org_id": user.org_id},
    )

    transport = httpx.ASGITransport(app=main.app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as anonymous:
            denied = await anonymous.get("/versions", params={"org_id": user.org_id})
            assert denied.status_code == 401, denied.text

        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            client.cookies.set(auth.SESSION_COOKIE, raw_session)
            response = await client.get("/versions", params={"org_id": user.org_id})
            assert response.status_code == 200, response.text
            payload = response.json()
            assert payload["stats"]["workspace_families"] == 1, payload
            assert payload["stats"]["workspace_versions"] == 2, payload
            assert payload["families"][0]["is_demo"] is True, payload
            workspace = next(family for family in payload["families"] if not family["is_demo"])
            assert workspace["version_count"] == 2, workspace
            assert workspace["contributors"] == ["Alex", "Lena"], workspace
            assert workspace["latest_version_id"].startswith("legacy-"), workspace
            assert workspace["diff"]["counts"]["changed"] == 1, workspace
            assert workspace["diff"]["counts"]["conflicts"] == 1, workspace
            assert workspace["truth_status"] == "contested", workspace

            without_demo = await client.get(
                "/versions", params={"org_id": user.org_id, "include_demo": "false"}
            )
            assert without_demo.status_code == 200, without_demo.text
            assert len(without_demo.json()["families"]) == 1, without_demo.text

        print("Document versions E2E: OK")
    finally:
        await cleanup()


if __name__ == "__main__":
    asyncio.run(run())
