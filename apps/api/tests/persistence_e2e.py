"""Restart-aware E2E check for Postgres-backed settings and sources.

Run in three phases around an API container restart:
    python tests/persistence_e2e.py seed
    # restart the API container
    python tests/persistence_e2e.py verify
    python tests/persistence_e2e.py cleanup
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from sqlalchemy import delete, select

import auth
from database import (
    AuthSession,
    AuthSessionContext,
    ConnectedSource,
    Org,
    OrganizationMembership,
    OrgSetting,
    PasswordCredential,
    User,
    async_session,
)
from persistence import get_connected_source


OTHER_ORG_ID = "e2e-persistence-other"
TOKEN = "e2e-secret-token-must-never-be-plaintext"
EMAIL = "persistence-e2e@example.com"
PASSWORD = "persistence-e2e-password"


async def e2e_user() -> User | None:
    async with async_session() as session:
        return (
            await session.execute(select(User).where(User.email == EMAIL))
        ).scalar_one_or_none()


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
        await session.execute(delete(ConnectedSource).where(ConnectedSource.org_id == user.org_id))
        await session.execute(delete(OrgSetting).where(OrgSetting.org_id == user.org_id))
        await session.execute(delete(PasswordCredential).where(PasswordCredential.user_id == user.id))
        await session.execute(delete(OrganizationMembership).where(OrganizationMembership.user_id == user.id))
        await session.execute(delete(User).where(User.id == user.id))
        await session.execute(delete(Org).where(Org.id == user.org_id))
        await session.commit()


async def seed() -> None:
    await cleanup()
    user = await auth.register_password_user("Persistence E2E", EMAIL, PASSWORD)
    raw_session, _ = await auth.create_session(user.id)
    org_id = user.org_id
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        client.cookies.set(auth.SESSION_COOKIE, raw_session)
        settings = await client.put(
            "/settings",
            params={"org_id": org_id},
            json={"auto_confirm": True, "parallel_batch_size": 7},
        )
        assert settings.status_code == 200, settings.text
        assert settings.json()["auto_confirm"] is True, settings.text
        assert settings.json()["parallel_batch_size"] == 7, settings.text

        source = await client.post(
            "/sources",
            params={
                "org_id": org_id,
                "source_type": "local",
                "name": "Persistent E2E Documents",
            },
            json={"path": "/data/docs/e2e", "token": TOKEN},
        )
        assert source.status_code == 200, source.text
        source_payload = source.json()
        assert "config" not in source_payload, source_payload

        listed = await client.get("/sources", params={"org_id": org_id})
        assert listed.status_code == 200, listed.text
        assert listed.json()["total"] == 1, listed.text
        assert "config" not in listed.json()["sources"][0], listed.text

        isolated = await client.get("/sources", params={"org_id": OTHER_ORG_ID})
        assert isolated.status_code == 403, isolated.text

    async with async_session() as session:
        ciphertext = (
            await session.execute(
                select(ConnectedSource.config_ciphertext)
                .where(ConnectedSource.org_id == org_id)
            )
        ).scalar_one()
    assert TOKEN not in ciphertext, ciphertext
    assert "/data/docs/e2e" not in ciphertext, ciphertext
    print("persistence E2E seed: OK")


async def verify() -> None:
    user = await e2e_user()
    assert user is not None
    raw_session, _ = await auth.create_session(user.id)
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        client.cookies.set(auth.SESSION_COOKIE, raw_session)
        settings = await client.get("/settings", params={"org_id": user.org_id})
        assert settings.status_code == 200, settings.text
        assert settings.json()["auto_confirm"] is True, settings.text
        assert settings.json()["parallel_batch_size"] == 7, settings.text

        listed = await client.get("/sources", params={"org_id": user.org_id})
        assert listed.status_code == 200, listed.text
        assert listed.json()["total"] == 1, listed.text
        source_id = listed.json()["sources"][0]["id"]

    private_source = await get_connected_source(
        user.org_id, source_id, include_config=True
    )
    assert private_source is not None
    assert private_source["config"] == {
        "path": "/data/docs/e2e",
        "token": TOKEN,
    }, private_source
    print("persistence E2E restart verification: OK")


async def run() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in {"seed", "verify", "cleanup"}:
        raise SystemExit("usage: persistence_e2e.py seed|verify|cleanup")
    phase = sys.argv[1]
    if phase == "seed":
        await seed()
    elif phase == "verify":
        await verify()
    else:
        await cleanup()
        print("persistence E2E cleanup: OK")


if __name__ == "__main__":
    asyncio.run(run())
