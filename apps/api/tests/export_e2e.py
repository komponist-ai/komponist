"""Authenticated workspace export contract and rejected-data filtering."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
import yaml
from sqlalchemy import delete, select

import auth
import main
from core.graph import GraphClient
from database import (
    AuthSession,
    AuthSessionContext,
    Org,
    OrganizationMembership,
    PasswordCredential,
    User,
    async_session,
    init_db,
)


EMAIL = "export-e2e@example.com"
PASSWORD = "export-e2e-password"


async def cleanup() -> None:
    async with async_session() as session:
        user = (
            await session.execute(select(User).where(User.email == EMAIL))
        ).scalar_one_or_none()
        if user is None:
            return
        await GraphClient.run_query(
            "MATCH (node) WHERE node.org_id = $org_id DETACH DELETE node",
            {"org_id": user.org_id},
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
        await session.execute(delete(Org).where(Org.id == user.org_id))
        await session.execute(delete(User).where(User.id == user.id))
        await session.commit()


async def run() -> None:
    await init_db()
    await cleanup()
    user = await auth.register_password_user("Export E2E", EMAIL, PASSWORD)
    raw_session, _ = await auth.create_session(user.id)

    await GraphClient.run_query(
        """
        CREATE (confirmed:Entity {
            id: 'export-confirmed', org_id: $org_id, entity_type: 'Decision',
            statement: 'Export confirmed knowledge.', status: 'confirmed',
            confidence: 'high', created_at: datetime(), confirmed_at: datetime()
        })
        CREATE (proposed:Entity {
            id: 'export-proposed', org_id: $org_id, entity_type: 'Goal',
            statement: 'Export proposed knowledge.', status: 'proposed',
            confidence: 'medium', created_at: datetime()
        })
        CREATE (rejected:Entity {
            id: 'export-rejected', org_id: $org_id, entity_type: 'Constraint',
            statement: 'Keep rejected knowledge out by default.', status: 'rejected',
            confidence: 'low', created_at: datetime()
        })
        CREATE (evidence:Evidence {
            id: 'export-evidence', org_id: $org_id, source: 'upload',
            title: 'export-policy.md', reference: 'upload:export-policy.md:e2e',
            excerpt: 'Decision: Export confirmed knowledge.', source_date: datetime()
        })
        CREATE (confirmed)-[:CITED_BY]->(evidence)
        CREATE (confirmed)-[:ADVANCES {score: 0.9}]->(proposed)
        CREATE (confirmed)-[:RELATES_TO {score: 0.4}]->(rejected)
        """,
        {"org_id": user.org_id},
    )

    transport = httpx.ASGITransport(app=main.app)
    try:
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            unauthenticated = await client.get(
                "/export/summary", params={"org_id": user.org_id}
            )
            assert unauthenticated.status_code == 401, unauthenticated.text

            client.cookies.set(auth.SESSION_COOKIE, raw_session)
            summary = await client.get(
                "/export/summary", params={"org_id": user.org_id}
            )
            assert summary.status_code == 200, summary.text
            summary_payload = summary.json()
            assert summary_payload["entities"] == {
                "total": 3, "confirmed": 1, "proposed": 1, "rejected": 1
            }, summary_payload
            assert summary_payload["relationships"] == 2, summary_payload
            assert summary_payload["evidence"] == 1, summary_payload

            exported = await client.get(
                "/export", params={"org_id": user.org_id}
            )
            assert exported.status_code == 200, exported.text
            assert exported.headers["content-type"].startswith("application/x-yaml")
            assert "komponist-export-" in exported.headers["content-disposition"]
            payload = yaml.safe_load(exported.text)
            assert payload["komponist_export"]["counts"]["entities"] == 2, payload
            assert payload["komponist_export"]["counts"]["relationships"] == 1, payload
            assert {entity["id"] for entity in payload["entities"]} == {
                "export-confirmed", "export-proposed"
            }
            confirmed = next(
                entity for entity in payload["entities"]
                if entity["id"] == "export-confirmed"
            )
            assert confirmed["evidence"][0]["title"] == "export-policy.md"

            with_rejected = await client.get(
                "/export",
                params={"org_id": user.org_id, "include_rejected": "true"},
            )
            rejected_payload = yaml.safe_load(with_rejected.text)
            assert rejected_payload["komponist_export"]["counts"]["entities"] == 3
            assert rejected_payload["komponist_export"]["counts"]["relationships"] == 2

            client.cookies.clear()
            blocked_import = await client.post(
                "/import",
                params={"org_id": user.org_id},
                files={"file": ("export.yaml", exported.content, "application/x-yaml")},
            )
            assert blocked_import.status_code == 401, blocked_import.text

        print("Workspace export E2E: OK")
    finally:
        await cleanup()


if __name__ == "__main__":
    asyncio.run(run())
