"""E2E checks for Workroom participants, room roles, and visibility modes.

Covers the authorization boundary that matters most: room membership must
never widen what someone can see, and a private room must not even disclose
its existence to an unauthorized organization member.
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
    Department,
    DepartmentMembership,
    GeneratedArtifact,
    Org,
    OrganizationMembership,
    PasswordCredential,
    User,
    Workroom,
    WorkroomEvent,
    WorkroomJob,
    WorkroomMember,
    WorkroomRun,
    WorkroomTask,
    async_session,
    init_db,
)


OWNER_EMAIL = "workroom-roles-owner-e2e@example.com"
EDITOR_EMAIL = "workroom-roles-editor-e2e@example.com"
VIEWER_EMAIL = "workroom-roles-viewer-e2e@example.com"
APPROVER_EMAIL = "workroom-roles-approver-e2e@example.com"
OUTSIDER_EMAIL = "workroom-roles-outsider-e2e@example.com"
PASSWORD = "correct horse battery staple"

EMAILS = [OWNER_EMAIL, EDITOR_EMAIL, VIEWER_EMAIL, APPROVER_EMAIL, OUTSIDER_EMAIL]


async def cleanup() -> None:
    async with async_session() as session:
        users = (
            await session.execute(select(User).where(User.email.in_(EMAILS)))
        ).scalars().all()
        user_ids = [user.id for user in users]
        org_ids = list({user.org_id for user in users})

        if org_ids:
            for table in (
                WorkroomJob, WorkroomEvent, WorkroomRun, WorkroomTask,
                WorkroomMember, Workroom,
            ):
                await session.execute(
                    delete(table).where(table.org_id.in_(org_ids))
                )
            await session.execute(
                delete(DepartmentMembership).where(
                    DepartmentMembership.org_id.in_(org_ids)
                )
            )
            await session.execute(
                delete(Department).where(Department.org_id.in_(org_ids))
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


async def register(client: httpx.AsyncClient, name: str, email: str) -> dict:
    response = await client.post(
        "/auth/register",
        json={"name": name, "email": email, "password": PASSWORD},
    )
    assert response.status_code == 201, response.text
    return response.json()["user"]


async def join_org(user_id: str, org_id: str, role: str = "member") -> None:
    async with async_session() as session:
        session.add(OrganizationMembership(
            id=str(uuid4()),
            user_id=user_id,
            org_id=org_id,
            role=role,
            status="active",
        ))
        await session.commit()


async def run() -> None:
    previous_mode = os.environ.get("KOMPONIST_AI_MODE")
    os.environ["KOMPONIST_AI_MODE"] = "mock"
    GraphClient.initialize()
    await init_db()
    await cleanup()
    transport = httpx.ASGITransport(app=main.app)

    def client() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=transport, base_url="http://testserver")

    try:
        async with client() as owner_c, client() as editor_c, client() as viewer_c, \
                client() as approver_c, client() as outsider_c:
            owner = await register(owner_c, "Room Owner", OWNER_EMAIL)
            editor = await register(editor_c, "Room Editor", EDITOR_EMAIL)
            viewer = await register(viewer_c, "Room Viewer", VIEWER_EMAIL)
            approver = await register(approver_c, "Room Approver", APPROVER_EMAIL)
            outsider = await register(outsider_c, "Other Org", OUTSIDER_EMAIL)
            org_id = owner["org_id"]

            for member in (editor, viewer, approver):
                await join_org(member["id"], org_id)

            # --- Creator becomes owner -----------------------------------
            created = await owner_c.post(
                "/workrooms",
                params={"org_id": org_id},
                json={
                    "title": "Roles room",
                    "objective": "Verify room roles and visibility",
                    "department_ids": [],
                    "visibility": "organization",
                },
            )
            assert created.status_code == 201, created.text
            room = created.json()
            room_id = room["id"]
            assert room["room_role"] == "owner", room
            assert room["visibility"] == "organization", room
            assert len(room["members"]) == 1, room["members"]
            assert room["members"][0]["room_role"] == "owner"
            print("✓ the creator becomes the room owner")

            # --- Organization visibility grants an implicit viewer role ---
            seen = await viewer_c.get(
                f"/workrooms/{room_id}", params={"org_id": org_id}
            )
            assert seen.status_code == 200, seen.text
            assert seen.json()["room_role"] == "viewer", seen.json()["room_role"]

            # A viewer cannot change the plan or drive the agent.
            blocked = await viewer_c.post(
                f"/workrooms/{room_id}/tasks",
                params={"org_id": org_id},
                json={"title": "Viewer task", "description": "should fail"},
            )
            assert blocked.status_code == 403, blocked.text
            blocked_run = await viewer_c.post(
                f"/workrooms/{room_id}/runs",
                params={"org_id": org_id},
                json={"instruction": "should fail"},
            )
            assert blocked_run.status_code == 403, blocked_run.text
            print("✓ an implicit viewer can read but not edit")

            # --- Only owners manage participants -------------------------
            refused = await viewer_c.post(
                f"/workrooms/{room_id}/members",
                params={"org_id": org_id},
                json={"user_id": editor["id"], "room_role": "editor"},
            )
            assert refused.status_code == 403, refused.text

            added = await owner_c.post(
                f"/workrooms/{room_id}/members",
                params={"org_id": org_id},
                json={"user_id": editor["id"], "room_role": "editor"},
            )
            assert added.status_code == 201, added.text
            assert added.json()["room_role"] == "editor"

            added_approver = await owner_c.post(
                f"/workrooms/{room_id}/members",
                params={"org_id": org_id},
                json={"user_id": approver["id"], "room_role": "approver"},
            )
            assert added_approver.status_code == 201, added_approver.text

            # Someone outside the organization can never be added.
            rejected = await owner_c.post(
                f"/workrooms/{room_id}/members",
                params={"org_id": org_id},
                json={"user_id": outsider["id"], "room_role": "viewer"},
            )
            assert rejected.status_code == 400, rejected.text
            print("✓ only owners manage participants, and only org members qualify")

            # --- Editors edit; approvers approve but do not edit ----------
            editor_task = await editor_c.post(
                f"/workrooms/{room_id}/tasks",
                params={"org_id": org_id},
                json={"title": "Editor task", "description": "allowed"},
            )
            assert editor_task.status_code == 201, editor_task.text

            approver_task = await approver_c.post(
                f"/workrooms/{room_id}/tasks",
                params={"org_id": org_id},
                json={"title": "Approver task", "description": "not allowed"},
            )
            assert approver_task.status_code == 403, approver_task.text
            print("✓ editors edit the plan and approvers do not")

            # --- A room must keep an owner --------------------------------
            demote = await owner_c.patch(
                f"/workrooms/{room_id}/members/{owner['id']}",
                params={"org_id": org_id},
                json={"room_role": "viewer"},
            )
            assert demote.status_code == 409, demote.text

            promoted = await owner_c.patch(
                f"/workrooms/{room_id}/members/{editor['id']}",
                params={"org_id": org_id},
                json={"room_role": "owner"},
            )
            assert promoted.status_code == 200, promoted.text
            print("✓ the last owner cannot be demoted away")

            # --- Removing a participant revokes explicit access -----------
            removed = await owner_c.delete(
                f"/workrooms/{room_id}/members/{approver['id']}",
                params={"org_id": org_id},
            )
            assert removed.status_code == 200, removed.text
            # The room is organization-visible, so they fall back to viewer.
            after_removal = await approver_c.get(
                f"/workrooms/{room_id}", params={"org_id": org_id}
            )
            assert after_removal.status_code == 200, after_removal.text
            assert after_removal.json()["room_role"] == "viewer"

            # --- Private visibility requires explicit membership ----------
            private = await owner_c.patch(
                f"/workrooms/{room_id}",
                params={"org_id": org_id},
                json={"visibility": "private"},
            )
            assert private.status_code == 200, private.text
            assert private.json()["visibility"] == "private"

            # A former member and an ordinary org member now get 404, not 403:
            # a private room's existence is not disclosed.
            hidden = await approver_c.get(
                f"/workrooms/{room_id}", params={"org_id": org_id}
            )
            assert hidden.status_code == 404, hidden.text
            hidden_list = await approver_c.get(
                "/workrooms", params={"org_id": org_id}
            )
            assert hidden_list.status_code == 200, hidden_list.text
            assert all(
                item["id"] != room_id for item in hidden_list.json()["workrooms"]
            ), hidden_list.json()
            # The still-explicit editor keeps access.
            still_in = await editor_c.get(
                f"/workrooms/{room_id}", params={"org_id": org_id}
            )
            assert still_in.status_code == 200, still_in.text
            print("✓ a private room is invisible without explicit membership")

            # --- Cross-organization isolation -----------------------------
            foreign = await outsider_c.get(
                f"/workrooms/{room_id}", params={"org_id": org_id}
            )
            assert foreign.status_code in (401, 403), foreign.text
            print("✓ another organization cannot reach the room")

            # --- Department visibility ------------------------------------
            async with async_session() as session:
                department = Department(
                    id=str(uuid4()),
                    org_id=org_id,
                    name=f"Board {uuid4().hex[:6]}",
                    description="Restricted",
                )
                session.add(department)
                session.add(DepartmentMembership(
                    id=str(uuid4()),
                    org_id=org_id,
                    department_id=department.id,
                    user_id=owner["id"],
                ))
                await session.commit()
                department_id = department.id

            scoped = await owner_c.post(
                "/workrooms",
                params={"org_id": org_id},
                json={
                    "title": "Department room",
                    "objective": "Only the board department may see this",
                    "department_ids": [department_id],
                    "visibility": "departments",
                },
            )
            assert scoped.status_code == 201, scoped.text
            scoped_id = scoped.json()["id"]

            outside_scope = await viewer_c.get(
                f"/workrooms/{scoped_id}", params={"org_id": org_id}
            )
            assert outside_scope.status_code == 404, outside_scope.text
            in_scope = await owner_c.get(
                f"/workrooms/{scoped_id}", params={"org_id": org_id}
            )
            assert in_scope.status_code == 200, in_scope.text
            print("✓ department visibility follows department access")

            # --- Archive and reopen ---------------------------------------
            archived = await owner_c.post(
                f"/workrooms/{scoped_id}/archive", params={"org_id": org_id}
            )
            assert archived.status_code == 200, archived.text
            assert archived.json()["status"] == "archived"

            frozen = await owner_c.post(
                f"/workrooms/{scoped_id}/tasks",
                params={"org_id": org_id},
                json={"title": "After archive", "description": "should fail"},
            )
            assert frozen.status_code == 409, frozen.text

            default_list = await owner_c.get("/workrooms", params={"org_id": org_id})
            assert all(
                item["id"] != scoped_id for item in default_list.json()["workrooms"]
            ), default_list.json()
            with_archived = await owner_c.get(
                "/workrooms", params={"org_id": org_id, "include_archived": True}
            )
            assert any(
                item["id"] == scoped_id
                for item in with_archived.json()["workrooms"]
            ), with_archived.json()

            reopened = await owner_c.post(
                f"/workrooms/{scoped_id}/reopen", params={"org_id": org_id}
            )
            assert reopened.status_code == 200, reopened.text
            assert reopened.json()["status"] == "active"
            print("✓ archiving hides a room without destroying it")

            # --- Membership changes are audited ---------------------------
            audit = await editor_c.get(
                f"/workrooms/{room_id}", params={"org_id": org_id}
            )
            event_types = {event["event_type"] for event in audit.json()["events"]}
            assert "member_added" in event_types, event_types
            assert "member_role_changed" in event_types, event_types
            assert "member_removed" in event_types, event_types
            assert "room_settings_changed" in event_types, event_types
            print("✓ membership and scope changes are audited")
    finally:
        await cleanup()
        await GraphClient.close()
        if previous_mode is None:
            os.environ.pop("KOMPONIST_AI_MODE", None)
        else:
            os.environ["KOMPONIST_AI_MODE"] = previous_mode


if __name__ == "__main__":
    asyncio.run(run())
    print("Workroom roles E2E: OK")
