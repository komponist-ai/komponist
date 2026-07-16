"""Google user login and persistent, revocable browser sessions."""

import hashlib
import os
import secrets
from datetime import datetime, timedelta
from typing import Any, Optional
from urllib.parse import urlencode
from uuid import uuid4

import httpx
from sqlalchemy import delete, select

from database import (
    AuthIdentity,
    AuthSession,
    OAuthLoginState,
    Org,
    User,
    async_session,
)


GOOGLE_AUTH_CLIENT_ID = os.getenv("GOOGLE_AUTH_CLIENT_ID", "")
GOOGLE_AUTH_CLIENT_SECRET = os.getenv("GOOGLE_AUTH_CLIENT_SECRET", "")
GOOGLE_AUTH_REDIRECT_URI = os.getenv(
    "GOOGLE_AUTH_REDIRECT_URI", "http://localhost:8000/auth/login/google/callback"
)
SESSION_COOKIE = "komponist_session"
LOGIN_STATE_COOKIE = "komponist_login_state"
SESSION_DAYS = 30
STATE_MINUTES = 10


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _safe_return_to(value: str) -> str:
    value = (value or "/").strip()
    if not value.startswith("/") or value.startswith("//") or len(value) > 500:
        return "/"
    return value


def login_state_matches(query_state: str, cookie_state: Optional[str]) -> bool:
    """Bind an OAuth callback to the browser that initiated the login."""
    if not query_state or not cookie_state:
        return False
    if len(query_state) > 200 or len(cookie_state) > 200:
        return False
    return secrets.compare_digest(query_state, cookie_state)


async def create_login_state(return_to: str = "/") -> str:
    """Create a short-lived, single-use OAuth state."""
    raw_state = secrets.token_urlsafe(32)
    now = datetime.utcnow()
    async with async_session() as session:
        await session.execute(
            delete(OAuthLoginState).where(OAuthLoginState.expires_at <= now)
        )
        session.add(
            OAuthLoginState(
                state_hash=_hash_token(raw_state),
                return_to=_safe_return_to(return_to),
                expires_at=now + timedelta(minutes=STATE_MINUTES),
            )
        )
        await session.commit()
    return raw_state


async def consume_login_state(raw_state: str) -> Optional[str]:
    """Consume an OAuth state exactly once and return its safe redirect path."""
    if not raw_state or len(raw_state) > 200:
        return None
    now = datetime.utcnow()
    async with async_session() as session:
        result = await session.execute(
            select(OAuthLoginState)
            .where(OAuthLoginState.state_hash == _hash_token(raw_state))
            .with_for_update()
        )
        state = result.scalar_one_or_none()
        if state is None or state.expires_at <= now:
            if state is not None:
                await session.delete(state)
                await session.commit()
            return None
        return_to = state.return_to
        await session.delete(state)
        await session.commit()
        return return_to


def google_authorization_url(state: str) -> str:
    params = {
        "client_id": GOOGLE_AUTH_CLIENT_ID,
        "redirect_uri": GOOGLE_AUTH_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    }
    return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"


async def exchange_google_code(code: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": GOOGLE_AUTH_CLIENT_ID,
                "client_secret": GOOGLE_AUTH_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": GOOGLE_AUTH_REDIRECT_URI,
            },
        )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload.get("access_token"), str):
        raise ValueError("Google token response contained no access token")
    return payload


async def fetch_google_identity(access_token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    response.raise_for_status()
    identity = response.json()
    subject = identity.get("sub")
    email = identity.get("email")
    if not isinstance(subject, str) or not subject or len(subject) > 255:
        raise ValueError("Google identity contained no valid subject")
    if not isinstance(email, str) or "@" not in email or len(email) > 255:
        raise ValueError("Google identity contained no valid email")
    if identity.get("email_verified") is not True:
        raise ValueError("Google email is not verified")
    return identity


async def upsert_google_user(identity: dict[str, Any]) -> User:
    """Create a personal organization on first login, or update the known user."""
    subject = identity["sub"]
    email = identity["email"].strip().lower()
    name = (identity.get("name") or email.split("@", 1)[0]).strip()[:255]
    avatar = identity.get("picture")
    if not isinstance(avatar, str) or len(avatar) > 2000:
        avatar = None

    async with async_session() as session:
        stored_identity = (
            await session.execute(
                select(AuthIdentity).where(
                    AuthIdentity.provider == "google",
                    AuthIdentity.subject == subject,
                )
            )
        ).scalar_one_or_none()
        user = None
        if stored_identity is not None:
            user = await session.get(User, stored_identity.user_id)
            if user is None:
                raise ValueError("Google identity points to a missing user")
        else:
            user = (
                await session.execute(select(User).where(User.email == email))
            ).scalar_one_or_none()
            if user is not None:
                conflicting_identity = (
                    await session.execute(
                        select(AuthIdentity).where(
                            AuthIdentity.provider == "google",
                            AuthIdentity.user_id == user.id,
                        )
                    )
                ).scalar_one_or_none()
                if conflicting_identity is not None:
                    raise ValueError("Email is already linked to another Google account")

        email_owner = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if email_owner is not None and user is not None and email_owner.id != user.id:
            raise ValueError("Email is already used by another account")

        if user is None:
            org_id = str(uuid4())
            user = User(
                id=str(uuid4()),
                org_id=org_id,
                email=email,
                name=name,
            )
            session.add(Org(id=org_id, name=f"{name}'s workspace"))
            session.add(user)
            await session.flush()

        if stored_identity is None:
            stored_identity = AuthIdentity(
                id=str(uuid4()),
                user_id=user.id,
                provider="google",
                subject=subject,
                email=email,
                avatar_url=avatar,
            )
            session.add(stored_identity)
        else:
            stored_identity.email = email
            stored_identity.avatar_url = avatar
            stored_identity.updated_at = datetime.utcnow()

        user.email = email
        user.name = name

        await session.commit()
        return user


async def create_session(user_id: str) -> tuple[str, AuthSession]:
    raw_token = secrets.token_urlsafe(48)
    session_row = AuthSession(
        id=str(uuid4()),
        user_id=user_id,
        token_hash=_hash_token(raw_token),
        expires_at=datetime.utcnow() + timedelta(days=SESSION_DAYS),
    )
    async with async_session() as session:
        session.add(session_row)
        await session.commit()
    return raw_token, session_row


async def authenticated_user(raw_token: Optional[str]) -> Optional[dict[str, Any]]:
    if not raw_token or len(raw_token) > 200:
        return None
    now = datetime.utcnow()
    async with async_session() as session:
        result = await session.execute(
            select(AuthSession, User, AuthIdentity)
            .join(User, User.id == AuthSession.user_id)
            .join(
                AuthIdentity,
                (AuthIdentity.user_id == User.id)
                & (AuthIdentity.provider == "google"),
            )
            .where(
                AuthSession.token_hash == _hash_token(raw_token),
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now,
            )
        )
        row = result.one_or_none()
        if row is None:
            return None
        auth_session, user, identity = row
        auth_session.last_seen_at = now
        await session.commit()
        return {
            "id": user.id,
            "org_id": user.org_id,
            "email": user.email,
            "name": user.name,
            "avatar_url": identity.avatar_url,
            "role": "owner",
        }


async def revoke_session(raw_token: Optional[str]) -> None:
    if not raw_token or len(raw_token) > 200:
        return
    async with async_session() as session:
        auth_session = (
            await session.execute(
                select(AuthSession).where(
                    AuthSession.token_hash == _hash_token(raw_token),
                    AuthSession.revoked_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if auth_session is not None:
            auth_session.revoked_at = datetime.utcnow()
            await session.commit()
