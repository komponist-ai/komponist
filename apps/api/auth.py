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
    AuthSessionContext,
    OAuthLoginState,
    Org,
    OrganizationInvitation,
    OrganizationMembership,
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
INVITATION_DAYS = 7
MEMBERSHIP_ROLES = {"owner", "admin", "member", "viewer"}
INVITABLE_ROLES = {"admin", "member", "viewer"}


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
        await _ensure_primary_membership(session, user)

        await session.commit()
        return user


async def _ensure_primary_membership(session, user: User) -> OrganizationMembership:
    membership = (
        await session.execute(
            select(OrganizationMembership).where(
                OrganizationMembership.user_id == user.id,
                OrganizationMembership.org_id == user.org_id,
            )
        )
    ).scalar_one_or_none()
    if membership is None:
        membership = OrganizationMembership(
            id=str(uuid4()),
            user_id=user.id,
            org_id=user.org_id,
            role="owner",
            status="active",
        )
        session.add(membership)
        await session.flush()
    return membership


async def create_session(user_id: str) -> tuple[str, AuthSession]:
    raw_token = secrets.token_urlsafe(48)
    async with async_session() as session:
        user = await session.get(User, user_id)
        if user is None:
            raise ValueError("Cannot create a session for an unknown user")
        await _ensure_primary_membership(session, user)
        session_row = AuthSession(
            id=str(uuid4()),
            user_id=user_id,
            token_hash=_hash_token(raw_token),
            expires_at=datetime.utcnow() + timedelta(days=SESSION_DAYS),
        )
        session.add(session_row)
        await session.flush()
        session.add(
            AuthSessionContext(
                session_id=session_row.id,
                active_org_id=user.org_id,
            )
        )
        await session.commit()
    return raw_token, session_row


async def _session_principal(session, raw_token: Optional[str]):
    if not raw_token or len(raw_token) > 200:
        return None
    now = datetime.utcnow()
    row = (
        await session.execute(
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
    ).one_or_none()
    if row is None:
        return None
    auth_session, user, identity = row
    await _ensure_primary_membership(session, user)

    context = await session.get(AuthSessionContext, auth_session.id)
    if context is None:
        context = AuthSessionContext(
            session_id=auth_session.id,
            active_org_id=user.org_id,
        )
        session.add(context)
        await session.flush()

    membership = (
        await session.execute(
            select(OrganizationMembership).where(
                OrganizationMembership.user_id == user.id,
                OrganizationMembership.org_id == context.active_org_id,
                OrganizationMembership.status == "active",
            )
        )
    ).scalar_one_or_none()
    if membership is None:
        membership = await _ensure_primary_membership(session, user)
        context.active_org_id = membership.org_id

    org = await session.get(Org, membership.org_id)
    if org is None:
        return None
    auth_session.last_seen_at = now
    return auth_session, user, identity, membership, org, context


def _user_payload(user, identity, membership, org) -> dict[str, Any]:
    return {
        "id": user.id,
        "org_id": org.id,
        "email": user.email,
        "name": user.name,
        "avatar_url": identity.avatar_url,
        "role": membership.role,
        "organization": {"id": org.id, "name": org.name},
    }


async def authenticated_user(raw_token: Optional[str]) -> Optional[dict[str, Any]]:
    async with async_session() as session:
        principal = await _session_principal(session, raw_token)
        if principal is None:
            return None
        _, user, identity, membership, org, _ = principal
        await session.commit()
        return _user_payload(user, identity, membership, org)


async def list_organizations(raw_token: Optional[str]) -> Optional[list[dict[str, Any]]]:
    async with async_session() as session:
        principal = await _session_principal(session, raw_token)
        if principal is None:
            return None
        _, user, _, _, _, context = principal
        rows = (
            await session.execute(
                select(OrganizationMembership, Org)
                .join(Org, Org.id == OrganizationMembership.org_id)
                .where(
                    OrganizationMembership.user_id == user.id,
                    OrganizationMembership.status == "active",
                )
                .order_by(Org.name.asc())
            )
        ).all()
        await session.commit()
        return [
            {
                "id": org.id,
                "name": org.name,
                "role": membership.role,
                "active": org.id == context.active_org_id,
            }
            for membership, org in rows
        ]


async def select_organization(raw_token: Optional[str], org_id: str) -> Optional[dict[str, Any]]:
    async with async_session() as session:
        principal = await _session_principal(session, raw_token)
        if principal is None:
            return None
        _, user, identity, _, _, context = principal
        membership = (
            await session.execute(
                select(OrganizationMembership).where(
                    OrganizationMembership.user_id == user.id,
                    OrganizationMembership.org_id == org_id,
                    OrganizationMembership.status == "active",
                )
            )
        ).scalar_one_or_none()
        org = await session.get(Org, org_id)
        if membership is None or org is None:
            raise PermissionError("User is not a member of this organization")
        context.active_org_id = org_id
        context.updated_at = datetime.utcnow()
        await session.commit()
        return _user_payload(user, identity, membership, org)


async def list_organization_members(
    raw_token: Optional[str], org_id: str
) -> Optional[list[dict[str, Any]]]:
    async with async_session() as session:
        principal = await _session_principal(session, raw_token)
        if principal is None:
            return None
        _, user, _, _, _, _ = principal
        actor = (
            await session.execute(
                select(OrganizationMembership).where(
                    OrganizationMembership.user_id == user.id,
                    OrganizationMembership.org_id == org_id,
                    OrganizationMembership.status == "active",
                )
            )
        ).scalar_one_or_none()
        if actor is None:
            raise PermissionError("User is not a member of this organization")
        rows = (
            await session.execute(
                select(OrganizationMembership, User)
                .join(User, User.id == OrganizationMembership.user_id)
                .where(
                    OrganizationMembership.org_id == org_id,
                    OrganizationMembership.status == "active",
                )
                .order_by(User.name.asc())
            )
        ).all()
        await session.commit()
        return [
            {
                "id": member.id,
                "user_id": member.user_id,
                "name": member_user.name,
                "email": member_user.email,
                "role": member.role,
            }
            for member, member_user in rows
        ]


async def create_organization_invitation(
    raw_token: Optional[str],
    org_id: str,
    email: str,
    role: str,
) -> Optional[dict[str, Any]]:
    email = email.strip().lower()
    role = role.strip().lower()
    if "@" not in email or len(email) > 255:
        raise ValueError("A valid email is required")
    if role not in INVITABLE_ROLES:
        raise ValueError("Role must be admin, member, or viewer")

    async with async_session() as session:
        principal = await _session_principal(session, raw_token)
        if principal is None:
            return None
        _, user, _, _, _, _ = principal
        actor = (
            await session.execute(
                select(OrganizationMembership).where(
                    OrganizationMembership.user_id == user.id,
                    OrganizationMembership.org_id == org_id,
                    OrganizationMembership.status == "active",
                )
            )
        ).scalar_one_or_none()
        if actor is None or actor.role not in {"owner", "admin"}:
            raise PermissionError("Only organization owners and admins can invite")
        if role == "admin" and actor.role != "owner":
            raise PermissionError("Only an owner can invite another admin")

        await session.execute(
            delete(OrganizationInvitation).where(
                OrganizationInvitation.org_id == org_id,
                OrganizationInvitation.email == email,
                OrganizationInvitation.accepted_at.is_(None),
            )
        )
        raw_invite = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(days=INVITATION_DAYS)
        session.add(
            OrganizationInvitation(
                id=str(uuid4()),
                org_id=org_id,
                email=email,
                role=role,
                token_hash=_hash_token(raw_invite),
                invited_by_user_id=user.id,
                expires_at=expires_at,
            )
        )
        await session.commit()
        return {
            "token": raw_invite,
            "email": email,
            "role": role,
            "expires_at": expires_at.isoformat(),
        }


async def accept_organization_invitation(
    raw_token: Optional[str], raw_invite: str
) -> Optional[dict[str, Any]]:
    if not raw_invite or len(raw_invite) > 200:
        raise ValueError("Invalid invitation")
    now = datetime.utcnow()
    async with async_session() as session:
        principal = await _session_principal(session, raw_token)
        if principal is None:
            return None
        _, user, identity, _, _, context = principal
        invitation = (
            await session.execute(
                select(OrganizationInvitation)
                .where(
                    OrganizationInvitation.token_hash == _hash_token(raw_invite)
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if (
            invitation is None
            or invitation.accepted_at is not None
            or invitation.expires_at <= now
        ):
            raise ValueError("Invitation is invalid, expired, or already used")
        if invitation.email != user.email.lower():
            raise PermissionError("Invitation belongs to a different email address")

        membership = (
            await session.execute(
                select(OrganizationMembership).where(
                    OrganizationMembership.user_id == user.id,
                    OrganizationMembership.org_id == invitation.org_id,
                )
            )
        ).scalar_one_or_none()
        if membership is None:
            membership = OrganizationMembership(
                id=str(uuid4()),
                user_id=user.id,
                org_id=invitation.org_id,
                role=invitation.role,
                status="active",
            )
            session.add(membership)
        else:
            role_rank = {"viewer": 0, "member": 1, "admin": 2, "owner": 3}
            if role_rank[invitation.role] > role_rank.get(membership.role, 0):
                membership.role = invitation.role
            membership.status = "active"
            membership.updated_at = now

        org = await session.get(Org, invitation.org_id)
        if org is None:
            raise ValueError("Invitation organization no longer exists")
        invitation.accepted_at = now
        invitation.accepted_by_user_id = user.id
        context.active_org_id = invitation.org_id
        context.updated_at = now
        await session.commit()
        return _user_payload(user, identity, membership, org)


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
