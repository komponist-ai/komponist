"""E2E checks for generated Workroom plans and real task management.

Runs provider-free: the deterministic mock returns the same shape the live
provider is held to, so the strict-schema and application-side validation
paths are the ones exercised here.
"""

import asyncio
import os
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages"))

import httpx
from pydantic import ValidationError
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
    WorkroomJob,
    WorkroomMember,
    WorkroomPlanVersion,
    WorkroomRun,
    WorkroomTask,
    async_session,
    init_db,
)
from workroom_plans import MAX_PLAN_TASKS, PLAN_SCHEMA, PlanSpec


OWNER_EMAIL = "workroom-plans-owner-e2e@example.com"
MEMBER_EMAIL = "workroom-plans-member-e2e@example.com"
PASSWORD = "correct horse battery staple"
EMAILS = [OWNER_EMAIL, MEMBER_EMAIL]


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
                WorkroomJob, WorkroomEvent, WorkroomRun, WorkroomTask,
                WorkroomPlanVersion, WorkroomMember, Workroom,
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


def check_schema_is_strict() -> None:
    """OpenAI strict mode requires closed objects with everything required."""
    assert PLAN_SCHEMA["additionalProperties"] is False
    assert set(PLAN_SCHEMA["required"]) == set(PLAN_SCHEMA["properties"])
    item = PLAN_SCHEMA["properties"]["tasks"]["items"]
    assert item["additionalProperties"] is False
    assert set(item["required"]) == set(item["properties"])
    print("✓ the plan schema satisfies strict structured outputs")


def check_validation_rejects_bad_plans() -> None:
    """Model output is never trusted: the graph rules are enforced locally."""
    base = {
        "client_key": "a",
        "title": "Do the thing",
        "description": "Actually do the thing.",
        "assignee_type": "agent",
        "depends_on": [],
        "requires_approval": False,
    }

    def rejects(tasks, label) -> None:
        try:
            PlanSpec.model_validate({"summary": "Plan", "tasks": tasks})
        except ValidationError:
            return
        raise AssertionError(f"validation accepted {label}")

    rejects([base, {**base, "client_key": "a"}], "duplicate keys")
    rejects([{**base, "depends_on": ["missing"]}], "an unknown dependency")
    rejects([{**base, "depends_on": ["a"]}], "a self-dependency")
    rejects(
        [
            {**base, "client_key": "a", "depends_on": ["b"]},
            {**base, "client_key": "b", "depends_on": ["a"]},
        ],
        "a dependency cycle",
    )
    rejects([], "an empty plan")
    rejects(
        [{**base, "client_key": f"k{index}"} for index in range(MAX_PLAN_TASKS + 1)],
        "too many tasks",
    )

    # A valid plan still passes, with keys normalised.
    valid = PlanSpec.model_validate({
        "summary": "  Plan   summary ",
        "tasks": [
            {**base, "client_key": "Research Decisions"},
            {**base, "client_key": "draft", "depends_on": ["research-decisions"]},
        ],
    })
    assert valid.summary == "Plan summary", valid.summary
    assert valid.tasks[0].client_key == "research-decisions"
    print("✓ invalid plans are rejected and valid ones are normalised")


async def run() -> None:
    previous_mode = os.environ.get("KOMPONIST_AI_MODE")
    os.environ["KOMPONIST_AI_MODE"] = "mock"
    GraphClient.initialize()
    await init_db()
    await cleanup()
    transport = httpx.ASGITransport(app=main.app)

    check_schema_is_strict()
    check_validation_rejects_bad_plans()

    def client() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=transport, base_url="http://testserver")

    try:
        async with client() as owner_c, client() as member_c:
            owner_response = await owner_c.post(
                "/auth/register",
                json={"name": "Plan Owner", "email": OWNER_EMAIL, "password": PASSWORD},
            )
            assert owner_response.status_code == 201, owner_response.text
            owner = owner_response.json()["user"]
            member_response = await member_c.post(
                "/auth/register",
                json={"name": "Plan Member", "email": MEMBER_EMAIL, "password": PASSWORD},
            )
            assert member_response.status_code == 201, member_response.text
            member = member_response.json()["user"]
            org_id = owner["org_id"]

            async with async_session() as session:
                session.add(OrganizationMembership(
                    id=str(uuid4()),
                    user_id=member["id"],
                    org_id=org_id,
                    role="member",
                    status="active",
                ))
                await session.commit()

            created = await owner_c.post(
                "/workrooms",
                params={"org_id": org_id},
                json={
                    "title": "Planning room",
                    "objective": "Prepare the Northstar pilot launch",
                    "department_ids": [],
                },
            )
            assert created.status_code == 201, created.text
            room_id = created.json()["id"]
            seeded_task_id = created.json()["tasks"][0]["id"]
            manual = await owner_c.post(
                f"/workrooms/{room_id}/tasks",
                params={"org_id": org_id},
                json={
                    "title": "Keep the manually added task",
                    "description": "This task was deliberately added by a person.",
                    "assignee_type": "agent",
                },
            )
            assert manual.status_code == 201, manual.text
            manual_task_id = manual.json()["id"]

            # --- Generation produces a draft, not an active plan ----------
            generated = await owner_c.post(
                f"/workrooms/{room_id}/plans",
                params={"org_id": org_id},
                json={"guidance": "Focus on what must happen before launch."},
            )
            assert generated.status_code == 201, generated.text
            plan = generated.json()
            plan_id = plan["id"]
            assert plan["status"] == "draft", plan
            assert plan["version"] == 1, plan
            assert plan["provider"] == "mock", plan
            assert plan["model"], plan
            assert len(plan["spec"]["tasks"]) >= 1, plan["spec"]
            # No model reasoning is persisted.
            assert "reasoning" not in plan["spec"], plan["spec"]

            # The draft has not touched the room's tasks yet.
            before = await owner_c.get(
                f"/workrooms/{room_id}", params={"org_id": org_id}
            )
            assert len(before.json()["tasks"]) == 2, before.json()["tasks"]
            print("✓ a generated plan starts as an unapproved draft")

            # --- Editing a draft is held to the same rules ----------------
            bad_edit = await owner_c.patch(
                f"/workrooms/{room_id}/plans/{plan_id}",
                params={"org_id": org_id},
                json={
                    "summary": "Broken plan",
                    "tasks": [{
                        "client_key": "only",
                        "title": "Broken task",
                        "description": "Depends on nothing real.",
                        "assignee_type": "agent",
                        "depends_on": ["ghost"],
                        "requires_approval": False,
                    }],
                },
            )
            assert bad_edit.status_code == 422, bad_edit.text

            edited = await owner_c.patch(
                f"/workrooms/{room_id}/plans/{plan_id}",
                params={"org_id": org_id},
                json={
                    "summary": "Ship the pilot with a cited briefing.",
                    "tasks": [
                        {
                            "client_key": "gather-context",
                            "title": "Gather confirmed launch context",
                            "description": "Collect confirmed launch facts and evidence.",
                            "assignee_type": "agent",
                            "depends_on": [],
                            "requires_approval": False,
                        },
                        {
                            "client_key": "brief-the-team",
                            "title": "Brief the launch team",
                            "description": "Walk the team through the confirmed plan.",
                            "assignee_type": "human",
                            "depends_on": ["gather-context"],
                            "requires_approval": True,
                        },
                    ],
                },
            )
            assert edited.status_code == 200, edited.text
            assert len(edited.json()["spec"]["tasks"]) == 2
            print("✓ draft edits are validated like generated output")

            # --- Only an approver may activate a plan ---------------------
            refused = await member_c.post(
                f"/workrooms/{room_id}/plans/{plan_id}/approval",
                params={"org_id": org_id},
                json={"approved": True},
            )
            assert refused.status_code == 403, refused.text

            approved = await owner_c.post(
                f"/workrooms/{room_id}/plans/{plan_id}/approval",
                params={"org_id": org_id},
                json={"approved": True},
            )
            assert approved.status_code == 200, approved.text
            assert approved.json()["status"] == "approved", approved.json()
            assert approved.json()["approved_by_user_id"] == owner["id"]

            after = await owner_c.get(
                f"/workrooms/{room_id}", params={"org_id": org_id}
            )
            tasks = after.json()["tasks"]
            by_key = {task["client_key"]: task for task in tasks if task["client_key"]}
            assert set(by_key) == {"gather-context", "brief-the-team"}, by_key
            # Dependencies are stored as real task ids.
            assert by_key["brief-the-team"]["depends_on"] == [
                by_key["gather-context"]["id"]
            ]
            assert by_key["brief-the-team"]["requires_approval"] is True
            # The temporary quick-start task is replaced, while real
            # person-authored work survives plan approval.
            assert all(task["id"] != seeded_task_id for task in tasks), tasks
            assert any(task["id"] == manual_task_id for task in tasks), tasks
            print("✓ approval replaces the quick-start task and preserves manual work")

            # --- Approving twice is rejected ------------------------------
            again = await owner_c.post(
                f"/workrooms/{room_id}/plans/{plan_id}/approval",
                params={"org_id": org_id},
                json={"approved": True},
            )
            assert again.status_code == 409, again.text

            # --- Regenerating supersedes the previous draft ---------------
            regenerated = await owner_c.post(
                f"/workrooms/{room_id}/plans",
                params={"org_id": org_id},
                json={"guidance": ""},
            )
            assert regenerated.status_code == 201, regenerated.text
            assert regenerated.json()["version"] == 2, regenerated.json()

            second = await owner_c.post(
                f"/workrooms/{room_id}/plans",
                params={"org_id": org_id},
                json={"guidance": ""},
            )
            assert second.status_code == 201, second.text
            listing = await owner_c.get(
                f"/workrooms/{room_id}/plans", params={"org_id": org_id}
            )
            payload = listing.json()
            statuses = {item["version"]: item["status"] for item in payload["plans"]}
            assert statuses[1] == "approved", statuses
            assert statuses[2] == "superseded", statuses
            assert statuses[3] == "draft", statuses
            assert payload["current"]["version"] == 1, payload["current"]
            assert payload["draft"]["version"] == 3, payload["draft"]
            print("✓ plan versions supersede rather than overwrite")

            # --- Rejecting a draft leaves the active plan alone -----------
            rejected = await owner_c.post(
                f"/workrooms/{room_id}/plans/{payload['draft']['id']}/approval",
                params={"org_id": org_id},
                json={"approved": False},
            )
            assert rejected.status_code == 200, rejected.text
            assert rejected.json()["status"] == "rejected"
            print("✓ a rejected draft does not change the active plan")

            # --- Task management ------------------------------------------
            target = by_key["brief-the-team"]["id"]
            assigned = await owner_c.patch(
                f"/workrooms/{room_id}/tasks/{target}",
                params={"org_id": org_id},
                json={
                    "assignee_type": "human",
                    "assignee_user_id": member["id"],
                    "status": "in_progress",
                },
            )
            assert assigned.status_code == 200, assigned.text
            assert assigned.json()["assignee_user_id"] == member["id"]
            assert assigned.json()["assignee_name"] == "Plan Member"

            # Assigning to a non-member is refused.
            bad_assign = await owner_c.patch(
                f"/workrooms/{room_id}/tasks/{target}",
                params={"org_id": org_id},
                json={"assignee_user_id": str(uuid4())},
            )
            assert bad_assign.status_code == 400, bad_assign.text

            # A task cannot depend on itself.
            self_dependency = await owner_c.patch(
                f"/workrooms/{room_id}/tasks/{target}",
                params={"org_id": org_id},
                json={"depends_on": [target]},
            )
            assert self_dependency.status_code == 200, self_dependency.text
            assert self_dependency.json()["depends_on"] == [], self_dependency.json()

            reordered = await owner_c.post(
                f"/workrooms/{room_id}/tasks/reorder",
                params={"org_id": org_id},
                json={"task_ids": [target, by_key["gather-context"]["id"]]},
            )
            assert reordered.status_code == 200, reordered.text
            assert reordered.json()["tasks"][0]["id"] == target

            archived = await owner_c.delete(
                f"/workrooms/{room_id}/tasks/{manual_task_id}",
                params={"org_id": org_id},
            )
            assert archived.status_code == 200, archived.text
            remaining = await owner_c.get(
                f"/workrooms/{room_id}", params={"org_id": org_id}
            )
            assert all(
                task["id"] != manual_task_id for task in remaining.json()["tasks"]
            ), remaining.json()["tasks"]
            print("✓ tasks can be assigned, reordered, and archived")

            # --- A viewer cannot generate or edit plans -------------------
            viewer_plan = await member_c.post(
                f"/workrooms/{room_id}/plans",
                params={"org_id": org_id},
                json={"guidance": ""},
            )
            assert viewer_plan.status_code == 403, viewer_plan.text
            print("✓ planning requires the edit permission")

            # --- Run lineage is exposed per task --------------------------
            lineage = await owner_c.get(
                f"/workrooms/{room_id}/tasks/{target}/runs",
                params={"org_id": org_id},
            )
            assert lineage.status_code == 200, lineage.text
            assert "runs" in lineage.json(), lineage.json()

            audit = await owner_c.get(
                f"/workrooms/{room_id}", params={"org_id": org_id}
            )
            event_types = {event["event_type"] for event in audit.json()["events"]}
            for expected in (
                "plan_generated", "plan_edited", "plan_approved",
                "plan_rejected", "task_updated", "task_archived",
            ):
                assert expected in event_types, (expected, event_types)
            print("✓ plan and task changes are audited")
    finally:
        await cleanup()
        await GraphClient.close()
        if previous_mode is None:
            os.environ.pop("KOMPONIST_AI_MODE", None)
        else:
            os.environ["KOMPONIST_AI_MODE"] = previous_mode


if __name__ == "__main__":
    asyncio.run(run())
    print("Workroom plans E2E: OK")
