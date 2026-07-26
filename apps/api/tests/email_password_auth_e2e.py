"""Provider-free E2E check for first-party email/password authentication."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from sqlalchemy import delete, select

import auth
import main
from database import (
    AuthIdentity,
    AuthSession,
    AuthSessionContext,
    Org,
    OrganizationInvitation,
    OrganizationMembership,
    PasswordCredential,
    User,
    async_session,
    init_db,
)


EMAIL = "password-auth-e2e@example.com"
PASSWORD = "correct horse battery staple"


async def cleanup() -> None:
    async with async_session() as session:
        user = (
            await session.execute(select(User).where(User.email == EMAIL))
        ).scalar_one_or_none()
        if user is None:
            return
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
        await session.execute(
            delete(OrganizationInvitation).where(
                (OrganizationInvitation.invited_by_user_id == user.id)
                | (OrganizationInvitation.accepted_by_user_id == user.id)
                | (OrganizationInvitation.org_id == user.org_id)
            )
        )
        await session.execute(
            delete(OrganizationMembership).where(
                OrganizationMembership.user_id == user.id
            )
        )
        await session.execute(
            delete(PasswordCredential).where(PasswordCredential.user_id == user.id)
        )
        await session.execute(
            delete(AuthIdentity).where(AuthIdentity.user_id == user.id)
        )
        org = await session.get(Org, user.org_id)
        await session.delete(user)
        if org is not None:
            await session.delete(org)
        await session.commit()


async def run() -> None:
    await init_db()
    await cleanup()
    transport = httpx.ASGITransport(app=main.app)
    try:
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            registration = await client.post(
                "/auth/register",
                json={
                    "name": "Password Auth User",
                    "email": EMAIL.upper(),
                    "password": PASSWORD,
                    "organization_name": "CampusKollektiv",
                },
            )
            assert registration.status_code == 201, registration.text
            assert client.cookies.get(auth.SESSION_COOKIE)
            registered_user = registration.json()["user"]
            assert registered_user["email"] == EMAIL
            assert registered_user["role"] == "owner"
            assert registered_user["avatar_url"] is None
            assert registered_user["organization"]["name"] == "CampusKollektiv"

            session_response = await client.get("/auth/session")
            assert session_response.json()["authenticated"] is True

            duplicate = await client.post(
                "/auth/register",
                json={
                    "name": "Duplicate",
                    "email": EMAIL,
                    "password": PASSWORD,
                },
            )
            assert duplicate.status_code == 409, duplicate.text

            logout = await client.post("/auth/logout")
            assert logout.status_code == 204, logout.text

            wrong_password = await client.post(
                "/auth/login/email",
                json={"email": EMAIL, "password": "wrong-password"},
            )
            assert wrong_password.status_code == 401, wrong_password.text
            assert wrong_password.json()["detail"] == "Invalid email or password"

            login = await client.post(
                "/auth/login/email",
                json={"email": EMAIL, "password": PASSWORD},
            )
            assert login.status_code == 200, login.text
            assert login.json()["user"]["email"] == EMAIL
            assert client.cookies.get(auth.SESSION_COOKIE)

            organizations = await client.get("/auth/organizations")
            assert organizations.status_code == 200, organizations.text
            assert len(organizations.json()["organizations"]) == 1

        async with async_session() as session:
            user = (
                await session.execute(select(User).where(User.email == EMAIL))
            ).scalar_one()
            credential = await session.get(PasswordCredential, user.id)
            assert credential is not None
            assert credential.password_hash.startswith("scrypt$")
            assert PASSWORD not in credential.password_hash

        print("Email/password auth E2E: OK")
    finally:
        await cleanup()


if __name__ == "__main__":
    asyncio.run(run())
