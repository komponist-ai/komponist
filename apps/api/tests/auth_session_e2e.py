"""Provider-free E2E check for Google login and persistent browser sessions."""

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from sqlalchemy import delete, select

import auth
import main
from database import (
    AuthIdentity,
    AuthSession,
    OAuthLoginState,
    Org,
    User,
    async_session,
    init_db,
)


EMAIL = "auth-e2e@example.com"
SUBJECT = "google-auth-e2e-subject"
RETURN_TO = "/graph"
RESTART_TOKEN = "provider-free-auth-restart-token"


async def cleanup() -> None:
    async with async_session() as session:
        user = (
            await session.execute(select(User).where(User.email == EMAIL))
        ).scalar_one_or_none()
        if user is not None:
            await session.execute(
                delete(AuthSession).where(AuthSession.user_id == user.id)
            )
            await session.execute(
                delete(AuthIdentity).where(AuthIdentity.user_id == user.id)
            )
            await session.delete(user)
            org = await session.get(Org, user.org_id)
            if org is not None:
                await session.delete(org)
        await session.execute(
            delete(OAuthLoginState).where(OAuthLoginState.return_to == RETURN_TO)
        )
        await session.commit()


async def fake_exchange(code: str) -> dict:
    assert code == "provider-free-code"
    return {"access_token": "provider-free-access-token"}


async def fake_identity(access_token: str) -> dict:
    assert access_token == "provider-free-access-token"
    return {
        "sub": SUBJECT,
        "email": EMAIL,
        "email_verified": True,
        "name": "Auth E2E User",
        "picture": "https://example.test/avatar.png",
    }


async def run() -> None:
    await init_db()
    await cleanup()
    original_client_id = auth.GOOGLE_AUTH_CLIENT_ID
    original_client_secret = auth.GOOGLE_AUTH_CLIENT_SECRET
    original_exchange = auth.exchange_google_code
    original_identity = auth.fetch_google_identity

    transport = httpx.ASGITransport(app=main.app)
    try:
        auth.GOOGLE_AUTH_CLIENT_ID = "provider-free-client"
        auth.GOOGLE_AUTH_CLIENT_SECRET = "provider-free-secret"
        auth.exchange_google_code = fake_exchange
        auth.fetch_google_identity = fake_identity

        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
            follow_redirects=False,
        ) as client:
            anonymous = await client.get("/auth/session")
            assert anonymous.json() == {"authenticated": False, "user": None}

            login = await client.get(
                "/auth/login/google", params={"return_to": RETURN_TO}
            )
            assert login.status_code == 307, login.text
            login_url = urlparse(login.headers["location"])
            assert login_url.netloc == "accounts.google.com", login_url
            login_query = parse_qs(login_url.query)
            state = login_query["state"][0]
            assert login_query["scope"] == ["openid email profile"]
            assert client.cookies.get(auth.LOGIN_STATE_COOKIE) == state

            unbound_client = httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
                follow_redirects=False,
            )
            try:
                unbound = await unbound_client.get(
                    "/auth/login/google/callback",
                    params={"code": "provider-free-code", "state": state},
                )
                assert unbound.status_code == 400, unbound.text
            finally:
                await unbound_client.aclose()

            callback = await client.get(
                "/auth/login/google/callback",
                params={"code": "provider-free-code", "state": state},
            )
            assert callback.status_code == 307, callback.text
            assert callback.headers["location"] == f"{main.FRONTEND_URL}{RETURN_TO}"
            set_cookie = callback.headers["set-cookie"].lower()
            assert "httponly" in set_cookie
            assert "samesite=lax" in set_cookie
            raw_token = client.cookies.get(auth.SESSION_COOKIE)
            assert raw_token

            session_response = await client.get("/auth/session")
            payload = session_response.json()
            assert payload["authenticated"] is True, payload
            assert payload["user"]["email"] == EMAIL, payload
            assert payload["user"]["role"] == "owner", payload

            replay = await client.get(
                "/auth/login/google/callback",
                params={"code": "provider-free-code", "state": state},
            )
            assert replay.status_code == 400, replay.text

        async with async_session() as session:
            users = (
                await session.execute(select(User).where(User.email == EMAIL))
            ).scalars().all()
            identities = (
                await session.execute(
                    select(AuthIdentity).where(AuthIdentity.subject == SUBJECT)
                )
            ).scalars().all()
            stored_session = (
                await session.execute(
                    select(AuthSession).where(AuthSession.user_id == users[0].id)
                )
            ).scalar_one()
            assert len(users) == 1
            assert len(identities) == 1
            assert stored_session.token_hash != raw_token
            assert len(stored_session.token_hash) == 64

        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as restarted_client:
            restarted_client.cookies.set(auth.SESSION_COOKIE, raw_token)
            persisted = await restarted_client.get("/auth/session")
            assert persisted.json()["authenticated"] is True, persisted.text

            logout = await restarted_client.post("/auth/logout")
            assert logout.status_code == 204, logout.text
            after_logout = await restarted_client.get("/auth/session")
            assert after_logout.json() == {"authenticated": False, "user": None}

        print("Google user auth session E2E: OK")
    finally:
        auth.GOOGLE_AUTH_CLIENT_ID = original_client_id
        auth.GOOGLE_AUTH_CLIENT_SECRET = original_client_secret
        auth.exchange_google_code = original_exchange
        auth.fetch_google_identity = original_identity
        await cleanup()


async def seed_restart() -> None:
    """Persist a known test session for verification after an API restart."""
    await init_db()
    await cleanup()
    user = await auth.upsert_google_user(await fake_identity("provider-free-access-token"))
    async with async_session() as session:
        session.add(
            AuthSession(
                id=str(uuid4()),
                user_id=user.id,
                token_hash=auth._hash_token(RESTART_TOKEN),
                expires_at=(
                    datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=10)
                ),
            )
        )
        await session.commit()
    print("Google auth restart seed: OK")


async def verify_restart() -> None:
    """Verify and revoke the seeded session in the restarted API process."""
    await init_db()
    transport = httpx.ASGITransport(app=main.app)
    try:
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            client.cookies.set(auth.SESSION_COOKIE, RESTART_TOKEN)
            persisted = await client.get("/auth/session")
            payload = persisted.json()
            assert payload["authenticated"] is True, payload
            assert payload["user"]["email"] == EMAIL, payload
            logout = await client.post("/auth/logout")
            assert logout.status_code == 204, logout.text
        print("Google auth API-restart E2E: OK")
    finally:
        await cleanup()


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "flow"
    if mode == "flow":
        asyncio.run(run())
    elif mode == "seed-restart":
        asyncio.run(seed_restart())
    elif mode == "verify-restart":
        asyncio.run(verify_restart())
    else:
        raise SystemExit(
            "Usage: auth_session_e2e.py [flow|seed-restart|verify-restart]"
        )
