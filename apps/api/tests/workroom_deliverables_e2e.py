"""E2E checks for deliverables shared with a Workroom.

The property under test: two authorized participants open the same artifact,
while an unauthorized organization member, another organization, and every
pre-existing private deliverable remain unaffected.
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
    WorkroomArtifact,
    WorkroomContextItem,
    WorkroomEvent,
    WorkroomJob,
    WorkroomMember,
    WorkroomMessage,
    WorkroomPlanVersion,
    WorkroomRun,
    WorkroomTask,
    async_session,
    init_db,
)
from workroom_agent import run_worker_loop


OWNER_EMAIL = "workroom-deliverables-owner-e2e@example.com"
PARTICIPANT_EMAIL = "workroom-deliverables-participant-e2e@example.com"
OUTSIDER_EMAIL = "workroom-deliverables-outsider-e2e@example.com"
FOREIGN_EMAIL = "workroom-deliverables-foreign-e2e@example.com"
PASSWORD = "correct horse battery staple"
EMAILS = [OWNER_EMAIL, PARTICIPANT_EMAIL, OUTSIDER_EMAIL, FOREIGN_EMAIL]


async def cleanup() -> None:
    async with async_session() as session:
        users = (
            await session.execute(select(User).where(User.email.in_(EMAILS)))
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
                WorkroomJob, WorkroomArtifact, WorkroomMessage, WorkroomEvent,
                WorkroomRun, WorkroomTask, WorkroomPlanVersion,
                WorkroomContextItem, WorkroomMember, Workroom,
            ):
                await session.execute(
                    delete(table).where(table.org_id.in_(org_ids))
                )
            await session.execute(
                delete(GeneratedArtifact).where(
                    GeneratedArtifact.org_id.in_(org_ids)
                )
            )
        if user_ids:
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
        CREATE (decision:Entity {
            id: 'deliv-decision', org_id: $org_id, entity_type: 'Decision',
            statement: 'Launch the Northstar pilot in September.',
            status: 'confirmed', confidence: 'high', department_ids: [],
            created_at: datetime(), confirmed_at: datetime()
        })
        CREATE (goal:Entity {
            id: 'deliv-goal', org_id: $org_id, entity_type: 'Goal',
            statement: 'The Northstar pilot runs for four weeks.',
            status: 'confirmed', confidence: 'high', department_ids: [],
            created_at: datetime(), confirmed_at: datetime()
        })
        CREATE (e1:Evidence {
            id: 'deliv-evidence-1', org_id: $org_id, source: 'upload',
            title: 'Northstar plan', reference: 'northstar-plan.md',
            excerpt: 'Launch in September.', line_start: 12, line_end: 12,
            source_date: datetime()
        })
        CREATE (e2:Evidence {
            id: 'deliv-evidence-2', org_id: $org_id, source: 'upload',
            title: 'Northstar plan', reference: 'northstar-plan.md',
            excerpt: 'The pilot lasts four weeks.', line_start: 18, line_end: 18,
            source_date: datetime()
        })
        CREATE (decision)-[:CITED_BY]->(e1)
        CREATE (goal)-[:CITED_BY]->(e2)
        """,
        {"org_id": org_id},
    )


async def wait_for_run(client, org_id, room_id, run_id, expected) -> dict:
    for _ in range(160):
        response = await client.get(
            f"/workrooms/{room_id}", params={"org_id": org_id}
        )
        assert response.status_code == 200, response.text
        run = next(
            (item for item in response.json()["runs"] if item["id"] == run_id), None
        )
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
            worker_id="workroom-deliverables-e2e",
            stop_event=worker_stop,
            poll_seconds=0.05,
        )
    )

    def client() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=transport, base_url="http://testserver")

    try:
        async with client() as owner_c, client() as participant_c, \
                client() as outsider_c, client() as foreign_c:
            owner = (await owner_c.post(
                "/auth/register",
                json={"name": "Deliv Owner", "email": OWNER_EMAIL, "password": PASSWORD},
            )).json()["user"]
            participant = (await participant_c.post(
                "/auth/register",
                json={
                    "name": "Deliv Participant",
                    "email": PARTICIPANT_EMAIL,
                    "password": PASSWORD,
                },
            )).json()["user"]
            outsider = (await outsider_c.post(
                "/auth/register",
                json={
                    "name": "Deliv Outsider",
                    "email": OUTSIDER_EMAIL,
                    "password": PASSWORD,
                },
            )).json()["user"]
            await foreign_c.post(
                "/auth/register",
                json={
                    "name": "Foreign Org",
                    "email": FOREIGN_EMAIL,
                    "password": PASSWORD,
                },
            )
            org_id = owner["org_id"]
            await seed_graph(org_id)

            async with async_session() as session:
                for member in (participant, outsider):
                    session.add(OrganizationMembership(
                        id=str(uuid4()),
                        user_id=member["id"],
                        org_id=org_id,
                        role="member",
                        status="active",
                    ))
                await session.commit()

            # A private deliverable created before any sharing exists.
            private = await owner_c.post(
                "/artifacts/generate",
                params={"org_id": org_id},
                json={
                    "artifact_type": "summary",
                    "topic": "Northstar pilot overview",
                    "audience": "Leadership team",
                    "instructions": "",
                    "language": "english",
                },
            )
            assert private.status_code == 201, private.text
            private_id = private.json()["id"]

            # --- A private room produces a shared deliverable -------------
            room = (await owner_c.post(
                "/workrooms",
                params={"org_id": org_id},
                json={
                    "title": "Deliverable room",
                    "objective": "Company overview for the Northstar pilot",
                    "department_ids": [],
                    "visibility": "private",
                },
            )).json()
            room_id = room["id"]
            task_id = room["tasks"][0]["id"]

            added = await owner_c.post(
                f"/workrooms/{room_id}/members",
                params={"org_id": org_id},
                json={"user_id": participant["id"], "room_role": "viewer"},
            )
            assert added.status_code == 201, added.text

            started = await owner_c.post(
                f"/workrooms/{room_id}/runs",
                params={"org_id": org_id},
                json={"task_id": task_id, "instruction": "Summarise the pilot."},
            )
            assert started.status_code == 202, started.text
            run_id = started.json()["id"]
            await wait_for_run(owner_c, org_id, room_id, run_id, "awaiting_approval")

            approved = await owner_c.post(
                f"/workroom-runs/{run_id}/approval",
                params={"org_id": org_id},
                json={"approved": True},
            )
            assert approved.status_code == 200, approved.text
            completed = await wait_for_run(
                owner_c, org_id, room_id, run_id, "completed"
            )
            shared_id = completed["result"]["artifact_id"]
            assert completed["result"]["shared_with_workroom"] is True, completed

            # --- Two authorized participants open the same artifact -------
            owner_view = await owner_c.get(
                f"/artifacts/{shared_id}", params={"org_id": org_id}
            )
            assert owner_view.status_code == 200, owner_view.text

            participant_view = await participant_c.get(
                f"/artifacts/{shared_id}", params={"org_id": org_id}
            )
            assert participant_view.status_code == 200, participant_view.text
            assert participant_view.json()["id"] == owner_view.json()["id"]
            assert participant_view.json()["title"] == owner_view.json()["title"]
            grant = participant_view.json()["access_via_workroom"]
            assert grant["workroom_id"] == room_id, grant
            assert grant["room_role"] == "viewer", grant
            print("✓ two authorized participants open the same deliverable")

            # A viewer may also download it.
            download = await participant_c.get(
                f"/artifacts/{shared_id}/download",
                params={"org_id": org_id, "format": "markdown"},
            )
            assert download.status_code == 200, download.status_code
            assert download.content, "empty download"
            print("✓ a room viewer can download a shared deliverable")

            # --- Unauthorized organization member is refused --------------
            refused = await outsider_c.get(
                f"/artifacts/{shared_id}", params={"org_id": org_id}
            )
            assert refused.status_code == 404, refused.text
            refused_download = await outsider_c.get(
                f"/artifacts/{shared_id}/download", params={"org_id": org_id}
            )
            assert refused_download.status_code == 404, refused_download.text
            print("✓ an organization member outside the room is refused")

            # --- Another organization is refused --------------------------
            foreign = await foreign_c.get(
                f"/artifacts/{shared_id}", params={"org_id": org_id}
            )
            assert foreign.status_code in (401, 403), foreign.text
            print("✓ another organization cannot reach the deliverable")

            # --- Old private deliverables stay private --------------------
            still_private = await participant_c.get(
                f"/artifacts/{private_id}", params={"org_id": org_id}
            )
            assert still_private.status_code == 404, still_private.text
            owner_private = await owner_c.get(
                f"/artifacts/{private_id}", params={"org_id": org_id}
            )
            assert owner_private.status_code == 200, owner_private.text
            assert owner_private.json()["shared_with_workrooms"] == [], (
                owner_private.json()["shared_with_workrooms"]
            )
            print("✓ pre-existing private deliverables remain private")

            # --- The room lists its deliverables with provenance ----------
            listing = await participant_c.get(
                f"/workrooms/{room_id}/deliverables", params={"org_id": org_id}
            )
            assert listing.status_code == 200, listing.text
            deliverables = listing.json()["deliverables"]
            assert len(deliverables) == 1, deliverables
            entry = deliverables[0]
            assert entry["artifact_id"] == shared_id, entry
            assert entry["run_id"] == run_id, entry
            assert entry["task_id"] == task_id, entry
            assert entry["approved_by_name"] == "Deliv Owner", entry
            assert entry["source_count"] >= 1, entry
            assert entry["compose_path"].startswith("/create?artifact="), entry
            print("✓ the room lists deliverables with approval and source metadata")

            # --- Duplicate approval does not duplicate the deliverable ----
            duplicate = await owner_c.post(
                f"/workroom-runs/{run_id}/approval",
                params={"org_id": org_id},
                json={"approved": True},
            )
            assert duplicate.status_code == 409, duplicate.text
            async with async_session() as session:
                links = (
                    await session.execute(
                        select(WorkroomArtifact).where(
                            WorkroomArtifact.workroom_id == room_id
                        )
                    )
                ).scalars().all()
            assert len(links) == 1, links
            print("✓ duplicate approval creates exactly one shared deliverable")

            # --- Only a manager may withdraw ------------------------------
            not_allowed = await participant_c.delete(
                f"/workrooms/{room_id}/deliverables/{shared_id}",
                params={"org_id": org_id},
            )
            assert not_allowed.status_code == 403, not_allowed.text

            withdrawn = await owner_c.delete(
                f"/workrooms/{room_id}/deliverables/{shared_id}",
                params={"org_id": org_id},
            )
            assert withdrawn.status_code == 200, withdrawn.text
            gone = await participant_c.get(
                f"/artifacts/{shared_id}", params={"org_id": org_id}
            )
            assert gone.status_code == 404, gone.text
            # Withdrawing shares it back down, it does not destroy the artifact.
            survives = await owner_c.get(
                f"/artifacts/{shared_id}", params={"org_id": org_id}
            )
            assert survives.status_code == 200, survives.text
            print("✓ withdrawing revokes access without destroying the artifact")
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
    print("Workroom deliverables E2E: OK")
