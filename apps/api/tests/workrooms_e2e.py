"""E2E checks for shared Workrooms and the governed agent-to-Compose flow."""

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
    WorkroomEvent,
    WorkroomRun,
    WorkroomTask,
    async_session,
    init_db,
)


OWNER_EMAIL = "workrooms-owner-e2e@example.com"
MEMBER_EMAIL = "workrooms-member-e2e@example.com"
PASSWORD = "correct horse battery staple"


async def cleanup() -> None:
    async with async_session() as session:
        users = (
            await session.execute(
                select(User).where(User.email.in_([OWNER_EMAIL, MEMBER_EMAIL]))
            )
        ).scalars().all()
        user_ids = [user.id for user in users]
        org_ids = list({user.org_id for user in users})

        if org_ids:
            for org_id in org_ids:
                await GraphClient.run_query(
                    "MATCH (node) WHERE node.org_id = $org_id DETACH DELETE node",
                    {"org_id": org_id},
                )
            await session.execute(
                delete(WorkroomEvent).where(WorkroomEvent.org_id.in_(org_ids))
            )
            await session.execute(
                delete(WorkroomRun).where(WorkroomRun.org_id.in_(org_ids))
            )
            await session.execute(
                delete(WorkroomTask).where(WorkroomTask.org_id.in_(org_ids))
            )
            await session.execute(
                delete(Workroom).where(Workroom.org_id.in_(org_ids))
            )

        if user_ids:
            await session.execute(
                delete(GeneratedArtifact).where(GeneratedArtifact.user_id.in_(user_ids))
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
            await session.execute(
                delete(AuthSession).where(AuthSession.user_id.in_(user_ids))
            )
            await session.execute(
                delete(PasswordCredential).where(
                    PasswordCredential.user_id.in_(user_ids)
                )
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
            await session.execute(delete(Org).where(Org.id.in_(org_ids)))
        await session.commit()


async def wait_for_run(
    client: httpx.AsyncClient,
    org_id: str,
    room_id: str,
    run_id: str,
    expected_status: str,
) -> dict:
    for _ in range(80):
        response = await client.get(
            f"/workrooms/{room_id}", params={"org_id": org_id}
        )
        assert response.status_code == 200, response.text
        room = response.json()
        run = next((item for item in room["runs"] if item["id"] == run_id), None)
        if run and run["status"] == expected_status:
            return room
        if run and run["status"] == "failed":
            raise AssertionError(run)
        await asyncio.sleep(0.05)
    raise AssertionError(f"Run {run_id} never reached {expected_status}")


async def run() -> None:
    previous_mode = os.environ.get("KOMPONIST_AI_MODE")
    os.environ["KOMPONIST_AI_MODE"] = "mock"
    GraphClient.initialize()
    await init_db()
    await cleanup()
    transport = httpx.ASGITransport(app=main.app)

    try:
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as owner_client, httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as member_client:
            owner_response = await owner_client.post(
                "/auth/register",
                json={"name": "Workroom Owner", "email": OWNER_EMAIL, "password": PASSWORD},
            )
            assert owner_response.status_code == 201, owner_response.text
            owner = owner_response.json()["user"]

            member_response = await member_client.post(
                "/auth/register",
                json={"name": "Workroom Member", "email": MEMBER_EMAIL, "password": PASSWORD},
            )
            assert member_response.status_code == 201, member_response.text
            member = member_response.json()["user"]

            async with async_session() as session:
                session.add(OrganizationMembership(
                    id=str(uuid4()),
                    user_id=member["id"],
                    org_id=owner["org_id"],
                    role="member",
                    status="active",
                ))
                await session.commit()

            await GraphClient.run_query(
                """
                CREATE (decision:Entity {
                    id: 'workroom-decision', org_id: $org_id,
                    entity_type: 'Decision',
                    statement: 'Launch the Northstar pilot in September.',
                    detail: 'The launch decision is confirmed for the pilot team.',
                    status: 'confirmed', confidence: 'high', department_ids: [],
                    created_at: datetime(), confirmed_at: datetime()
                })
                CREATE (goal:Entity {
                    id: 'workroom-goal', org_id: $org_id,
                    entity_type: 'Goal',
                    statement: 'The Northstar pilot runs for four weeks.',
                    status: 'confirmed', confidence: 'high', department_ids: [],
                    created_at: datetime(), confirmed_at: datetime()
                })
                CREATE (hidden:Entity {
                    id: 'workroom-hidden', org_id: $org_id,
                    entity_type: 'Constraint',
                    statement: 'The confidential board budget is 900000 euros.',
                    status: 'confirmed', confidence: 'high',
                    department_ids: ['board'],
                    created_at: datetime(), confirmed_at: datetime()
                })
                CREATE (e1:Evidence {
                    id: 'workroom-evidence-1', org_id: $org_id, source: 'upload',
                    title: 'Northstar plan', reference: 'northstar-plan.md',
                    excerpt: 'Launch in September.', line_start: 12, line_end: 12,
                    source_date: datetime()
                })
                CREATE (e2:Evidence {
                    id: 'workroom-evidence-2', org_id: $org_id, source: 'upload',
                    title: 'Northstar plan', reference: 'northstar-plan.md',
                    excerpt: 'The pilot lasts four weeks.', line_start: 18, line_end: 18,
                    source_date: datetime()
                })
                CREATE (e3:Evidence {
                    id: 'workroom-evidence-hidden', org_id: $org_id, source: 'upload',
                    title: 'Board budget', reference: 'board-budget.md',
                    excerpt: 'Confidential budget.', department_id: 'board',
                    source_date: datetime()
                })
                CREATE (decision)-[:CITED_BY]->(e1)
                CREATE (goal)-[:CITED_BY]->(e2)
                CREATE (hidden)-[:CITED_BY]->(e3)
                CREATE (decision)-[:ADVANCES]->(goal)
                """,
                {"org_id": owner["org_id"]},
            )

            unauthenticated = await httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ).get("/workrooms", params={"org_id": owner["org_id"]})
            assert unauthenticated.status_code == 401, unauthenticated.text

            create_response = await owner_client.post(
                "/workrooms",
                params={"org_id": owner["org_id"]},
                json={
                    "title": "Northstar launch room",
                    "objective": "Company overview for the Northstar pilot",
                    "department_ids": [],
                },
            )
            assert create_response.status_code == 201, create_response.text
            room = create_response.json()
            room_id = room["id"]
            task_id = room["tasks"][0]["id"]

            shared_response = await member_client.get(
                f"/workrooms/{room_id}", params={"org_id": owner["org_id"]}
            )
            assert shared_response.status_code == 200, shared_response.text

            start_response = await owner_client.post(
                f"/workrooms/{room_id}/runs",
                params={"org_id": owner["org_id"]},
                json={"task_id": task_id, "instruction": "Focus on current facts."},
            )
            assert start_response.status_code == 202, start_response.text
            first_run_id = start_response.json()["id"]
            researched = await wait_for_run(
                owner_client,
                owner["org_id"],
                room_id,
                first_run_id,
                "awaiting_approval",
            )
            first_run = next(
                item for item in researched["runs"] if item["id"] == first_run_id
            )
            statements = " ".join(
                finding["statement"]
                for finding in first_run["context_snapshot"]["findings"]
            )
            assert "Northstar" in statements
            assert "900000" not in statements
            assert first_run["result"]["source_count"] == 2

            pause_response = await owner_client.post(
                f"/workroom-runs/{first_run_id}/pause",
                params={"org_id": owner["org_id"]},
            )
            assert pause_response.status_code == 200, pause_response.text
            resume_response = await owner_client.post(
                f"/workroom-runs/{first_run_id}/resume",
                params={"org_id": owner["org_id"]},
            )
            assert resume_response.status_code == 200, resume_response.text
            assert resume_response.json()["status"] == "awaiting_approval"

            redirect_response = await owner_client.post(
                f"/workroom-runs/{first_run_id}/redirect",
                params={"org_id": owner["org_id"]},
                json={"instruction": "Focus on timing and launch decisions."},
            )
            assert redirect_response.status_code == 202, redirect_response.text
            second_run_id = redirect_response.json()["id"]
            assert redirect_response.json()["redirected_from_run_id"] == first_run_id
            await wait_for_run(
                owner_client,
                owner["org_id"],
                room_id,
                second_run_id,
                "awaiting_approval",
            )

            approval_responses = await asyncio.gather(
                *[
                    owner_client.post(
                        f"/workroom-runs/{second_run_id}/approval",
                        params={"org_id": owner["org_id"]},
                        json={"approved": True},
                    )
                    for _ in range(2)
                ]
            )
            assert sorted(
                response.status_code for response in approval_responses
            ) == [200, 409], [response.text for response in approval_responses]
            completed = await wait_for_run(
                owner_client,
                owner["org_id"],
                room_id,
                second_run_id,
                "completed",
            )
            completed_run = next(
                item for item in completed["runs"] if item["id"] == second_run_id
            )
            assert completed_run["result"]["artifact_id"]
            assert completed_run["result"]["compose_path"].startswith("/create?artifact=")
            assert completed["tasks"][0]["status"] == "completed"
            assert any(
                event["event_type"] == "artifact_created"
                for event in completed["events"]
            )

            artifact_response = await owner_client.get(
                f"/artifacts/{completed_run['result']['artifact_id']}",
                params={"org_id": owner["org_id"]},
            )
            assert artifact_response.status_code == 200, artifact_response.text
            artifact = artifact_response.json()
            assert artifact["artifact_type"] == "briefing"
            assert all("hidden" not in source["id"] for source in artifact["sources"])
    finally:
        await cleanup()
        await GraphClient.close()
        if previous_mode is None:
            os.environ.pop("KOMPONIST_AI_MODE", None)
        else:
            os.environ["KOMPONIST_AI_MODE"] = previous_mode


if __name__ == "__main__":
    asyncio.run(run())
    print("Workrooms E2E: OK")
