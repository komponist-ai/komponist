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
from persistence import authenticate_api_key


EMAIL = "platform-api-e2e@example.com"


async def cleanup() -> None:
    async with async_session() as session:
        user = (
            await session.execute(select(User).where(User.email == EMAIL))
        ).scalar_one_or_none()
        if user is None:
            return
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
        await session.execute(delete(OrganizationMembership).where(OrganizationMembership.user_id == user.id))
        await session.execute(delete(User).where(User.id == user.id))
        await session.execute(delete(Org).where(Org.id == user.org_id))
        await session.commit()


async def run() -> None:
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

        print("Platform AI and API keys E2E: OK")
    finally:
        await cleanup()


if __name__ == "__main__":
    asyncio.run(run())
