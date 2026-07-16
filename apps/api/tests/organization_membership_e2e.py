"""E2E check for multi-organization membership and invitation workflows."""

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
    User,
    async_session,
    init_db,
)


OWNER_EMAIL = "org-owner-e2e@example.com"
MEMBER_EMAIL = "org-member-e2e@example.com"


def identity(subject: str, email: str, name: str) -> dict:
    return {
        "sub": subject,
        "email": email,
        "email_verified": True,
        "name": name,
    }


async def cleanup() -> None:
    async with async_session() as session:
        users = (
            await session.execute(
                select(User).where(User.email.in_([OWNER_EMAIL, MEMBER_EMAIL]))
            )
        ).scalars().all()
        user_ids = [user.id for user in users]
        org_ids = [user.org_id for user in users]
        if user_ids:
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
            await session.execute(
                delete(AuthSession).where(AuthSession.user_id.in_(user_ids))
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
            await session.execute(
                delete(OrganizationInvitation).where(
                    OrganizationInvitation.org_id.in_(org_ids)
                )
            )
            await session.execute(delete(Org).where(Org.id.in_(org_ids)))
        await session.commit()


async def run() -> None:
    await init_db()
    await cleanup()
    owner = await auth.upsert_google_user(
        identity("org-owner-e2e-subject", OWNER_EMAIL, "Customer Owner")
    )
    member = await auth.upsert_google_user(
        identity("org-member-e2e-subject", MEMBER_EMAIL, "Customer Member")
    )
    owner_token, _ = await auth.create_session(owner.id)
    member_token, _ = await auth.create_session(member.id)
    transport = httpx.ASGITransport(app=main.app)

    try:
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as owner_client, httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as member_client:
            owner_client.cookies.set(auth.SESSION_COOKIE, owner_token)
            member_client.cookies.set(auth.SESSION_COOKIE, member_token)

            hidden = await member_client.get(
                f"/auth/organizations/{owner.org_id}/members"
            )
            assert hidden.status_code == 403, hidden.text

            invitation_response = await owner_client.post(
                f"/auth/organizations/{owner.org_id}/invitations",
                json={"email": MEMBER_EMAIL, "role": "member"},
            )
            assert invitation_response.status_code == 201, invitation_response.text
            invitation = invitation_response.json()
            raw_invite = invitation["token"]
            assert raw_invite in invitation["invite_url"]

            async with async_session() as session:
                stored_invite = (
                    await session.execute(
                        select(OrganizationInvitation).where(
                            OrganizationInvitation.org_id == owner.org_id,
                            OrganizationInvitation.email == MEMBER_EMAIL,
                        )
                    )
                ).scalar_one()
                assert stored_invite.token_hash != raw_invite
                assert len(stored_invite.token_hash) == 64

            accepted = await member_client.post(
                "/auth/invitations/accept", json={"token": raw_invite}
            )
            assert accepted.status_code == 200, accepted.text
            accepted_user = accepted.json()["user"]
            assert accepted_user["org_id"] == owner.org_id, accepted_user
            assert accepted_user["role"] == "member", accepted_user

            organizations = await member_client.get("/auth/organizations")
            organization_rows = organizations.json()["organizations"]
            assert len(organization_rows) == 2, organization_rows
            assert sum(row["active"] for row in organization_rows) == 1
            assert next(row for row in organization_rows if row["active"])["id"] == owner.org_id

            members = await owner_client.get(
                f"/auth/organizations/{owner.org_id}/members"
            )
            assert members.status_code == 200, members.text
            member_rows = members.json()["members"]
            assert {row["email"] for row in member_rows} == {
                OWNER_EMAIL,
                MEMBER_EMAIL,
            }
            assert {row["role"] for row in member_rows} == {"owner", "member"}

            forbidden_invite = await member_client.post(
                f"/auth/organizations/{owner.org_id}/invitations",
                json={"email": "third@example.com", "role": "viewer"},
            )
            assert forbidden_invite.status_code == 403, forbidden_invite.text

            personal = await member_client.post(
                f"/auth/organizations/{member.org_id}/select"
            )
            assert personal.status_code == 200, personal.text
            assert personal.json()["user"]["org_id"] == member.org_id
            assert personal.json()["user"]["role"] == "owner"

            customer = await member_client.post(
                f"/auth/organizations/{owner.org_id}/select"
            )
            assert customer.status_code == 200, customer.text
            assert customer.json()["user"]["role"] == "member"

            replay = await member_client.post(
                "/auth/invitations/accept", json={"token": raw_invite}
            )
            assert replay.status_code == 400, replay.text

        print("Organization membership and invitation E2E: OK")
    finally:
        await cleanup()


if __name__ == "__main__":
    asyncio.run(run())
