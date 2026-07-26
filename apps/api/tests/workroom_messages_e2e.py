"""E2E checks for the shared Workroom conversation.

Also pins down the boundary that matters: an ordinary message is not a command
to the agent, and conversation stays distinct from the audit trail.
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
    WorkroomMessage,
    WorkroomPlanVersion,
    WorkroomRun,
    WorkroomTask,
    async_session,
    init_db,
)


OWNER_EMAIL = "workroom-messages-owner-e2e@example.com"
MEMBER_EMAIL = "workroom-messages-member-e2e@example.com"
OTHER_EMAIL = "workroom-messages-other-e2e@example.com"
PASSWORD = "correct horse battery staple"
EMAILS = [OWNER_EMAIL, MEMBER_EMAIL, OTHER_EMAIL]


async def cleanup() -> None:
    async with async_session() as session:
        users = (
            await session.execute(select(User).where(User.email.in_(EMAILS)))
        ).scalars().all()
        user_ids = [user.id for user in users]
        org_ids = list({user.org_id for user in users})

        if org_ids:
            for table in (
                WorkroomJob, WorkroomMessage, WorkroomEvent, WorkroomRun,
                WorkroomTask, WorkroomPlanVersion, WorkroomContextItem,
                WorkroomMember, Workroom,
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
        async with client() as owner_c, client() as member_c, client() as other_c:
            owner = (await owner_c.post(
                "/auth/register",
                json={"name": "Chat Owner", "email": OWNER_EMAIL, "password": PASSWORD},
            )).json()["user"]
            member = (await member_c.post(
                "/auth/register",
                json={"name": "Chat Member", "email": MEMBER_EMAIL, "password": PASSWORD},
            )).json()["user"]
            other = (await other_c.post(
                "/auth/register",
                json={"name": "Other Org", "email": OTHER_EMAIL, "password": PASSWORD},
            )).json()["user"]
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

            room = (await owner_c.post(
                "/workrooms",
                params={"org_id": org_id},
                json={
                    "title": "Conversation room",
                    "objective": "Coordinate the Northstar pilot",
                    "department_ids": [],
                },
            )).json()
            room_id = room["id"]
            task_id = room["tasks"][0]["id"]

            # --- Posting and threading ------------------------------------
            first = await owner_c.post(
                f"/workrooms/{room_id}/messages",
                params={"org_id": org_id},
                json={
                    "body": "Where did we land on the launch date?",
                    "references": [
                        {"kind": "task", "id": task_id, "label": "Research task"}
                    ],
                },
            )
            assert first.status_code == 201, first.text
            first_id = first.json()["id"]
            assert first.json()["author_type"] == "human"
            assert first.json()["references"][0]["kind"] == "task"

            reply = await member_c.post(
                f"/workrooms/{room_id}/messages",
                params={"org_id": org_id},
                json={
                    "body": "September, per the confirmed decision.",
                    "reply_to_message_id": first_id,
                },
            )
            assert reply.status_code == 201, reply.text
            assert reply.json()["reply_to_message_id"] == first_id
            print("✓ messages post and thread inside a room")

            # --- Invalid references and mentions are not trusted ----------
            # An unknown reference kind is rejected at the request boundary
            # rather than stored as an opaque pointer.
            bad_kind = await owner_c.post(
                f"/workrooms/{room_id}/messages",
                params={"org_id": org_id},
                json={
                    "body": "Checking reference handling.",
                    "references": [{"kind": "secret", "id": "nope", "label": "bad"}],
                },
            )
            assert bad_kind.status_code == 422, bad_kind.text

            noisy = await owner_c.post(
                f"/workrooms/{room_id}/messages",
                params={"org_id": org_id},
                json={
                    "body": "Checking mention handling.",
                    "references": [
                        {"kind": "task", "id": task_id, "label": "ok"}
                    ],
                    "mentions": [member["id"], other["id"], str(uuid4())],
                },
            )
            assert noisy.status_code == 201, noisy.text
            kinds = [ref["kind"] for ref in noisy.json()["references"]]
            assert kinds == ["task"], kinds
            # Only actual room participants can be mentioned: the other-org
            # user and an invented id are both discarded.
            assert noisy.json()["mentions"] == [member["id"]], noisy.json()["mentions"]
            print("✓ unknown reference kinds and non-participants are rejected")

            # --- Replying across rooms is refused -------------------------
            other_room = (await owner_c.post(
                "/workrooms",
                params={"org_id": org_id},
                json={
                    "title": "Second room",
                    "objective": "A different objective entirely",
                    "department_ids": [],
                },
            )).json()
            cross = await owner_c.post(
                f"/workrooms/{other_room['id']}/messages",
                params={"org_id": org_id},
                json={"body": "Reply from elsewhere.", "reply_to_message_id": first_id},
            )
            assert cross.status_code == 201, cross.text
            assert cross.json()["reply_to_message_id"] is None, cross.json()
            print("✓ a reply cannot point at another room's message")

            # --- Editing and deleting -------------------------------------
            edited = await owner_c.patch(
                f"/workrooms/{room_id}/messages/{first_id}",
                params={"org_id": org_id},
                json={"body": "Where did we land on the launch date? (updated)"},
            )
            assert edited.status_code == 200, edited.text
            assert edited.json()["edited_at"] is not None

            # Someone else's message is not editable.
            forbidden = await member_c.patch(
                f"/workrooms/{room_id}/messages/{first_id}",
                params={"org_id": org_id},
                json={"body": "Not mine to edit."},
            )
            assert forbidden.status_code == 404, forbidden.text

            deleted = await owner_c.delete(
                f"/workrooms/{room_id}/messages/{noisy.json()['id']}",
                params={"org_id": org_id},
            )
            assert deleted.status_code == 200, deleted.text
            assert deleted.json()["deleted"] is True
            assert deleted.json()["body"] == "", deleted.json()
            print("✓ authors edit their own messages and deletion redacts content")

            # --- Conversation and activity stay separate ------------------
            listing = await member_c.get(
                f"/workrooms/{room_id}/messages", params={"org_id": org_id}
            )
            assert listing.status_code == 200, listing.text
            bodies = [message["body"] for message in listing.json()["messages"]]
            assert any("September" in body for body in bodies), bodies
            latest_page = await member_c.get(
                f"/workrooms/{room_id}/messages",
                params={"org_id": org_id, "limit": 2},
            )
            latest_payload = latest_page.json()
            assert latest_payload["has_more"] is True, latest_payload
            assert latest_payload["total"] == 3, latest_payload
            older_page = await member_c.get(
                f"/workrooms/{room_id}/messages",
                params={
                    "org_id": org_id,
                    "limit": 2,
                    "before": latest_payload["next_before"],
                },
            )
            assert older_page.status_code == 200, older_page.text
            assert len(older_page.json()["messages"]) == 1, older_page.text

            detail = await member_c.get(
                f"/workrooms/{room_id}", params={"org_id": org_id}
            )
            event_types = {event["event_type"] for event in detail.json()["events"]}
            assert "message_posted" in event_types, event_types
            # The audit trail records that a message happened, not its content.
            assert not any(
                "September" in event["message"] for event in detail.json()["events"]
            ), detail.json()["events"]
            print("✓ conversation content stays out of the audit trail")

            # --- A message does not command the agent ---------------------
            before = await member_c.get(
                f"/workrooms/{room_id}", params={"org_id": org_id}
            )
            assert before.json()["runs"] == [], before.json()["runs"]
            await owner_c.post(
                f"/workrooms/{room_id}/messages",
                params={"org_id": org_id},
                json={"body": "Agent, start researching the launch immediately."},
            )
            after = await member_c.get(
                f"/workrooms/{room_id}", params={"org_id": org_id}
            )
            assert after.json()["runs"] == [], after.json()["runs"]
            print("✓ posting a message never starts the agent by itself")

            # --- Isolation -------------------------------------------------
            foreign = await other_c.get(
                f"/workrooms/{room_id}/messages", params={"org_id": org_id}
            )
            assert foreign.status_code in (401, 403), foreign.text

            unauthenticated = await httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ).get(f"/workrooms/{room_id}/messages", params={"org_id": org_id})
            assert unauthenticated.status_code == 401, unauthenticated.text
            print("✓ conversations are organization- and room-isolated")
    finally:
        await cleanup()
        await GraphClient.close()
        if previous_mode is None:
            os.environ.pop("KOMPONIST_AI_MODE", None)
        else:
            os.environ["KOMPONIST_AI_MODE"] = previous_mode


if __name__ == "__main__":
    asyncio.run(run())
    print("Workroom messages E2E: OK")
