"""E2E check for private, persistent multi-conversation chat history."""

import asyncio
import os
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages"))

import httpx
from sqlalchemy import delete, select

import auth
import main
from core.graph import GraphClient
from database import (
    AuthIdentity,
    AuthSession,
    AuthSessionContext,
    ChatConversation,
    ChatMessageRecord,
    Org,
    OrganizationMembership,
    PasswordCredential,
    User,
    async_session,
    init_db,
)


OWNER_EMAIL = "chat-history-owner-e2e@example.com"
MEMBER_EMAIL = "chat-history-member-e2e@example.com"
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
        if user_ids:
            conversation_ids = (
                await session.execute(
                    select(ChatConversation.id).where(
                        ChatConversation.user_id.in_(user_ids)
                    )
                )
            ).scalars().all()
            if conversation_ids:
                await session.execute(
                    delete(ChatMessageRecord).where(
                        ChatMessageRecord.conversation_id.in_(conversation_ids)
                    )
                )
            await session.execute(
                delete(ChatConversation).where(ChatConversation.user_id.in_(user_ids))
            )
            session_ids = (
                await session.execute(
                    select(AuthSession.id).where(AuthSession.user_id.in_(user_ids))
                )
            ).scalars().all()
            if session_ids:
                await session.execute(
                    delete(AuthSessionContext).where(
                        AuthSessionContext.session_id.in_(session_ids)
                    )
                )
            await session.execute(delete(AuthSession).where(AuthSession.user_id.in_(user_ids)))
            await session.execute(delete(PasswordCredential).where(PasswordCredential.user_id.in_(user_ids)))
            await session.execute(delete(AuthIdentity).where(AuthIdentity.user_id.in_(user_ids)))
            await session.execute(delete(OrganizationMembership).where(OrganizationMembership.user_id.in_(user_ids)))
            await session.execute(delete(User).where(User.id.in_(user_ids)))
        if org_ids:
            await session.execute(delete(Org).where(Org.id.in_(org_ids)))
        await session.commit()


async def run() -> None:
    previous_mode = os.environ.get("KOMPONIST_AI_MODE")
    os.environ["KOMPONIST_AI_MODE"] = "mock"
    await init_db()
    await cleanup()
    GraphClient.initialize()
    transport = httpx.ASGITransport(app=main.app)

    try:
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as owner_client, httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as member_client:
            owner_registration = await owner_client.post(
                "/auth/register",
                json={"name": "Chat Owner", "email": OWNER_EMAIL, "password": PASSWORD},
            )
            assert owner_registration.status_code == 201, owner_registration.text
            owner = owner_registration.json()["user"]

            member_registration = await member_client.post(
                "/auth/register",
                json={"name": "Chat Member", "email": MEMBER_EMAIL, "password": PASSWORD},
            )
            assert member_registration.status_code == 201, member_registration.text
            member = member_registration.json()["user"]

            async with async_session() as session:
                session.add(OrganizationMembership(
                    id=str(uuid4()),
                    user_id=member["id"],
                    org_id=owner["org_id"],
                    role="member",
                    status="active",
                ))
                await session.commit()

            first = await owner_client.post(
                "/chat",
                json={
                    "org_id": owner["org_id"],
                    "message": "What company knowledge is available?",
                    "stream": False,
                },
            )
            assert first.status_code == 200, first.text
            first_payload = first.json()
            first_id = first_payload["conversation_id"]
            assert first_id

            continued = await owner_client.post(
                "/chat",
                json={
                    "org_id": owner["org_id"],
                    "conversation_id": first_id,
                    "message": "Can you summarize that?",
                    "stream": False,
                },
            )
            assert continued.status_code == 200, continued.text
            assert continued.json()["conversation_id"] == first_id

            history = await owner_client.get(
                f"/chat/conversations/{first_id}",
                params={"org_id": owner["org_id"]},
            )
            assert history.status_code == 200, history.text
            history_payload = history.json()
            assert history_payload["conversation"]["message_count"] == 4
            assert [message["role"] for message in history_payload["messages"]] == [
                "user", "assistant", "user", "assistant"
            ]
            latest_page = await owner_client.get(
                f"/chat/conversations/{first_id}",
                params={"org_id": owner["org_id"], "limit": 2},
            )
            latest_payload = latest_page.json()
            assert latest_payload["has_more"] is True, latest_payload
            assert len(latest_payload["messages"]) == 2, latest_payload
            older_page = await owner_client.get(
                f"/chat/conversations/{first_id}",
                params={
                    "org_id": owner["org_id"],
                    "limit": 2,
                    "before": latest_payload["next_before"],
                },
            )
            older_payload = older_page.json()
            assert older_payload["has_more"] is False, older_payload
            assert len(older_payload["messages"]) == 2, older_payload

            second = await owner_client.post(
                "/chat",
                json={
                    "org_id": owner["org_id"],
                    "message": "List every confirmed goal.",
                    "stream": False,
                },
            )
            assert second.status_code == 200, second.text
            second_id = second.json()["conversation_id"]
            assert second_id != first_id

            listed = await owner_client.get(
                "/chat/conversations", params={"org_id": owner["org_id"]}
            )
            assert listed.status_code == 200, listed.text
            rows = listed.json()["conversations"]
            assert len(rows) == 2, rows
            assert rows[0]["id"] == second_id
            assert rows[1]["message_count"] == 4
            conversation_page = await owner_client.get(
                "/chat/conversations",
                params={"org_id": owner["org_id"], "limit": 1},
            )
            assert conversation_page.json()["has_more"] is True
            assert conversation_page.json()["total"] == 2
            assert len(conversation_page.json()["conversations"]) == 1

            renamed = await owner_client.patch(
                f"/chat/conversations/{first_id}",
                params={"org_id": owner["org_id"]},
                json={"title": "Architecture follow-up"},
            )
            assert renamed.status_code == 200, renamed.text
            assert renamed.json()["title"] == "Architecture follow-up"

            member_list = await member_client.get(
                "/chat/conversations", params={"org_id": owner["org_id"]}
            )
            assert member_list.status_code == 200, member_list.text
            assert member_list.json()["conversations"] == []
            hidden = await member_client.get(
                f"/chat/conversations/{first_id}",
                params={"org_id": owner["org_id"]},
            )
            assert hidden.status_code == 404, hidden.text

            removed = await owner_client.delete(
                f"/chat/conversations/{first_id}",
                params={"org_id": owner["org_id"]},
            )
            assert removed.status_code == 204, removed.text
            missing = await owner_client.get(
                f"/chat/conversations/{first_id}",
                params={"org_id": owner["org_id"]},
            )
            assert missing.status_code == 404, missing.text

        print("Chat history E2E: OK")
    finally:
        await cleanup()
        await GraphClient.close()
        if previous_mode is None:
            os.environ.pop("KOMPONIST_AI_MODE", None)
        else:
            os.environ["KOMPONIST_AI_MODE"] = previous_mode


if __name__ == "__main__":
    asyncio.run(run())
