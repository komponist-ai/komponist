"""Authenticated document inventory and Komponist-only deletion contract."""

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
    AuthSession,
    AuthSessionContext,
    ConnectedSource,
    Org,
    OrganizationMembership,
    PasswordCredential,
    User,
    async_session,
    init_db,
)
from persistence import create_connected_source


EMAIL = "source-documents-e2e@example.com"
PASSWORD = "source-documents-e2e-password"


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
        await session.execute(delete(ConnectedSource).where(ConnectedSource.org_id == user.org_id))
        await session.execute(delete(OrganizationMembership).where(OrganizationMembership.user_id == user.id))
        await session.execute(delete(Org).where(Org.id == user.org_id))
        await session.execute(delete(User).where(User.id == user.id))
        await session.commit()


async def run() -> None:
    await init_db()
    await cleanup()
    user = await auth.register_password_user("Source Documents E2E", EMAIL, PASSWORD)
    raw_session, _ = await auth.create_session(user.id)
    source = await create_connected_source(
        user.org_id, "upload", "Document Uploads", {}
    )
    reference = "upload:source-inventory.md:e2e123"

    await GraphClient.run_query(
        """
        CREATE (only:Entity {
            id: 'source-doc-only', org_id: $org_id, entity_type: 'Decision',
            statement: 'Delete me with my only document.', status: 'confirmed',
            created_at: datetime()
        })
        CREATE (shared:Entity {
            id: 'source-doc-shared', org_id: $org_id, entity_type: 'Goal',
            statement: 'Keep me because another source remains.', status: 'proposed',
            created_at: datetime()
        })
        CREATE (first:Evidence {
            id: 'source-doc-ev-1', org_id: $org_id, source: 'upload',
            reference: $reference, url: 'upload://source-inventory.md',
            source_date: datetime()
        })
        CREATE (second:Evidence {
            id: 'source-doc-ev-2', org_id: $org_id, source: 'upload',
            reference: $reference, url: 'upload://source-inventory.md',
            source_date: datetime()
        })
        CREATE (remaining:Evidence {
            id: 'source-doc-ev-3', org_id: $org_id, source: 'manual',
            reference: 'local:remaining.md', url: 'file:///remaining.md',
            source_date: datetime()
        })
        CREATE (only)-[:CITED_BY]->(first)
        CREATE (shared)-[:CITED_BY]->(second)
        CREATE (shared)-[:CITED_BY]->(remaining)
        """,
        {"org_id": user.org_id, "reference": reference},
    )

    transport = httpx.ASGITransport(app=main.app)
    try:
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            client.cookies.set(auth.SESSION_COOKIE, raw_session)

            inventory = await client.get(
                f"/sources/{source['id']}/documents",
                params={"org_id": user.org_id},
            )
            assert inventory.status_code == 200, inventory.text
            document = inventory.json()["documents"][0]
            assert document["title"] == "source-inventory.md", document
            assert document["entity_count"] == 2, document
            assert document["review_status"] == "mixed", document

            removed = await client.delete(
                f"/sources/{source['id']}/documents",
                params={"org_id": user.org_id, "reference": reference},
            )
            assert removed.status_code == 200, removed.text
            payload = removed.json()
            assert payload["platform_unchanged"] is True, payload
            assert payload["evidence_deleted"] == 2, payload
            assert payload["entities_deleted"] == 1, payload

            await GraphClient.run_query(
                """
                MATCH (shared:Entity {id: 'source-doc-shared', org_id: $org_id})
                CREATE (upload_ev:Evidence {
                    id: 'source-doc-ev-4', org_id: $org_id, source: 'upload',
                    reference: 'upload:second.md:e2e456', url: 'upload://second.md',
                    source_date: datetime()
                })
                CREATE (shared)-[:CITED_BY]->(upload_ev)
                """,
                {"org_id": user.org_id},
            )
            removed_source = await client.delete(
                f"/sources/{source['id']}",
                params={"org_id": user.org_id, "remove_data": True},
            )
            assert removed_source.status_code == 200, removed_source.text
            assert removed_source.json()["evidence_deleted"] == 1, removed_source.text
            assert removed_source.json()["entities_deleted"] == 0, removed_source.text

        remaining = await GraphClient.run_query(
            """
            MATCH (entity:Entity {org_id: $org_id})
            RETURN collect(entity.id) AS ids
            """,
            {"org_id": user.org_id},
        )
        assert remaining[0]["ids"] == ["source-doc-shared"], remaining
        print("Source documents E2E: OK")
    finally:
        await cleanup()


if __name__ == "__main__":
    asyncio.run(run())
