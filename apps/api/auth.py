"""Google and password login with persistent, revocable browser sessions."""

import asyncio
import base64
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
    ChatConversation,
    ChatMessageRecord,
    ConnectedSource,
    Department,
    DepartmentMembership,
    GeneratedArtifact,
    OAuthLoginState,
    Org,
    OrganizationInvitation,
    OrganizationMembership,
    PasswordCredential,
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
DEPARTMENT_COLORS = {"orange", "teal", "blue", "violet", "rose", "amber"}
PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 128
PASSWORD_SCRYPT_N = 2**14
PASSWORD_SCRYPT_R = 8
PASSWORD_SCRYPT_P = 1


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _normalized_email(value: str) -> str:
    email = (value or "").strip().lower()
    if (
        len(email) < 3
        or len(email) > 255
        or email.count("@") != 1
        or not all(email.split("@"))
        or any(character.isspace() for character in email)
    ):
        raise ValueError("A valid email address is required")
    return email


def _validated_password(value: str) -> str:
    if len(value or "") < PASSWORD_MIN_LENGTH:
        raise ValueError(f"Password must be at least {PASSWORD_MIN_LENGTH} characters")
    if len(value) > PASSWORD_MAX_LENGTH:
        raise ValueError(f"Password must be at most {PASSWORD_MAX_LENGTH} characters")
    return value


def _password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=PASSWORD_SCRYPT_N,
        r=PASSWORD_SCRYPT_R,
        p=PASSWORD_SCRYPT_P,
        dklen=32,
    )
    return "$".join(
        (
            "scrypt",
            str(PASSWORD_SCRYPT_N),
            str(PASSWORD_SCRYPT_R),
            str(PASSWORD_SCRYPT_P),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        )
    )


def _password_matches(password: str, encoded_hash: str) -> bool:
    try:
        algorithm, n, r, p, encoded_salt, encoded_digest = encoded_hash.split("$", 5)
        if algorithm != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(encoded_salt.encode("ascii"))
        expected = base64.urlsafe_b64decode(encoded_digest.encode("ascii"))
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
        return secrets.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


async def register_password_user(name: str, email: str, password: str) -> User:
    """Create a user, personal organization, and first-party credential."""
    normalized_email = _normalized_email(email)
    normalized_name = (name or "").strip()
    if not normalized_name or len(normalized_name) > 255:
        raise ValueError("A name between 1 and 255 characters is required")
    validated_password = _validated_password(password)
    encoded_hash = await asyncio.to_thread(_password_hash, validated_password)

    async with async_session() as session:
        existing_user = (
            await session.execute(select(User).where(User.email == normalized_email))
        ).scalar_one_or_none()
        if existing_user is not None:
            raise ValueError("An account with this email already exists")

        org_id = str(uuid4())
        user = User(
            id=str(uuid4()),
            org_id=org_id,
            email=normalized_email,
            name=normalized_name,
        )
        session.add(Org(id=org_id, name=f"{normalized_name}'s workspace"))
        session.add(user)
        await session.flush()
        session.add(
            PasswordCredential(user_id=user.id, password_hash=encoded_hash)
        )
        await _ensure_primary_membership(session, user)
        await session.commit()
        return user


async def authenticate_password_user(email: str, password: str) -> Optional[User]:
    """Validate an email/password pair without exposing which field failed."""
    try:
        normalized_email = _normalized_email(email)
    except ValueError:
        normalized_email = "invalid@example.invalid"

    async with async_session() as session:
        row = (
            await session.execute(
                select(User, PasswordCredential)
                .join(PasswordCredential, PasswordCredential.user_id == User.id)
                .where(User.email == normalized_email)
            )
        ).one_or_none()

    if row is None:
        await asyncio.to_thread(_password_hash, password[:PASSWORD_MAX_LENGTH] or "invalid-password")
        return None
    user, credential = row
    matches = await asyncio.to_thread(
        _password_matches, password[:PASSWORD_MAX_LENGTH], credential.password_hash
    )
    return user if matches else None


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
            .outerjoin(
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


async def _membership_department_ids(session, membership) -> list[str]:
    if membership.role in {"owner", "admin"}:
        return []
    return list(
        (
            await session.execute(
                select(DepartmentMembership.department_id)
                .join(Department, Department.id == DepartmentMembership.department_id)
                .where(
                    DepartmentMembership.org_id == membership.org_id,
                    DepartmentMembership.user_id == membership.user_id,
                    Department.org_id == membership.org_id,
                )
                .order_by(Department.name.asc())
            )
        ).scalars()
    )


def _user_payload(
    user, identity, membership, org, department_ids: Optional[list[str]] = None
) -> dict[str, Any]:
    return {
        "id": user.id,
        "org_id": org.id,
        "email": user.email,
        "name": user.name,
        "avatar_url": identity.avatar_url if identity is not None else None,
        "role": membership.role,
        "department_ids": department_ids or [],
        "access_all_departments": membership.role in {"owner", "admin"},
        "organization": {"id": org.id, "name": org.name},
    }


async def authenticated_user(raw_token: Optional[str]) -> Optional[dict[str, Any]]:
    async with async_session() as session:
        principal = await _session_principal(session, raw_token)
        if principal is None:
            return None
        _, user, identity, membership, org, _ = principal
        await session.commit()
        department_ids = await _membership_department_ids(session, membership)
        return _user_payload(user, identity, membership, org, department_ids)


async def authorize_organization(
    raw_token: Optional[str],
    org_id: str,
    allowed_roles: Optional[set[str]] = None,
) -> Optional[dict[str, Any]]:
    """Authenticate a browser session and authorize membership in one org."""
    async with async_session() as session:
        principal = await _session_principal(session, raw_token)
        if principal is None:
            return None
        _, user, identity, _, _, _ = principal
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
        if allowed_roles and membership.role not in allowed_roles:
            raise PermissionError("Owner or admin access is required")
        await session.commit()
        department_ids = await _membership_department_ids(session, membership)
        return _user_payload(user, identity, membership, org, department_ids)


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
        department_ids = await _membership_department_ids(session, membership)
        return _user_payload(user, identity, membership, org, department_ids)


async def _active_membership(session, user_id: str, org_id: str):
    return (
        await session.execute(
            select(OrganizationMembership).where(
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.org_id == org_id,
                OrganizationMembership.status == "active",
            )
        )
    ).scalar_one_or_none()


async def _management_actor(session, user_id: str, org_id: str):
    actor = await _active_membership(session, user_id, org_id)
    if actor is None or actor.role not in {"owner", "admin"}:
        raise PermissionError("Only organization owners and admins can manage the team")
    return actor


async def _validated_department_ids(
    session, org_id: str, department_ids: Optional[list[str]]
) -> list[str]:
    normalized = list(dict.fromkeys(department_ids or []))
    if len(normalized) > 25:
        raise ValueError("A member can belong to at most 25 departments")
    if not normalized:
        return []
    found = set(
        (
            await session.execute(
                select(Department.id).where(
                    Department.org_id == org_id,
                    Department.id.in_(normalized),
                )
            )
        ).scalars()
    )
    if found != set(normalized):
        raise ValueError("One or more departments do not belong to this organization")
    return normalized


async def _clear_member_chat_history(session, org_id: str, user_id: str) -> None:
    """Revoke cached derived content when a member's knowledge scope changes."""
    conversations = list(
        (
            await session.execute(
                select(ChatConversation.id).where(
                    ChatConversation.org_id == org_id,
                    ChatConversation.user_id == user_id,
                )
            )
        ).scalars()
    )
    if conversations:
        await session.execute(
            delete(ChatMessageRecord).where(
                ChatMessageRecord.org_id == org_id,
                ChatMessageRecord.conversation_id.in_(conversations),
            )
        )
        await session.execute(
            delete(ChatConversation).where(
                ChatConversation.org_id == org_id,
                ChatConversation.user_id == user_id,
            )
        )
    await session.execute(
        delete(GeneratedArtifact).where(
            GeneratedArtifact.org_id == org_id,
            GeneratedArtifact.user_id == user_id,
        )
    )


async def list_organization_departments(
    raw_token: Optional[str], org_id: str
) -> Optional[list[dict[str, Any]]]:
    """List departments visible to the signed-in organization member."""
    async with async_session() as session:
        principal = await _session_principal(session, raw_token)
        if principal is None:
            return None
        _, user, _, _, _, _ = principal
        actor = await _active_membership(session, user.id, org_id)
        if actor is None:
            raise PermissionError("User is not a member of this organization")

        query = select(Department).where(Department.org_id == org_id)
        if actor.role not in {"owner", "admin"}:
            query = query.join(
                DepartmentMembership,
                DepartmentMembership.department_id == Department.id,
            ).where(DepartmentMembership.user_id == user.id)
        departments = list(
            (await session.execute(query.order_by(Department.name.asc()))).scalars()
        )
        department_ids = [department.id for department in departments]
        assignments = []
        if department_ids:
            assignments = (
                await session.execute(
                    select(DepartmentMembership).where(
                        DepartmentMembership.org_id == org_id,
                        DepartmentMembership.department_id.in_(department_ids),
                    )
                )
            ).scalars().all()
        counts = {
            department_id: sum(
                assignment.department_id == department_id
                for assignment in assignments
            )
            for department_id in department_ids
        }
        await session.commit()
        return [
            {
                "id": department.id,
                "name": department.name,
                "description": department.description,
                "color": department.color,
                "member_count": counts.get(department.id, 0),
                "created_at": department.created_at.isoformat(),
            }
            for department in departments
        ]


async def create_organization_department(
    raw_token: Optional[str],
    org_id: str,
    name: str,
    description: Optional[str] = None,
    color: str = "orange",
) -> Optional[dict[str, Any]]:
    normalized_name = " ".join((name or "").split()).strip()
    normalized_description = " ".join((description or "").split()).strip() or None
    normalized_color = color.strip().lower()
    if not normalized_name or len(normalized_name) > 100:
        raise ValueError("Department name must be between 1 and 100 characters")
    if normalized_description and len(normalized_description) > 500:
        raise ValueError("Department description must be at most 500 characters")
    if normalized_color not in DEPARTMENT_COLORS:
        raise ValueError("Unsupported department color")

    async with async_session() as session:
        principal = await _session_principal(session, raw_token)
        if principal is None:
            return None
        _, user, _, _, _, _ = principal
        await _management_actor(session, user.id, org_id)
        existing = (
            await session.execute(
                select(Department).where(
                    Department.org_id == org_id,
                    Department.name == normalized_name,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise ValueError("A department with this name already exists")
        department = Department(
            id=str(uuid4()),
            org_id=org_id,
            name=normalized_name,
            description=normalized_description,
            color=normalized_color,
        )
        session.add(department)
        await session.commit()
        return {
            "id": department.id,
            "name": department.name,
            "description": department.description,
            "color": department.color,
            "member_count": 0,
            "created_at": department.created_at.isoformat(),
        }


async def update_organization_department(
    raw_token: Optional[str],
    org_id: str,
    department_id: str,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    color: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    async with async_session() as session:
        principal = await _session_principal(session, raw_token)
        if principal is None:
            return None
        _, user, _, _, _, _ = principal
        await _management_actor(session, user.id, org_id)
        department = await session.get(Department, department_id)
        if department is None or department.org_id != org_id:
            raise ValueError("Department not found")
        if name is not None:
            normalized_name = " ".join(name.split()).strip()
            if not normalized_name or len(normalized_name) > 100:
                raise ValueError("Department name must be between 1 and 100 characters")
            duplicate = (
                await session.execute(
                    select(Department).where(
                        Department.org_id == org_id,
                        Department.name == normalized_name,
                        Department.id != department_id,
                    )
                )
            ).scalar_one_or_none()
            if duplicate is not None:
                raise ValueError("A department with this name already exists")
            department.name = normalized_name
        if description is not None:
            normalized_description = " ".join(description.split()).strip()
            if len(normalized_description) > 500:
                raise ValueError("Department description must be at most 500 characters")
            department.description = normalized_description or None
        if color is not None:
            normalized_color = color.strip().lower()
            if normalized_color not in DEPARTMENT_COLORS:
                raise ValueError("Unsupported department color")
            department.color = normalized_color
        department.updated_at = datetime.utcnow()
        await session.commit()
        return {
            "id": department.id,
            "name": department.name,
            "description": department.description,
            "color": department.color,
        }


async def delete_organization_department(
    raw_token: Optional[str],
    org_id: str,
    department_id: str,
    reassign_to: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Delete a department and optionally move assignments to another department."""
    async with async_session() as session:
        principal = await _session_principal(session, raw_token)
        if principal is None:
            return None
        _, user, _, _, _, _ = principal
        await _management_actor(session, user.id, org_id)
        department = await session.get(Department, department_id)
        if department is None or department.org_id != org_id:
            raise ValueError("Department not found")
        target = None
        if reassign_to:
            if reassign_to == department_id:
                raise ValueError("Replacement department must be different")
            target = await session.get(Department, reassign_to)
            if target is None or target.org_id != org_id:
                raise ValueError("Replacement department not found")

        assignments = list(
            (
                await session.execute(
                    select(DepartmentMembership).where(
                        DepartmentMembership.org_id == org_id,
                        DepartmentMembership.department_id == department_id,
                    )
                )
            ).scalars()
        )
        if target is not None:
            existing_target_users = set(
                (
                    await session.execute(
                        select(DepartmentMembership.user_id).where(
                            DepartmentMembership.department_id == target.id
                        )
                    )
                ).scalars()
            )
            for assignment in assignments:
                if assignment.user_id not in existing_target_users:
                    session.add(
                        DepartmentMembership(
                            id=str(uuid4()),
                            org_id=org_id,
                            department_id=target.id,
                            user_id=assignment.user_id,
                        )
                    )
        await session.execute(
            delete(DepartmentMembership).where(
                DepartmentMembership.org_id == org_id,
                DepartmentMembership.department_id == department_id,
            )
        )
        await session.execute(
            delete(Department).where(
                Department.id == department_id,
                Department.org_id == org_id,
            )
        )
        sources = list(
            (
                await session.execute(
                    select(ConnectedSource).where(
                        ConnectedSource.org_id == org_id,
                        ConnectedSource.department_id == department_id,
                    )
                )
            ).scalars()
        )
        for source in sources:
            source.department_id = target.id if target else None
        for assigned_user_id in {assignment.user_id for assignment in assignments}:
            await _clear_member_chat_history(session, org_id, assigned_user_id)
        await session.commit()
        return {
            "id": department_id,
            "reassigned_to": target.id if target else None,
            "members_moved": len(assignments),
        }


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
        assignment_rows = (
            await session.execute(
                select(DepartmentMembership, Department)
                .join(Department, Department.id == DepartmentMembership.department_id)
                .where(DepartmentMembership.org_id == org_id)
                .order_by(Department.name.asc())
            )
        ).all()
        departments_by_user: dict[str, list[dict[str, str]]] = {}
        for assignment, department in assignment_rows:
            departments_by_user.setdefault(assignment.user_id, []).append({
                "id": department.id,
                "name": department.name,
                "color": department.color,
            })
        await session.commit()
        return [
            {
                "id": member.id,
                "user_id": member.user_id,
                "name": member_user.name,
                "email": member_user.email,
                "role": member.role,
                "departments": departments_by_user.get(member.user_id, []),
            }
            for member, member_user in rows
        ]


async def update_organization_member(
    raw_token: Optional[str],
    org_id: str,
    membership_id: str,
    *,
    role: Optional[str] = None,
    department_ids: Optional[list[str]] = None,
) -> Optional[dict[str, Any]]:
    async with async_session() as session:
        principal = await _session_principal(session, raw_token)
        if principal is None:
            return None
        _, user, _, _, _, _ = principal
        actor = await _management_actor(session, user.id, org_id)
        target = await session.get(OrganizationMembership, membership_id)
        if target is None or target.org_id != org_id or target.status != "active":
            raise ValueError("Organization member not found")
        if target.role == "owner":
            raise PermissionError("The organization owner cannot be reorganized")
        if actor.role != "owner" and target.role == "admin":
            raise PermissionError("Only the owner can manage board/admin members")

        normalized_role = role.strip().lower() if role is not None else target.role
        if normalized_role not in INVITABLE_ROLES:
            raise ValueError("Role must be admin, member, or viewer")
        if (target.role == "admin" or normalized_role == "admin") and actor.role != "owner":
            raise PermissionError("Only the owner can grant or remove board/admin access")
        normalized_departments = await _validated_department_ids(
            session, org_id, department_ids
        ) if department_ids is not None else None

        target.role = normalized_role
        target.updated_at = datetime.utcnow()
        if normalized_departments is not None:
            await session.execute(
                delete(DepartmentMembership).where(
                    DepartmentMembership.org_id == org_id,
                    DepartmentMembership.user_id == target.user_id,
                )
            )
            if normalized_role not in {"owner", "admin"}:
                for department_id in normalized_departments:
                    session.add(
                        DepartmentMembership(
                            id=str(uuid4()),
                            org_id=org_id,
                            department_id=department_id,
                            user_id=target.user_id,
                        )
                    )
        await _clear_member_chat_history(session, org_id, target.user_id)
        await session.commit()
        return {"id": target.id, "role": target.role}


async def remove_organization_member(
    raw_token: Optional[str], org_id: str, membership_id: str
) -> Optional[dict[str, Any]]:
    async with async_session() as session:
        principal = await _session_principal(session, raw_token)
        if principal is None:
            return None
        _, user, _, _, _, _ = principal
        actor = await _management_actor(session, user.id, org_id)
        target = await session.get(OrganizationMembership, membership_id)
        if target is None or target.org_id != org_id or target.status != "active":
            raise ValueError("Organization member not found")
        if target.role == "owner":
            raise PermissionError("The organization owner cannot be removed")
        if actor.role != "owner" and target.role == "admin":
            raise PermissionError("Only the owner can remove board/admin members")
        await session.execute(
            delete(DepartmentMembership).where(
                DepartmentMembership.org_id == org_id,
                DepartmentMembership.user_id == target.user_id,
            )
        )
        target.status = "removed"
        target.updated_at = datetime.utcnow()
        await _clear_member_chat_history(session, org_id, target.user_id)
        await session.commit()
        return {"id": target.id, "user_id": target.user_id, "status": "removed"}


async def create_organization_invitation(
    raw_token: Optional[str],
    org_id: str,
    email: str,
    role: str,
    department_ids: Optional[list[str]] = None,
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
        normalized_departments = await _validated_department_ids(
            session, org_id, department_ids
        )
        if role == "admin":
            normalized_departments = []

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
                department_ids=normalized_departments,
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
            "department_ids": normalized_departments,
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

        await session.execute(
            delete(DepartmentMembership).where(
                DepartmentMembership.org_id == invitation.org_id,
                DepartmentMembership.user_id == user.id,
            )
        )
        if membership.role not in {"owner", "admin"}:
            department_ids = await _validated_department_ids(
                session, invitation.org_id, invitation.department_ids
            )
            for department_id in department_ids:
                session.add(
                    DepartmentMembership(
                        id=str(uuid4()),
                        org_id=invitation.org_id,
                        department_id=department_id,
                        user_id=user.id,
                    )
                )

        org = await session.get(Org, invitation.org_id)
        if org is None:
            raise ValueError("Invitation organization no longer exists")
        invitation.accepted_at = now
        invitation.accepted_by_user_id = user.id
        context.active_org_id = invitation.org_id
        context.updated_at = now
        await session.commit()
        department_ids = await _membership_department_ids(session, membership)
        return _user_payload(user, identity, membership, org, department_ids)


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
