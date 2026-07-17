"""Authenticated direct-upload contract without external model calls."""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from sqlalchemy import delete, select

import auth
import main
from database import (
    AuthSession, AuthSessionContext, ConnectedSource, Org,
    OrganizationMembership, PasswordCredential, User, async_session, init_db,
)


EMAIL = "document-upload-e2e@example.com"


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
        await session.execute(delete(PasswordCredential).where(PasswordCredential.user_id == user.id))
        await session.execute(delete(ConnectedSource).where(ConnectedSource.org_id == user.org_id))
        await session.execute(delete(OrganizationMembership).where(OrganizationMembership.user_id == user.id))
        await session.execute(delete(Org).where(Org.id == user.org_id))
        await session.execute(delete(User).where(User.id == user.id))
        await session.commit()


async def run() -> None:
    await init_db()
    await cleanup()
    user = await auth.register_password_user(
        "Upload E2E", EMAIL, "document-upload-password"
    )
    raw_session, _ = await auth.create_session(user.id)
    captured = []

    async def fake_extraction(source_item, auto_confirm=False):
        captured.append((source_item, auto_confirm))
        return {
            "entities_created": 2,
            "relationships_created": 0,
            "entity_ids": ["entity-1", "entity-2"],
        }

    transport = httpx.ASGITransport(app=main.app)
    try:
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as anonymous:
            denied = await anonymous.post(
                "/sources/upload",
                params={"org_id": user.org_id},
                files={"files": ("strategy.md", b"# Strategy", "text/markdown")},
            )
            assert denied.status_code == 401, denied.text

        with patch.object(main, "run_extraction", new=fake_extraction):
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as client:
                client.cookies.set(auth.SESSION_COOKIE, raw_session)
                response = await client.post(
                    "/sources/upload",
                    params={"org_id": user.org_id},
                    files=[
                        ("files", ("strategy.md", b"# Strategy\nDecision: Ship upload.", "text/markdown")),
                        ("files", ("image.png", b"not-an-image", "image/png")),
                    ],
                )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["status"] == "partial", payload
        assert payload["files_processed"] == 1, payload
        assert payload["entities_created"] == 2, payload
        assert payload["review_mode"] is True, payload
        assert captured[0][0].reference.startswith("upload:strategy.md:"), captured
        assert captured[0][0].url == "upload://strategy.md", captured
        assert captured[0][0].source.value == "upload", captured
        assert captured[0][1] is False

        async with async_session() as session:
            source = (
                await session.execute(
                    select(ConnectedSource).where(
                        ConnectedSource.org_id == user.org_id,
                        ConnectedSource.source_type == "upload",
                    )
                )
            ).scalar_one()
            assert source.item_count == 1

        print("Document upload E2E: OK")
    finally:
        await cleanup()


if __name__ == "__main__":
    asyncio.run(run())
