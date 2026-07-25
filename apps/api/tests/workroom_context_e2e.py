"""E2E checks for governed Workroom context packs.

Proves the agent reads exactly the intersection of the caller's authorized
knowledge, the room's scope, and the room's context pack — and that an
inaccessible confidential source is never named in the preview.
"""

import asyncio
import os
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages"))

import httpx
from sqlalchemy import delete, select

import main
from core.graph import GraphClient
from database import (
    AuthIdentity,
    AuthSession,
    AuthSessionContext,
    GeneratedArtifact,
    Org,
    OrganizationMembership,
    PasswordCredential,
    User,
    Workroom,
    WorkroomContextItem,
    WorkroomEvent,
    WorkroomJob,
    WorkroomMember,
    WorkroomPlanVersion,
    WorkroomRun,
    WorkroomTask,
    async_session,
    init_db,
)
from workroom_agent import run_worker_loop


OWNER_EMAIL = "workroom-context-owner-e2e@example.com"
PASSWORD = "correct horse battery staple"


async def cleanup() -> None:
    async with async_session() as session:
        users = (
            await session.execute(select(User).where(User.email == OWNER_EMAIL))
        ).scalars().all()
        user_ids = [user.id for user in users]
        org_ids = list({user.org_id for user in users})

        if org_ids:
            for org_id in org_ids:
                await GraphClient.run_query(
                    "MATCH (node) WHERE node.org_id = $org_id DETACH DELETE node",
                    {"org_id": org_id},
                )
            for table in (
                WorkroomJob, WorkroomEvent, WorkroomRun, WorkroomTask,
                WorkroomPlanVersion, WorkroomContextItem, WorkroomMember, Workroom,
            ):
                await session.execute(
                    delete(table).where(table.org_id.in_(org_ids))
                )
        if user_ids:
            await session.execute(
                delete(GeneratedArtifact).where(
                    GeneratedArtifact.user_id.in_(user_ids)
                )
            )
            session_ids = list((
                await session.execute(
                    select(AuthSession.id).where(AuthSession.user_id.in_(user_ids))
                )
            ).scalars())
            if session_ids:
                await session.execute(
                    delete(AuthSessionContext).where(
                        AuthSessionContext.session_id.in_(session_ids)
                    )
                )
            for table in (
                AuthSession, PasswordCredential, AuthIdentity,
                OrganizationMembership,
            ):
                await session.execute(
                    delete(table).where(table.user_id.in_(user_ids))
                )
            await session.execute(delete(User).where(User.id.in_(user_ids)))
        if org_ids:
            await session.execute(delete(Org).where(Org.id.in_(org_ids)))
        await session.commit()


async def seed_graph(org_id: str) -> None:
    await GraphClient.run_query(
        """
        CREATE (launch:Entity {
            id: 'ctx-launch', org_id: $org_id, entity_type: 'Decision',
            statement: 'Launch the Northstar pilot in September.',
            status: 'confirmed', confidence: 'high', department_ids: [],
            created_at: datetime(), confirmed_at: datetime()
        })
        CREATE (scope:Entity {
            id: 'ctx-scope', org_id: $org_id, entity_type: 'Goal',
            statement: 'The Northstar pilot runs for four weeks.',
            status: 'confirmed', confidence: 'high', department_ids: [],
            created_at: datetime(), confirmed_at: datetime()
        })
        CREATE (stale:Entity {
            id: 'ctx-stale', org_id: $org_id, entity_type: 'Constraint',
            statement: 'The Northstar pilot uses the retired onboarding script.',
            status: 'confirmed', confidence: 'high', department_ids: [],
            created_at: datetime(), confirmed_at: datetime()
        })
        CREATE (secret:Entity {
            id: 'ctx-secret', org_id: $org_id, entity_type: 'Constraint',
            statement: 'The confidential board budget is 900000 euros.',
            status: 'confirmed', confidence: 'high', department_ids: ['board'],
            created_at: datetime(), confirmed_at: datetime()
        })
        CREATE (e1:Evidence {
            id: 'ctx-evidence-launch', org_id: $org_id, source: 'upload',
            title: 'Northstar plan', reference: 'northstar-plan.md',
            excerpt: 'Launch in September.', line_start: 12, line_end: 12,
            source_date: datetime()
        })
        CREATE (e2:Evidence {
            id: 'ctx-evidence-scope', org_id: $org_id, source: 'upload',
            title: 'Northstar plan', reference: 'northstar-plan.md',
            excerpt: 'The pilot lasts four weeks.', line_start: 18, line_end: 18,
            source_date: datetime()
        })
        CREATE (e3:Evidence {
            id: 'ctx-evidence-stale', org_id: $org_id, source: 'upload',
            title: 'Retired onboarding runbook', reference: 'retired-runbook.md',
            excerpt: 'Use the retired onboarding script.', line_start: 4, line_end: 4,
            source_date: datetime()
        })
        CREATE (e4:Evidence {
            id: 'ctx-evidence-secret', org_id: $org_id, source: 'upload',
            title: 'Confidential board budget', reference: 'board-budget.md',
            excerpt: 'Confidential budget.', department_id: 'board',
            source_date: datetime()
        })
        CREATE (launch)-[:CITED_BY]->(e1)
        CREATE (scope)-[:CITED_BY]->(e2)
        CREATE (stale)-[:CITED_BY]->(e3)
        CREATE (secret)-[:CITED_BY]->(e4)
        """,
        {"org_id": org_id},
    )


async def wait_for_run(client, org_id, room_id, run_id, expected) -> dict:
    for _ in range(120):
        response = await client.get(
            f"/workrooms/{room_id}", params={"org_id": org_id}
        )
        assert response.status_code == 200, response.text
        room = response.json()
        run = next((item for item in room["runs"] if item["id"] == run_id), None)
        if run and run["status"] == expected:
            return run
        if run and run["status"] == "failed":
            raise AssertionError(run)
        await asyncio.sleep(0.05)
    raise AssertionError(f"Run {run_id} never reached {expected}")


async def run() -> None:
    previous_mode = os.environ.get("KOMPONIST_AI_MODE")
    os.environ["KOMPONIST_AI_MODE"] = "mock"
    GraphClient.initialize()
    await init_db()
    await cleanup()
    transport = httpx.ASGITransport(app=main.app)

    worker_stop = asyncio.Event()
    worker_task = asyncio.create_task(
        run_worker_loop(
            worker_id="workroom-context-e2e",
            stop_event=worker_stop,
            poll_seconds=0.05,
        )
    )

    try:
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as owner_c:
            registered = await owner_c.post(
                "/auth/register",
                json={
                    "name": "Context Owner",
                    "email": OWNER_EMAIL,
                    "password": PASSWORD,
                },
            )
            assert registered.status_code == 201, registered.text
            owner = registered.json()["user"]
            org_id = owner["org_id"]
            await seed_graph(org_id)

            created = await owner_c.post(
                "/workrooms",
                params={"org_id": org_id},
                json={
                    "title": "Context room",
                    "objective": "Company overview for the Northstar pilot",
                    "department_ids": [],
                },
            )
            assert created.status_code == 201, created.text
            room_id = created.json()["id"]
            task_id = created.json()["tasks"][0]["id"]

            # --- Preview never names inaccessible knowledge ---------------
            preview = await owner_c.get(
                f"/workrooms/{room_id}/context", params={"org_id": org_id}
            )
            assert preview.status_code == 200, preview.text
            body = preview.json()
            assert body["confirmed_fact_count"] >= 3, body
            assert body["accessible_source_count"] >= 3, body
            serialized = str(body)
            assert "900000" not in serialized, "a confidential fact leaked"
            assert "board-budget" not in serialized, "a confidential source leaked"
            assert "Confidential board budget" not in serialized, serialized
            assert body["pinned"] == [] and body["excluded"] == [], body
            assert body["last_context_update_at"] is None, body
            print("✓ the preview never reveals inaccessible sources")

            # --- Excluding a source removes it from the agent's context ---
            excluded = await owner_c.post(
                f"/workrooms/{room_id}/context",
                params={"org_id": org_id},
                json={
                    "item_kind": "source",
                    "reference_id": "ctx-evidence-stale",
                    "mode": "exclude",
                    "label": "Retired runbook",
                },
            )
            assert excluded.status_code == 201, excluded.text

            pinned = await owner_c.post(
                f"/workrooms/{room_id}/context",
                params={"org_id": org_id},
                json={
                    "item_kind": "source",
                    "reference_id": "ctx-evidence-launch",
                    "mode": "include",
                    "label": "Launch decision",
                },
            )
            assert pinned.status_code == 201, pinned.text

            after = (await owner_c.get(
                f"/workrooms/{room_id}/context", params={"org_id": org_id}
            )).json()
            assert len(after["pinned"]) == 1, after["pinned"]
            assert len(after["excluded"]) == 1, after["excluded"]
            assert after["last_context_update_at"] is not None, after
            source_ids = [source["id"] for source in after["sources"]]
            assert "ctx-evidence-stale" not in source_ids, source_ids
            # A pinned source is guaranteed present and ranked first.
            assert source_ids[0] == "ctx-evidence-launch", source_ids
            assert after["sources"][0]["pinned"] is True, after["sources"][0]
            print("✓ pins rank first and exclusions are removed")

            # --- The run snapshot records exactly what was read -----------
            started = await owner_c.post(
                f"/workrooms/{room_id}/runs",
                params={"org_id": org_id},
                json={"task_id": task_id, "instruction": "Summarise the pilot."},
            )
            assert started.status_code == 202, started.text
            run_id = started.json()["id"]
            finished = await wait_for_run(
                owner_c, org_id, room_id, run_id, "awaiting_approval"
            )
            snapshot = finished["context_snapshot"]

            assert snapshot["entity_ids"], snapshot
            assert snapshot["evidence_ids"], snapshot
            assert "ctx-evidence-stale" not in snapshot["evidence_ids"], snapshot
            assert "ctx-secret" not in snapshot["entity_ids"], snapshot
            assert "ctx-evidence-secret" not in snapshot["evidence_ids"], snapshot

            # Every cited source carries a verifiable location and deep link.
            for source in snapshot["sources"]:
                assert source["id"], source
                assert source["excerpt"], source
                assert source["komponist_path"], source

            scope = snapshot["permission_scope"]
            assert scope["access_all_departments"] is False, scope
            assert scope["visibility"] == "organization", scope
            pack = snapshot["context_pack"]
            assert "ctx-evidence-stale" in pack["excluded_source_ids"], pack
            assert "ctx-evidence-launch" in pack["pinned_source_ids"], pack
            assert snapshot["captured_at"], snapshot
            assert "900000" not in str(snapshot), "a confidential fact leaked"
            print("✓ each run stores an immutable, permission-scoped snapshot")

            # --- Removing a rule restores the source ----------------------
            removed = await owner_c.delete(
                f"/workrooms/{room_id}/context/{excluded.json()['id']}",
                params={"org_id": org_id},
            )
            assert removed.status_code == 200, removed.text
            restored = (await owner_c.get(
                f"/workrooms/{room_id}/context", params={"org_id": org_id}
            )).json()
            assert "ctx-evidence-stale" in [
                source["id"] for source in restored["sources"]
            ], restored["sources"]
            print("✓ removing an exclusion restores the source")

            audit = await owner_c.get(
                f"/workrooms/{room_id}", params={"org_id": org_id}
            )
            assert any(
                event["event_type"] == "context_changed"
                for event in audit.json()["events"]
            ), audit.json()["events"]
            print("✓ context changes are audited")
    finally:
        worker_stop.set()
        try:
            await asyncio.wait_for(worker_task, timeout=10)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            worker_task.cancel()
        await cleanup()
        await GraphClient.close()
        if previous_mode is None:
            os.environ.pop("KOMPONIST_AI_MODE", None)
        else:
            os.environ["KOMPONIST_AI_MODE"] = previous_mode


if __name__ == "__main__":
    asyncio.run(run())
    print("Workroom context E2E: OK")
