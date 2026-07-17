"""E2E coverage for centrally managed AI status and organization API keys."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from sqlalchemy import delete, select

import auth
import main
from database import (
    ApprovalRequest,
    AuthSession,
    AuthSessionContext,
    Org,
    OrganizationApiKey,
    OrganizationMembership,
    PasswordCredential,
    User,
    async_session,
    init_db,
)
from core.graph import GraphClient
from persistence import authenticate_api_key


EMAIL = "platform-api-e2e@example.com"


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
        sessions = (
            await session.execute(
                select(AuthSession.id).where(AuthSession.user_id == user.id)
            )
        ).scalars().all()
        if sessions:
            await session.execute(
                delete(AuthSessionContext).where(
                    AuthSessionContext.session_id.in_(sessions)
                )
            )
        await session.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
        await session.execute(delete(PasswordCredential).where(PasswordCredential.user_id == user.id))
        await session.execute(delete(OrganizationApiKey).where(OrganizationApiKey.org_id == user.org_id))
        await session.execute(delete(ApprovalRequest).where(ApprovalRequest.org_id == user.org_id))
        await session.execute(delete(OrganizationMembership).where(OrganizationMembership.user_id == user.id))
        await session.execute(delete(User).where(User.id == user.id))
        await session.execute(delete(Org).where(Org.id == user.org_id))
        await session.commit()


async def run() -> None:
    GraphClient.initialize()
    await init_db()
    await cleanup()
    user = await auth.register_password_user(
        "Platform E2E", EMAIL, "platform-e2e-password"
    )
    raw_session, _ = await auth.create_session(user.id)
    transport = httpx.ASGITransport(app=main.app)
    try:
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            client.cookies.set(auth.SESSION_COOKIE, raw_session)

            ai_status = await client.get(
                "/settings/ai", params={"org_id": user.org_id}
            )
            assert ai_status.status_code == 200, ai_status.text
            assert ai_status.json()["managed_by"] == "komponist"
            assert "api_key" not in ai_status.text

            created = await client.post(
                f"/auth/organizations/{user.org_id}/api-keys",
                json={"name": "E2E agent"},
            )
            assert created.status_code == 201, created.text
            key = created.json()["key"]
            key_id = created.json()["id"]
            assert key.startswith("komponist_sk_")
            assert await authenticate_api_key(key) == user.org_id

            await GraphClient.run_query(
                """
                CREATE (project:Entity:Project {
                    id: 'api-e2e-project', org_id: $org_id,
                    entity_type: 'Project', statement: 'ApiNebula launch',
                    status: 'confirmed', confirmed_at: datetime(), created_at: datetime()
                })
                CREATE (scoped:Entity:Decision {
                    id: 'api-e2e-scoped', org_id: $org_id,
                    entity_type: 'Decision', statement: 'Use ApiNebula for launch auth.',
                    status: 'confirmed', confirmed_at: datetime(), created_at: datetime()
                })
                CREATE (global:Entity:Decision {
                    id: 'api-e2e-global', org_id: $org_id,
                    entity_type: 'Decision', statement: 'Document ApiNebula rollbacks.',
                    status: 'confirmed', confirmed_at: datetime(), created_at: datetime()
                })
                CREATE (orphan:Entity:Decision {
                    id: 'api-e2e-orphan', org_id: $org_id,
                    entity_type: 'Decision', statement: 'ApiNebula without evidence.',
                    status: 'confirmed', confirmed_at: datetime(), created_at: datetime()
                })
                CREATE (proposed:Entity:Decision {
                    id: 'api-e2e-proposed', org_id: $org_id,
                    entity_type: 'Decision', statement: 'Unreviewed ApiNebula change.',
                    status: 'proposed', created_at: datetime()
                })
                CREATE (scoped_ev:Evidence {
                    id: 'api-e2e-scoped-ev', org_id: $org_id, source: 'e2e',
                    reference: 'api.md', excerpt: 'Use ApiNebula for launch auth.'
                })
                CREATE (global_ev:Evidence {
                    id: 'api-e2e-global-ev', org_id: $org_id, source: 'e2e',
                    reference: 'rollbacks.md', excerpt: 'Document ApiNebula rollbacks.'
                })
                CREATE (proposed_ev:Evidence {
                    id: 'api-e2e-proposed-ev', org_id: $org_id, source: 'e2e',
                    reference: 'draft.md', excerpt: 'This must stay private.'
                })
                CREATE (scoped)-[:CITED_BY]->(scoped_ev)
                CREATE (global)-[:CITED_BY]->(global_ev)
                CREATE (proposed)-[:CITED_BY]->(proposed_ev)
                """,
                {"org_id": user.org_id},
            )

            stats_without_edges = await client.get(
                "/graph/stats", params={"org_id": user.org_id}
            )
            assert stats_without_edges.status_code == 200, stats_without_edges.text
            assert stats_without_edges.json()["total_nodes"] == 5, stats_without_edges.text
            assert stats_without_edges.json()["total_edges"] == 0, stats_without_edges.text

            await GraphClient.run_query(
                """
                MATCH (decision:Entity {id: 'api-e2e-scoped', org_id: $org_id})
                MATCH (project:Entity {id: 'api-e2e-project', org_id: $org_id})
                CREATE (decision)-[:AFFECTS]->(project)
                """,
                {"org_id": user.org_id},
            )

            api_headers = {"Authorization": f"Bearer {key}"}
            context = await client.get(
                "/v1/context",
                params=[("query", "ApiNebula"), ("types", "Decision")],
                headers=api_headers,
            )
            assert context.status_code == 200, context.text
            context_ids = {item["id"] for item in context.json()["items"]}
            assert context_ids == {"api-e2e-scoped", "api-e2e-global"}, context.text
            assert all(item["evidence"] for item in context.json()["items"])

            decisions = await client.get(
                "/v1/decisions",
                params={"project_id": "api-e2e-project"},
                headers=api_headers,
            )
            assert decisions.status_code == 200, decisions.text
            assert [item["id"] for item in decisions.json()["decisions"]] == [
                "api-e2e-scoped"
            ], decisions.text

            brain = await client.get("/v1/brain", headers=api_headers)
            assert brain.status_code == 200, brain.text
            assert brain.json()["organization_id"] == user.org_id

            invalid_type = await client.get(
                "/v1/context",
                params=[("query", "ApiNebula"), ("types", "Person")],
                headers=api_headers,
            )
            assert invalid_type.status_code == 400, invalid_type.text

            async with async_session() as session:
                session.add(ApprovalRequest(
                    id="api-e2e-approval",
                    org_id=user.org_id,
                    action="Publish ApiNebula",
                    constraint_id="api-e2e-constraint",
                    constraint_statement="Publishing requires approval.",
                    context="Programmatic API E2E",
                    status="pending",
                ))
                await session.commit()

            approvals = await client.get(
                "/approvals", params={"org_id": user.org_id, "status": "pending"}
            )
            assert approvals.status_code == 200, approvals.text
            assert approvals.json()["total"] == 1, approvals.text
            resolved = await client.post(
                "/approvals/api-e2e-approval/resolve",
                params={"org_id": user.org_id},
                json={"approved": True},
            )
            assert resolved.status_code == 200, resolved.text
            assert resolved.json()["status"] == "approved", resolved.text
            second_resolution = await client.post(
                "/approvals/api-e2e-approval/resolve",
                params={"org_id": user.org_id},
                json={"approved": False},
            )
            assert second_resolution.json()["status"] == "approved", second_resolution.text

            unsigned_webhook = await client.post(
                "/webhooks/github",
                params={"org_id": user.org_id},
                json={"action": "closed"},
            )
            assert unsigned_webhook.status_code == 401, unsigned_webhook.text

            listed = await client.get(
                f"/auth/organizations/{user.org_id}/api-keys"
            )
            assert key not in listed.text
            assert listed.json()["keys"][0]["last_used_at"] is not None

            revoked = await client.delete(
                f"/auth/organizations/{user.org_id}/api-keys/{key_id}"
            )
            assert revoked.status_code == 204, revoked.text
            assert await authenticate_api_key(key) is None
            revoked_context = await client.get(
                "/v1/context", params={"query": "ApiNebula"}, headers=api_headers
            )
            assert revoked_context.status_code == 401, revoked_context.text

            client.cookies.clear()
            protected_reads = [
                ("/queue", {}),
                ("/entities", {}),
                ("/sources", {}),
                ("/graph", {}),
                ("/graph/stats", {}),
                ("/settings", {}),
                ("/approvals", {}),
                ("/export/summary", {}),
                ("/connectors/local-docs/status", {}),
            ]
            for path, extra_params in protected_reads:
                response = await client.get(
                    path, params={"org_id": user.org_id, **extra_params}
                )
                assert response.status_code == 401, (path, response.text)

        print("Platform AI and API keys E2E: OK")
    finally:
        await cleanup()
        await GraphClient.close()


if __name__ == "__main__":
    asyncio.run(run())
