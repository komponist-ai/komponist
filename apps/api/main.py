"""
Komponist API

FastAPI application for webhooks, REST endpoints, and health checks.
The programmable company brain.
"""

import os
import hashlib
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

import httpx
from fastapi import FastAPI, HTTPException, UploadFile, File, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, RedirectResponse
from pydantic import BaseModel, Field

import sys
sys.path.append("../../packages")

from core.graph import GraphClient
from core.schema import GraphSchema
from core.export import export_brain_yaml
from core.import_ import import_brain_yaml
from database import init_db, health_check_db
from persistence import (
    authenticate_api_key,
    create_api_key,
    create_connected_source,
    delete_connected_source,
    get_connected_source,
    list_connected_sources,
    list_api_keys,
    load_org_settings,
    save_org_settings,
    revoke_api_key,
    update_connected_source,
    upsert_single_source_type,
)


# Import security utilities
from security import validate_org_id, check_rate_limit


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    GraphClient.initialize()
    await init_db()
    await GraphSchema.apply_schema()
    print("✓ Databases initialized")

    yield

    # Shutdown
    await GraphClient.close()
    print("✓ Connections closed")


app = FastAPI(
    title="Komponist API",
    description="The programmable company brain. Company context, composed for every agent.",
    version="0.1.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Next.js dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def get_org_settings(org_id: str) -> dict:
    """Get settings for an org with defaults."""
    defaults = {
        "auto_confirm": False,
        "extraction_model": os.getenv("KOMPONIST_LLM_MODEL", "gpt-5.6-terra"),
        "parallel_batch_size": 5,
    }
    settings = await load_org_settings(org_id) or {}
    return {**defaults, **settings}


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Komponist API",
        "version": "0.1.0",
        "tagline": "The programmable company brain"
    }


@app.get("/healthz")
async def health_check():
    """
    Health check endpoint.

    Verifies connectivity to Neo4j and Postgres.
    """
    neo4j_health = await GraphClient.health_check()
    postgres_health = await health_check_db()

    overall_healthy = (
        neo4j_health["status"] == "healthy" and
        postgres_health["status"] == "healthy"
    )

    return {
        "status": "healthy" if overall_healthy else "degraded",
        "services": {
            "neo4j": neo4j_health,
            "postgres": postgres_health
        }
    }


# Queue and entity management routes


class ConfirmEntityRequest(BaseModel):
    statement: Optional[str] = None


class MergeEntityRequest(BaseModel):
    target_id: str


class OrgSettingsUpdate(BaseModel):
    auto_confirm: Optional[bool] = None
    parallel_batch_size: Optional[int] = None


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


async def _authorized_org_user(
    request: Request, org_id: str, *, manage: bool = False
) -> dict:
    import auth

    try:
        user = await auth.authorize_organization(
            request.cookies.get(auth.SESSION_COOKIE),
            org_id,
            {"owner", "admin"} if manage else None,
        )
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


async def _get_entity_lifecycle(entity_id: str, org_id: str) -> dict:
    """Load the lifecycle fields required by review mutations."""
    result = await GraphClient.run_query(
        """
        MATCH (e:Entity {id: $entity_id, org_id: $org_id})
        RETURN e.id AS id, e.entity_type AS entity_type, e.status AS status
        """,
        {"entity_id": entity_id, "org_id": org_id},
    )
    if not result:
        raise HTTPException(status_code=404, detail="Entity not found")
    return result[0]


@app.get("/queue")
async def get_queue(org_id: str = "default-org"):
    """Get review queue (proposed entities)."""
    query = """
    MATCH (e:Entity {org_id: $org_id, status: 'proposed'})
    OPTIONAL MATCH (e)-[:CITED_BY]->(ev:Evidence)
    OPTIONAL MATCH (e)-[r:RELATES_TO]->(related:Entity)
    WHERE r.score > 0.80
    RETURN
        e.id as id,
        e.entity_type as entity_type,
        e.statement as statement,
        e.detail as detail,
        e.confidence as confidence,
        e.created_at as created_at,
        collect(DISTINCT ev{.id, .source, .reference, .url, .source_date}) as evidence,
        collect(DISTINCT {id: related.id, statement: related.statement, score: r.score}) as related_to
    ORDER BY e.created_at DESC
    """

    results = await GraphClient.run_query(query, {"org_id": org_id})

    # Filter out null evidence/related_to
    for r in results:
        r["evidence"] = [e for e in r.get("evidence", []) if e.get("id")]
        r["related_to"] = [rel for rel in r.get("related_to", []) if rel.get("id")]

    return {"items": results, "total": len(results)}


@app.get("/entities")
async def list_entities(
    org_id: str = "default-org",
    status: str = "confirmed",
    entity_type: Optional[str] = None,
    limit: int = 100
):
    """List brain entities."""
    type_filter = ""
    if entity_type:
        type_filter = "AND e.entity_type = $entity_type"

    query = f"""
    MATCH (e:Entity {{org_id: $org_id, status: $status}})
    {type_filter}
    OPTIONAL MATCH (e)-[:CITED_BY]->(ev:Evidence)
    RETURN
        e.id as id,
        e.entity_type as entity_type,
        e.statement as statement,
        e.detail as detail,
        e.confidence as confidence,
        e.confirmed_at as confirmed_at,
        e.created_at as created_at,
        collect(ev{{.id, .source, .reference, .url}}) as evidence
    ORDER BY e.confirmed_at DESC, e.created_at DESC
    LIMIT $limit
    """

    params = {"org_id": org_id, "status": status, "limit": limit}
    if entity_type:
        params["entity_type"] = entity_type

    results = await GraphClient.run_query(query, params)

    # Filter nulls
    for r in results:
        r["evidence"] = [e for e in r.get("evidence", []) if e.get("id")]

    return {"entities": results, "total": len(results)}


@app.get("/entities/{entity_id}")
async def get_entity(entity_id: str, org_id: str = "default-org"):
    """Get entity details."""
    query = """
    MATCH (e:Entity {id: $entity_id, org_id: $org_id})
    OPTIONAL MATCH (e)-[:CITED_BY]->(ev:Evidence)
    OPTIONAL MATCH (e)-[r:SUPERSEDES]->(old:Entity)
    RETURN
        e.id as id,
        e.entity_type as entity_type,
        e.statement as statement,
        e.detail as detail,
        e.status as status,
        e.confidence as confidence,
        e.created_at as created_at,
        e.confirmed_at as confirmed_at,
        collect(DISTINCT ev{.id, .source, .reference, .url, .excerpt, .source_date}) as evidence,
        collect(DISTINCT old{.id, .statement, .status}) as superseded
    """

    results = await GraphClient.run_query(query, {"entity_id": entity_id, "org_id": org_id})

    if not results:
        return {"error": "Entity not found"}, 404

    entity = results[0]
    entity["evidence"] = [e for e in entity.get("evidence", []) if e.get("id")]
    entity["superseded"] = [s for s in entity.get("superseded", []) if s.get("id")]

    return entity


@app.get("/entities/{entity_id}/neighborhood")
async def get_entity_neighborhood(entity_id: str, org_id: str = "default-org"):
    """Get entity 1-hop neighborhood."""
    from core.queries import BrainQueries

    expansion = await BrainQueries.context_expansion(
        org_id=org_id,
        seed_ids=[entity_id],
        max_hops=1
    )

    return expansion


@app.post("/entities/{entity_id}/confirm")
async def confirm_entity(
    entity_id: str,
    payload: Optional[ConfirmEntityRequest] = None,
    org_id: str = "default-org",
    statement: Optional[str] = None,
):
    """Confirm a proposed entity."""
    entity = await _get_entity_lifecycle(entity_id, org_id)
    if entity["status"] != "proposed":
        raise HTTPException(
            status_code=409,
            detail="Only proposed entities can be confirmed",
        )

    edited_statement = payload.statement if payload else statement
    if edited_statement is not None:
        edited_statement = edited_statement.strip()
        if not edited_statement:
            raise HTTPException(status_code=422, detail="statement cannot be empty")

    # Update statement if provided
    if edited_statement:
        query = """
        MATCH (e:Entity {id: $entity_id, org_id: $org_id, status: 'proposed'})
        SET e.statement = $statement,
            e.status = 'confirmed',
            e.confirmed_at = datetime(),
            e.updated_at = datetime()
        RETURN e.id as id, e.status as status
        """
        params = {
            "entity_id": entity_id,
            "org_id": org_id,
            "statement": edited_statement,
        }
    else:
        query = """
        MATCH (e:Entity {id: $entity_id, org_id: $org_id, status: 'proposed'})
        SET e.status = 'confirmed',
            e.confirmed_at = datetime(),
            e.updated_at = datetime()
        RETURN e.id as id, e.status as status
        """
        params = {"entity_id": entity_id, "org_id": org_id}

    result = await GraphClient.run_query(query, params)

    if not result:
        raise HTTPException(status_code=409, detail="Entity lifecycle changed")

    return result[0]


@app.post("/entities/{entity_id}/reject")
async def reject_entity(entity_id: str, org_id: str = "default-org"):
    """Reject a proposed entity."""
    entity = await _get_entity_lifecycle(entity_id, org_id)
    if entity["status"] != "proposed":
        raise HTTPException(
            status_code=409,
            detail="Only proposed entities can be rejected",
        )

    query = """
    MATCH (e:Entity {id: $entity_id, org_id: $org_id, status: 'proposed'})
    SET e.status = 'rejected',
        e.updated_at = datetime()
    RETURN e.id as id, e.status as status
    """

    result = await GraphClient.run_query(query, {"entity_id": entity_id, "org_id": org_id})

    if not result:
        raise HTTPException(status_code=409, detail="Entity lifecycle changed")

    return result[0]


@app.post("/entities/{entity_id}/merge")
async def merge_entity(
    entity_id: str,
    payload: Optional[MergeEntityRequest] = None,
    target_id: Optional[str] = None,
    org_id: str = "default-org",
):
    """Merge entity into another."""
    resolved_target_id = payload.target_id if payload else target_id
    if not resolved_target_id:
        raise HTTPException(status_code=422, detail="target_id is required")
    if resolved_target_id == entity_id:
        raise HTTPException(status_code=422, detail="Cannot merge an entity into itself")

    source = await _get_entity_lifecycle(entity_id, org_id)
    target = await _get_entity_lifecycle(resolved_target_id, org_id)
    if source["status"] != "proposed":
        raise HTTPException(
            status_code=409,
            detail="Only proposed entities can be merged",
        )
    if target["status"] not in {"proposed", "confirmed"}:
        raise HTTPException(
            status_code=409,
            detail="Merge target must be proposed or confirmed",
        )
    if source["entity_type"] != target["entity_type"]:
        raise HTTPException(
            status_code=409,
            detail="Entities must have the same type to be merged",
        )

    # Attach the source entity's evidence to the target, then delete source
    query = """
    MATCH (source:Entity {id: $entity_id, org_id: $org_id})
    MATCH (target:Entity {id: $target_id, org_id: $org_id})
    OPTIONAL MATCH (source)-[:CITED_BY]->(ev:Evidence)
    WITH source, target, collect(ev) as evidences
    FOREACH (ev IN evidences |
        MERGE (target)-[:CITED_BY]->(ev)
    )
    DETACH DELETE source
    RETURN target.id as target_id, size(evidences) as evidence_moved
    """

    result = await GraphClient.run_query(query, {
        "entity_id": entity_id,
        "target_id": resolved_target_id,
        "org_id": org_id
    })

    if not result:
        raise HTTPException(status_code=409, detail="Entity lifecycle changed")

    return {
        "merged": entity_id,
        "into": resolved_target_id,
        "evidence_moved": result[0]["evidence_moved"],
    }


# Webhook handlers
@app.post("/webhooks/github")
async def github_webhook():
    """GitHub webhook handler."""
    return {"status": "received"}


@app.post("/webhooks/slack")
async def slack_webhook():
    """Slack webhook handler."""
    return {"status": "received"}


@app.post("/webhooks/notion")
async def notion_webhook():
    """Notion webhook handler (placeholder - Notion doesn't have official webhooks yet)."""
    return {"status": "received"}


@app.post("/webhooks/google")
async def google_webhook():
    """Google Drive webhook handler."""
    return {"status": "received"}


FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")


# =============================================================================
# User authentication endpoints
# =============================================================================

class OrganizationInvitationRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    role: str = Field(default="member", max_length=20)


class AcceptInvitationRequest(BaseModel):
    token: str = Field(min_length=20, max_length=200)


class EmailRegistrationRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=12, max_length=128)


class EmailLoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)


def _set_session_cookie(response: Response, raw_token: str) -> None:
    import auth

    response.set_cookie(
        key=auth.SESSION_COOKIE,
        value=raw_token,
        max_age=auth.SESSION_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=os.getenv("KOMPONIST_COOKIE_SECURE", "false").lower() == "true",
        samesite="lax",
        path="/",
    )


def _check_auth_rate_limit(request: Request) -> None:
    client_host = request.client.host if request.client else "unknown"
    if not check_rate_limit(f"user-auth:{client_host}", limit=10):
        raise HTTPException(status_code=429, detail="Too many authentication attempts")


@app.post("/auth/register", status_code=201)
async def register_with_email(
    payload: EmailRegistrationRequest,
    request: Request,
    response: Response,
):
    """Create an email/password user and issue the standard session cookie."""
    import auth

    _check_auth_rate_limit(request)
    try:
        user = await auth.register_password_user(
            payload.name, payload.email, payload.password
        )
    except ValueError as error:
        status = 409 if "already exists" in str(error) else 400
        raise HTTPException(status_code=status, detail=str(error)) from error
    raw_token, _ = await auth.create_session(user.id)
    _set_session_cookie(response, raw_token)
    return {"user": await auth.authenticated_user(raw_token)}


@app.post("/auth/login/email")
async def login_with_email(
    payload: EmailLoginRequest,
    request: Request,
    response: Response,
):
    """Authenticate a first-party password without revealing which field failed."""
    import auth

    _check_auth_rate_limit(request)
    user = await auth.authenticate_password_user(payload.email, payload.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    raw_token, _ = await auth.create_session(user.id)
    _set_session_cookie(response, raw_token)
    return {"user": await auth.authenticated_user(raw_token)}

@app.get("/auth/login/google")
async def google_login_start(return_to: str = "/"):
    """Start Google OIDC login for a Komponist user."""
    import auth

    if not auth.GOOGLE_AUTH_CLIENT_ID or not auth.GOOGLE_AUTH_CLIENT_SECRET:
        raise HTTPException(status_code=503, detail="Google user login is not configured")
    state = await auth.create_login_state(return_to)
    response = RedirectResponse(auth.google_authorization_url(state))
    response.set_cookie(
        key=auth.LOGIN_STATE_COOKIE,
        value=state,
        max_age=auth.STATE_MINUTES * 60,
        httponly=True,
        secure=os.getenv("KOMPONIST_COOKIE_SECURE", "false").lower() == "true",
        samesite="lax",
        path="/auth/login/google/callback",
    )
    return response


@app.get("/auth/login/google/callback")
async def google_login_callback(request: Request, code: str, state: str):
    """Complete Google login and issue a persistent HttpOnly session cookie."""
    import auth

    if not auth.login_state_matches(
        state, request.cookies.get(auth.LOGIN_STATE_COOKIE)
    ):
        raise HTTPException(status_code=400, detail="Login state does not match browser")
    return_to = await auth.consume_login_state(state)
    if return_to is None:
        raise HTTPException(status_code=400, detail="Invalid or expired login state")
    try:
        tokens = await auth.exchange_google_code(code)
        identity = await auth.fetch_google_identity(tokens["access_token"])
        user = await auth.upsert_google_user(identity)
        raw_token, _ = await auth.create_session(user.id)
    except (httpx.HTTPError, ValueError) as error:
        print(f"[User Auth] Google callback failed: {type(error).__name__}")
        raise HTTPException(status_code=400, detail="Google login failed") from error

    response = RedirectResponse(f"{FRONTEND_URL}{return_to}")
    _set_session_cookie(response, raw_token)
    response.delete_cookie(
        auth.LOGIN_STATE_COOKIE,
        path="/auth/login/google/callback",
        secure=os.getenv("KOMPONIST_COOKIE_SECURE", "false").lower() == "true",
        httponly=True,
        samesite="lax",
    )
    return response


@app.get("/auth/session")
async def get_auth_session(request: Request):
    """Return the current browser session without exposing its bearer token."""
    import auth

    user = await auth.authenticated_user(request.cookies.get(auth.SESSION_COOKIE))
    return {"authenticated": user is not None, "user": user}


@app.post("/auth/logout", status_code=204)
async def logout(request: Request, response: Response):
    """Revoke the current session and clear its browser cookie."""
    import auth

    await auth.revoke_session(request.cookies.get(auth.SESSION_COOKIE))
    response.delete_cookie(
        auth.SESSION_COOKIE,
        path="/",
        secure=os.getenv("KOMPONIST_COOKIE_SECURE", "false").lower() == "true",
        httponly=True,
        samesite="lax",
    )


@app.get("/auth/organizations")
async def get_auth_organizations(request: Request):
    """List all organizations the signed-in user belongs to."""
    import auth

    organizations = await auth.list_organizations(
        request.cookies.get(auth.SESSION_COOKIE)
    )
    if organizations is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return {"organizations": organizations}


@app.post("/auth/organizations/{org_id}/select")
async def select_auth_organization(org_id: str, request: Request):
    """Switch the active organization for the current browser session."""
    import auth

    try:
        user = await auth.select_organization(
            request.cookies.get(auth.SESSION_COOKIE), org_id
        )
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return {"user": user}


@app.get("/auth/organizations/{org_id}/members")
async def get_organization_members(org_id: str, request: Request):
    """List active members of an organization visible to the signed-in user."""
    import auth

    try:
        members = await auth.list_organization_members(
            request.cookies.get(auth.SESSION_COOKIE), org_id
        )
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    if members is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return {"members": members}


@app.post("/auth/organizations/{org_id}/invitations", status_code=201)
async def invite_organization_member(
    org_id: str,
    payload: OrganizationInvitationRequest,
    request: Request,
):
    """Create a single-use invite link. Email delivery will be added later."""
    import auth
    from urllib.parse import urlencode

    try:
        invitation = await auth.create_organization_invitation(
            request.cookies.get(auth.SESSION_COOKIE),
            org_id,
            payload.email,
            payload.role,
        )
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if invitation is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    invitation["invite_url"] = (
        f"{FRONTEND_URL}/invite?{urlencode({'token': invitation['token']})}"
    )
    return invitation


@app.post("/auth/invitations/accept")
async def accept_organization_invitation(
    payload: AcceptInvitationRequest,
    request: Request,
):
    """Accept an invite matching the signed-in user's verified Google email."""
    import auth

    try:
        user = await auth.accept_organization_invitation(
            request.cookies.get(auth.SESSION_COOKIE), payload.token
        )
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return {"user": user}


def _validated_oauth_org(org_id: str) -> str:
    """Accept only org identifiers that are safe to persist and redirect."""
    if not validate_org_id(org_id):
        raise HTTPException(status_code=400, detail="Invalid organization ID")
    return org_id


def _oauth_redirect(source: str, org_id: str, status: str) -> RedirectResponse:
    """Build a callback redirect without reflecting provider errors or secrets."""
    from urllib.parse import urlencode

    query = urlencode({"source": source, "status": status, "org": org_id})
    return RedirectResponse(url=f"{FRONTEND_URL}/onboard?{query}")


def _required_oauth_token(tokens: dict, provider: str) -> str:
    token = tokens.get("access_token")
    if not isinstance(token, str) or not token.strip():
        raise ValueError(f"{provider} OAuth response contained no access token")
    return token.strip()


# =============================================================================
# Notion connector endpoints
# =============================================================================

@app.get("/auth/notion")
async def notion_auth_start(org: str):
    """Start Notion OAuth flow."""
    from integrations.notion import get_oauth_url, NOTION_CLIENT_ID
    org = _validated_oauth_org(org)
    if not NOTION_CLIENT_ID:
        return {"error": "NOTION_CLIENT_ID not configured. Use token-based auth instead.", "use_token": True}
    url = get_oauth_url(state=org)
    return {"auth_url": url}


@app.post("/auth/notion/token")
async def notion_token_connect(org_id: str, token: str):
    """
    Connect Notion using an Internal Integration token.

    This is the easy setup path - no OAuth app needed.
    User creates an integration at notion.so/my-integrations and pastes the token.
    """
    from integrations.notion import validate_token
    # Validate the token
    user_info = await validate_token(token)

    # Get workspace/bot name
    bot_info = user_info.get("bot", {})
    workspace_name = bot_info.get("workspace_name", "Notion Workspace")

    await upsert_single_source_type(
        org_id=org_id,
        source_type="notion",
        name=workspace_name,
        config={"token": token},
    )

    print(f"[Notion] Token validated for org {org_id}: {workspace_name}")

    return {
        "status": "connected",
        "bot": bot_info,
        "name": workspace_name,
        "message": "Token validated. Share pages with your integration to sync them."
    }


@app.get("/auth/notion/callback")
async def notion_auth_callback(code: str, state: str):
    """Handle Notion OAuth callback."""
    from integrations.notion import exchange_code
    state = _validated_oauth_org(state)
    try:
        tokens = await exchange_code(code)
        access_token = _required_oauth_token(tokens, "Notion")
        await upsert_single_source_type(
            org_id=state,
            source_type="notion",
            name=tokens.get("workspace_name") or "Notion Workspace",
            config={
                "token": access_token,
                "workspace_id": tokens.get("workspace_id"),
                "bot_id": tokens.get("bot_id"),
                "oauth": True,
            },
        )
        return _oauth_redirect("notion", state, "connected")
    except Exception as error:
        print(f"[Notion OAuth] Callback failed for org {state}: {type(error).__name__}")
        return _oauth_redirect("notion", state, "error")


@app.get("/auth/slack")
async def slack_auth_start(org: str):
    """Start Slack OAuth flow."""
    from integrations.slack import get_oauth_url
    org = _validated_oauth_org(org)
    url = get_oauth_url(state=org)
    return {"auth_url": url}


@app.get("/auth/slack/callback")
async def slack_auth_callback(code: str, state: str):
    """Handle Slack OAuth callback."""
    from integrations.slack import exchange_code
    state = _validated_oauth_org(state)
    try:
        tokens = await exchange_code(code)
        access_token = _required_oauth_token(tokens, "Slack")
        team = tokens.get("team") if isinstance(tokens.get("team"), dict) else {}
        await upsert_single_source_type(
            org_id=state,
            source_type="slack",
            name=team.get("name") or "Slack Workspace",
            config={
                "token": access_token,
                "team_id": team.get("id"),
                "bot_user_id": tokens.get("bot_user_id"),
                "scope": tokens.get("scope"),
                "oauth": True,
            },
        )
        return _oauth_redirect("slack", state, "connected")
    except Exception as error:
        print(f"[Slack OAuth] Callback failed for org {state}: {type(error).__name__}")
        return _oauth_redirect("slack", state, "error")


@app.get("/auth/google")
async def google_auth_start(org: str):
    """Start Google OAuth flow."""
    from integrations.google import get_oauth_url
    org = _validated_oauth_org(org)
    url = get_oauth_url(state=org)
    return {"auth_url": url}


@app.get("/auth/google/callback")
async def google_auth_callback(code: str, state: str):
    """Handle Google OAuth callback."""
    from integrations.google import exchange_code
    state = _validated_oauth_org(state)
    try:
        tokens = await exchange_code(code)
        access_token = _required_oauth_token(tokens, "Google")
        config = {
            "access_token": access_token,
            "expires_in": tokens.get("expires_in"),
            "scope": tokens.get("scope"),
            "token_type": tokens.get("token_type"),
            "oauth": True,
        }
        refresh_token = tokens.get("refresh_token")
        if isinstance(refresh_token, str) and refresh_token.strip():
            config["refresh_token"] = refresh_token.strip()
        await upsert_single_source_type(
            org_id=state,
            source_type="google",
            name="Google Workspace",
            config=config,
            preserve_existing_config=True,
        )
        return _oauth_redirect("google", state, "connected")
    except Exception as error:
        print(f"[Google OAuth] Callback failed for org {state}: {type(error).__name__}")
        return _oauth_redirect("google", state, "error")


# =============================================================================
# Export / Import endpoints
# =============================================================================

@app.get("/export", response_class=PlainTextResponse)
async def export_brain_endpoint(
    org_id: str = Query("default-org", description="Organization ID to export"),
    include_embeddings: bool = Query(False, description="Include embedding vectors (large!)"),
    include_rejected: bool = Query(False, description="Include rejected entities")
):
    """
    Export the brain to portable YAML format.

    Returns a YAML file containing all entities, relationships, evidence,
    and workpacks for the organization.
    """
    yaml_content = await export_brain_yaml(
        org_id=org_id,
        include_embeddings=include_embeddings,
        include_rejected=include_rejected
    )

    return PlainTextResponse(
        content=yaml_content,
        media_type="application/x-yaml",
        headers={
            "Content-Disposition": f"attachment; filename=komponist-brain-{org_id}.yaml"
        }
    )


@app.post("/import")
async def import_brain_endpoint(
    file: UploadFile = File(..., description="YAML export file to import"),
    org_id: Optional[str] = Query(None, description="Override org_id (uses export's if not provided)"),
    mode: str = Query("merge", description="Import mode: merge, replace, or skip_existing")
):
    """
    Import a brain export.

    Modes:
    - merge: Update existing entities, create new ones (default)
    - skip_existing: Only import entities that don't exist
    - replace: Clear and replace all data (dangerous!)
    """
    if mode not in ["merge", "skip_existing", "replace"]:
        return {"error": f"Invalid mode: {mode}. Use merge, skip_existing, or replace."}

    # Read uploaded file
    content = await file.read()
    yaml_content = content.decode("utf-8")

    # Import
    result = await import_brain_yaml(
        yaml_content=yaml_content,
        org_id=org_id,
        mode=mode
    )

    return result


# =============================================================================
# Sources management
# =============================================================================

@app.get("/sources")
async def list_sources(org_id: str = Query("default-org")):
    """List connected sources for an organization."""
    org_sources = await list_connected_sources(org_id)
    return {"sources": org_sources, "total": len(org_sources)}


@app.post("/sources")
async def add_source(
    org_id: str = Query("default-org"),
    source_type: str = Query(..., description="Source type: notion, slack, google, local, upload"),
    name: str = Query(..., description="Display name for the source"),
    config: dict = None
):
    """Register a connected source."""
    if source_type not in {"notion", "slack", "google", "local", "upload"}:
        raise HTTPException(status_code=400, detail="Unsupported source type")
    return await create_connected_source(
        org_id=org_id,
        source_type=source_type,
        name=name,
        config=config or {},
    )


@app.delete("/sources/{source_id}")
async def remove_source(
    source_id: str,
    org_id: str = Query("default-org"),
    remove_data: bool = Query(False)
):
    """
    Remove a connected source.

    Args:
        source_id: ID of the source to remove
        org_id: Organization ID
        remove_data: If True, also delete all entities and evidence from this source
    """
    # Get source info before removing
    source = await get_connected_source(org_id, source_id, include_config=True)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    entities_deleted = 0
    evidence_deleted = 0

    if remove_data and source:
        source_type = source.get("type", "").lower()

        try:
            # Step 1: Delete entities that came from this source
            # (delete entities that have CITED_BY relationship to evidence from this source)
            delete_entities_query = """
            MATCH (e:Entity {org_id: $org_id})-[:CITED_BY]->(ev:Evidence)
            WHERE toLower(ev.source) = $source_type
            DETACH DELETE e
            RETURN count(e) as deleted
            """
            result = await GraphClient.run_query(delete_entities_query, {
                "org_id": org_id,
                "source_type": source_type
            })
            if result:
                entities_deleted = result[0].get("deleted", 0)

            # Step 2: Delete evidence from this source
            delete_evidence_query = """
            MATCH (ev:Evidence {org_id: $org_id})
            WHERE toLower(ev.source) = $source_type
            DETACH DELETE ev
            RETURN count(ev) as deleted
            """
            result = await GraphClient.run_query(delete_evidence_query, {
                "org_id": org_id,
                "source_type": source_type
            })
            if result:
                evidence_deleted = result[0].get("deleted", 0)

            print(f"[Disconnect] Removed {entities_deleted} entities, {evidence_deleted} evidence from {source_type}")

        except Exception as e:
            print(f"[Disconnect] Error removing data: {e}")
            import traceback
            traceback.print_exc()

    await delete_connected_source(org_id, source_id)

    return {
        "status": "removed",
        "source_id": source_id,
        "data_removed": remove_data,
        "entities_deleted": entities_deleted,
        "evidence_deleted": evidence_deleted
    }


@app.post("/sources/{source_id}/sync")
async def sync_source(source_id: str, org_id: str = Query("default-org")):
    """
    Sync a connected source - fetch data and extract facts.
    """
    from datetime import datetime

    # Find the source
    source = await get_connected_source(org_id, source_id, include_config=True)

    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    await update_connected_source(org_id, source_id, status="syncing")

    try:
        if source["type"] == "notion":
            result = await sync_notion_source(org_id, source)
        elif source["type"] == "local":
            result = await sync_local_source(org_id, source)
        else:
            raise ValueError(f"Sync not implemented for {source['type']}")

        await update_connected_source(
            org_id,
            source_id,
            status="connected",
            last_sync=datetime.utcnow(),
            item_count=result.get("items_processed", 0),
        )

        return result

    except Exception as e:
        await update_connected_source(org_id, source_id, status="error")
        raise HTTPException(status_code=400, detail=str(e))


async def sync_notion_source(org_id: str, source: dict) -> dict:
    """Sync Notion pages and extract facts with parallel processing."""
    import asyncio
    from integrations.notion import search_notion, get_page_content, normalize_page

    token = source.get("config", {}).get("token")
    if not token:
        raise ValueError("No token found for Notion source")

    print(f"[Notion Sync] Starting sync for org {org_id}")

    # Collect all pages first
    all_pages = []
    start_cursor = None

    while True:
        result = await search_notion(
            access_token=token,
            filter_type="page",
            start_cursor=start_cursor
        )

        pages = result.get("results", [])
        all_pages.extend(pages)

        if not result.get("has_more"):
            break
        start_cursor = result.get("next_cursor")

    print(f"[Notion Sync] Found {len(all_pages)} pages total, processing in parallel...")

    # Get org settings
    settings = await get_org_settings(org_id)
    auto_confirm = settings.get("auto_confirm", True)
    batch_size = settings.get("parallel_batch_size", 5)

    print(f"[Notion Sync] Auto-confirm: {auto_confirm}, Batch size: {batch_size}")

    # Process pages in parallel batches
    total_entities = 0
    total_relationships = 0
    pages_processed = 0

    async def process_page(page):
        """Process a single page."""
        try:
            page_id = page["id"]
            content = await get_page_content(token, page_id)

            if content and len(content.strip()) > 50:  # Skip near-empty pages
                source_item = normalize_page(page, content, org_id)
                print(f"[Notion Sync] Processing: {source_item.title[:40]}...")

                result = await run_extraction(source_item, auto_confirm=auto_confirm)
                return {
                    "success": True,
                    "entities": result.get("entities_created", 0),
                    "relationships": result.get("relationships_created", 0)
                }
            return {"success": True, "entities": 0, "relationships": 0}
        except Exception as e:
            print(f"[Notion Sync] Error: {e}")
            return {"success": False, "entities": 0, "relationships": 0}

    # Process in batches
    for i in range(0, len(all_pages), batch_size):
        batch = all_pages[i:i + batch_size]
        print(f"[Notion Sync] Processing batch {i // batch_size + 1}/{(len(all_pages) + batch_size - 1) // batch_size}")

        # Run batch in parallel
        results = await asyncio.gather(*[process_page(page) for page in batch])

        for r in results:
            if r["success"]:
                pages_processed += 1
                total_entities += r["entities"]
                total_relationships += r["relationships"]

    print(f"[Notion Sync] Complete: {pages_processed} pages, {total_entities} entities, {total_relationships} relationships")

    return {
        "status": "complete",
        "items_processed": pages_processed,
        "entities_created": total_entities,
        "relationships_created": total_relationships
    }


async def sync_local_source(org_id: str, source: dict) -> dict:
    """Sync local documents."""
    from integrations.local_docs import backfill_local_docs

    path = source.get("config", {}).get("path", "./docs")
    result = await backfill_local_docs(org_id=org_id, docs_path=path)
    if result.get("status") == "error":
        raise ValueError(result.get("error", "Local documents sync failed"))
    return result


async def run_extraction(source_item, auto_confirm: bool = False) -> dict:
    """Run the narrow MVP extraction pipeline on a source item."""
    from pipelines.extract import extract_from_source

    result = await extract_from_source(source_item)
    if not result.get("success"):
        raise RuntimeError(result.get("error") or "Extraction pipeline failed")

    entity_ids = result.get("entity_ids", [])
    if auto_confirm and entity_ids:
        await GraphClient.run_query(
            """
            MATCH (e:Entity {org_id: $org_id})
            WHERE e.id IN $entity_ids AND e.status = 'proposed'
            SET e.status = 'confirmed',
                e.confirmed_at = datetime(),
                e.updated_at = datetime()
            """,
            {"org_id": source_item.org_id, "entity_ids": entity_ids},
        )

    return {
        "entities_created": result.get("entities_created", 0),
        "relationships_created": result.get("relationships_created", 0),
        "entity_ids": entity_ids,
    }


UPLOAD_EXTENSIONS = {".md", ".markdown", ".txt", ".yaml", ".yml"}
MAX_UPLOAD_FILES = 10
MAX_UPLOAD_BYTES = 1024 * 1024


@app.post("/sources/upload")
async def upload_documents(
    request: Request,
    org_id: str = Query(...),
    files: List[UploadFile] = File(...),
):
    """Extract uploaded text documents without persisting their raw contents."""
    await _authorized_org_user(request, org_id)
    if not files or len(files) > MAX_UPLOAD_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Upload between 1 and {MAX_UPLOAD_FILES} files at a time",
        )

    from core.models import SourceItem, SourceType
    from integrations.local_docs import extract_title_from_markdown

    settings = await get_org_settings(org_id)
    auto_confirm = settings.get("auto_confirm", False)
    results = []
    total_entities = 0

    for upload in files:
        filename = Path(upload.filename or "document.txt").name
        suffix = Path(filename).suffix.lower()
        if suffix not in UPLOAD_EXTENSIONS:
            results.append({
                "filename": filename,
                "status": "error",
                "error": "Supported formats: .md, .txt, .yaml, .yml",
            })
            continue

        content_bytes = await upload.read(MAX_UPLOAD_BYTES + 1)
        if len(content_bytes) > MAX_UPLOAD_BYTES:
            results.append({
                "filename": filename,
                "status": "error",
                "error": "File exceeds the 1 MB limit",
            })
            continue
        try:
            content = content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            results.append({
                "filename": filename,
                "status": "error",
                "error": "File must be UTF-8 encoded text",
            })
            continue
        if not content.strip():
            results.append({
                "filename": filename, "status": "error", "error": "File is empty"
            })
            continue

        digest = hashlib.sha256(content_bytes).hexdigest()
        source_item = SourceItem(
            org_id=org_id,
            source=SourceType.UPLOAD,
            kind={
                ".md": "markdown", ".markdown": "markdown",
                ".yaml": "yaml", ".yml": "yaml",
            }.get(suffix, "text"),
            title=extract_title_from_markdown(content, filename),
            body=content,
            url=f"upload://{filename}",
            reference=f"upload:{filename}:{digest[:12]}",
            source_date=datetime.utcnow(),
        )
        try:
            extraction = await run_extraction(source_item, auto_confirm=auto_confirm)
            created = extraction["entities_created"]
            total_entities += created
            results.append({
                "filename": filename,
                "status": "processed",
                "entities_created": created,
                "entity_ids": extraction["entity_ids"],
            })
        except Exception as error:
            results.append({
                "filename": filename,
                "status": "error",
                "error": str(error),
            })

    processed = sum(item["status"] == "processed" for item in results)
    if processed:
        source = await upsert_single_source_type(
            org_id=org_id,
            source_type="upload",
            name="Document Uploads",
            config={},
        )
        await update_connected_source(
            org_id,
            source["id"],
            last_sync=datetime.utcnow(),
            item_count=source.get("itemCount", 0) + processed,
        )

    return {
        "status": "complete" if processed == len(files) else "partial",
        "files_processed": processed,
        "entities_created": total_entities,
        "review_mode": not auto_confirm,
        "results": results,
    }


# =============================================================================
# Local Documents connector
# =============================================================================

@app.get("/connectors/local-docs/status")
async def local_docs_status():
    """Get local documents connector status."""
    from integrations.local_docs import get_local_docs_status
    return get_local_docs_status()


@app.post("/connectors/local-docs/scan")
async def local_docs_scan(
    org_id: str = Query("default-org"),
    path: Optional[str] = Query(None, description="Override docs path")
):
    """Trigger a scan of local documents."""
    from integrations.local_docs import backfill_local_docs
    result = await backfill_local_docs(org_id=org_id, docs_path=path)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


# =============================================================================
# Graph API endpoints
# =============================================================================

@app.get("/graph")
async def get_graph(
    org_id: str = Query("default-org"),
    limit: int = Query(200, description="Max nodes to return"),
    entity_types: Optional[str] = Query(None, description="Comma-separated entity types to filter")
):
    """
    Get the knowledge graph for visualization.

    Returns nodes (entities) and edges (relationships).
    """
    type_filter = ""
    if entity_types:
        types = [t.strip() for t in entity_types.split(",")]
        type_filter = f"AND e.entity_type IN {types}"

    # Get nodes
    nodes_query = f"""
    MATCH (e:Entity {{org_id: $org_id}})
    WHERE e.status IN ['proposed', 'confirmed']
    {type_filter}
    RETURN
        e.id as id,
        coalesce(e.name, e.statement) as name,
        e.entity_type as type,
        e.detail as description,
        e.status as status,
        e.confidence as confidence
    ORDER BY e.created_at DESC
    LIMIT $limit
    """

    nodes = await GraphClient.run_query(nodes_query, {
        "org_id": org_id,
        "limit": limit
    })

    # Get all node IDs for edge filtering
    node_ids = [n["id"] for n in nodes]

    if not node_ids:
        return {"nodes": [], "edges": []}

    # Get edges between these nodes
    edges_query = """
    MATCH (s:Entity {org_id: $org_id})-[r]->(t:Entity {org_id: $org_id})
    WHERE s.id IN $node_ids AND t.id IN $node_ids
    AND NOT type(r) = 'CITED_BY'
    RETURN
        s.id as source,
        t.id as target,
        type(r) as type,
        r.description as description
    """

    edges = await GraphClient.run_query(edges_query, {
        "org_id": org_id,
        "node_ids": node_ids
    })

    return {
        "nodes": nodes,
        "edges": edges
    }


@app.get("/graph/stats")
async def get_graph_stats(org_id: str = Query("default-org")):
    """Get statistics about the knowledge graph."""

    # Count nodes by type
    type_query = """
    MATCH (e:Entity {org_id: $org_id})
    WHERE e.status IN ['proposed', 'confirmed']
    RETURN e.entity_type as type, count(e) as count
    ORDER BY count DESC
    """

    type_counts = await GraphClient.run_query(type_query, {"org_id": org_id})

    # Count relationships by type
    rel_query = """
    MATCH (s:Entity {org_id: $org_id})-[r]->(t:Entity {org_id: $org_id})
    WHERE NOT type(r) = 'CITED_BY'
    RETURN type(r) as type, count(r) as count
    ORDER BY count DESC
    """

    rel_counts = await GraphClient.run_query(rel_query, {"org_id": org_id})

    # Total counts
    totals_query = """
    MATCH (e:Entity {org_id: $org_id})
    WHERE e.status IN ['proposed', 'confirmed']
    WITH count(e) as node_count
    MATCH (s:Entity {org_id: $org_id})-[r]->(t:Entity {org_id: $org_id})
    WHERE NOT type(r) = 'CITED_BY'
    RETURN node_count, count(r) as edge_count
    """

    totals = await GraphClient.run_query(totals_query, {"org_id": org_id})

    node_count = totals[0]["node_count"] if totals else 0
    edge_count = totals[0]["edge_count"] if totals else 0

    return {
        "total_nodes": node_count,
        "total_edges": edge_count,
        "nodes_by_type": {t["type"]: t["count"] for t in type_counts},
        "edges_by_type": {r["type"]: r["count"] for r in rel_counts}
    }


@app.get("/graph/neighbors/{entity_id}")
async def get_entity_neighbors(
    entity_id: str,
    org_id: str = Query("default-org"),
    depth: int = Query(1, description="How many hops to traverse")
):
    """Get the neighborhood of a specific entity."""

    # Get the entity and its neighbors up to N hops
    query = """
    MATCH path = (center:Entity {id: $entity_id, org_id: $org_id})-[*1..$depth]-(neighbor:Entity)
    WHERE neighbor.org_id = $org_id
    WITH center, neighbor, relationships(path) as rels
    UNWIND rels as r
    WITH center, neighbor, r, startNode(r) as source, endNode(r) as target
    WHERE NOT type(r) = 'CITED_BY'
    RETURN DISTINCT
        neighbor.id as id,
        neighbor.name as name,
        neighbor.entity_type as type,
        neighbor.detail as description,
        source.id as edge_source,
        target.id as edge_target,
        type(r) as edge_type
    """

    results = await GraphClient.run_query(query, {
        "entity_id": entity_id,
        "org_id": org_id,
        "depth": depth
    })

    # Build nodes and edges
    nodes = {}
    edges = []

    # Add center node
    center_query = """
    MATCH (e:Entity {id: $entity_id, org_id: $org_id})
    RETURN e.id as id, e.name as name, e.entity_type as type, e.detail as description
    """
    center = await GraphClient.run_query(center_query, {
        "entity_id": entity_id,
        "org_id": org_id
    })

    if center:
        nodes[entity_id] = {
            "id": center[0]["id"],
            "name": center[0]["name"],
            "type": center[0]["type"],
            "description": center[0]["description"],
            "isCenter": True
        }

    for row in results:
        # Add neighbor node
        if row["id"] not in nodes:
            nodes[row["id"]] = {
                "id": row["id"],
                "name": row["name"],
                "type": row["type"],
                "description": row["description"],
                "isCenter": False
            }

        # Add edge
        edge = {
            "source": row["edge_source"],
            "target": row["edge_target"],
            "type": row["edge_type"]
        }
        if edge not in edges:
            edges.append(edge)

    return {
        "center": entity_id,
        "nodes": list(nodes.values()),
        "edges": edges
    }


# =============================================================================
# Chat API endpoint
# =============================================================================

from sse_starlette.sse import EventSourceResponse
import json
from core.llm import get_llm
from core.embeddings import embed
from core.queries import BrainQueries


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str
    sources: Optional[List[Dict[str, Any]]] = None


class ChatRequest(BaseModel):
    message: str
    org_id: str = "default-org"
    conversation_history: List[ChatMessage] = Field(default_factory=list)
    stream: bool = True


class ChatResponse(BaseModel):
    response: str
    sources: List[Dict[str, Any]]
    conversation_id: Optional[str] = None


_CHAT_STOP_WORDS = {
    "about", "all", "and", "are", "been", "der", "die", "das", "do",
    "does", "for", "from", "haben", "has", "ist", "it", "me", "our",
    "show", "the", "und", "use", "was", "what", "welche", "which",
    "who", "wie", "wir", "with",
}


def _chat_search_terms(message: str) -> List[str]:
    """Extract useful literal fallback terms from a natural-language question."""
    import re

    words = re.findall(r"[\w-]+", message.casefold(), flags=re.UNICODE)
    return list(dict.fromkeys(
        word for word in words if len(word) >= 3 and word not in _CHAT_STOP_WORDS
    ))[:12]


async def _literal_chat_search(org_id: str, message: str, k: int = 8) -> List[dict]:
    """Search confirmed entities without relying on vector/full-text indexes."""
    terms = _chat_search_terms(message)
    if not terms:
        return []

    return await GraphClient.run_query(
        """
        MATCH (n:Entity {org_id: $org_id, status: 'confirmed'})
        WHERE any(term IN $terms WHERE
            toLower(coalesce(n.statement, '')) CONTAINS term OR
            toLower(coalesce(n.detail, '')) CONTAINS term OR
            toLower(coalesce(n.name, '')) CONTAINS term)
        WITH n, size([term IN $terms WHERE
            toLower(coalesce(n.statement, '')) CONTAINS term OR
            toLower(coalesce(n.detail, '')) CONTAINS term OR
            toLower(coalesce(n.name, '')) CONTAINS term]) AS matches
        RETURN n.id AS id, n.entity_type AS entity_type,
               n.statement AS statement, n.detail AS detail,
               n.status AS status, n.confidence AS confidence,
               toFloat(matches) AS score
        ORDER BY matches DESC, n.confirmed_at DESC
        LIMIT $k
        """,
        {"org_id": org_id, "terms": terms, "k": k},
    )


async def _attach_chat_evidence(org_id: str, entities: List[dict]) -> None:
    """Attach provenance owned by the same organization to selected entities."""
    if not entities:
        return

    rows = await GraphClient.run_query(
        """
        MATCH (entity:Entity {org_id: $org_id, status: 'confirmed'})
        WHERE entity.id IN $entity_ids
        OPTIONAL MATCH (entity)-[:CITED_BY]->(evidence:Evidence {org_id: $org_id})
        RETURN entity.id AS entity_id,
               collect(DISTINCT evidence{.id, .source, .reference, .url,
                                         .excerpt, .source_date}) AS evidence
        """,
        {"org_id": org_id, "entity_ids": [entity["id"] for entity in entities]},
    )
    evidence_by_entity = {
        row["entity_id"]: [item for item in row["evidence"] if item.get("id")]
        for row in rows
    }
    for entity in entities:
        entity["evidence"] = evidence_by_entity.get(entity["id"], [])


def _chat_context_and_sources(search_results: List[dict]) -> tuple[str, List[dict]]:
    """Build grounded model context and flattened UI citations."""
    if not search_results:
        return "No relevant confirmed information was found in the knowledge graph.", []

    sources: List[dict] = []
    context_parts = []
    for result in search_results:
        citation_numbers = []
        evidence_lines = []
        for evidence in result.get("evidence", []):
            source_date = evidence.get("source_date")
            source_date = str(source_date) if source_date is not None else None
            sources.append({
                "id": evidence["id"],
                "entity_id": result["id"],
                "type": result["entity_type"],
                "statement": result["statement"],
                "source": evidence.get("source") or "unknown",
                "reference": evidence.get("reference") or "Unknown reference",
                "url": evidence.get("url"),
                "excerpt": evidence.get("excerpt"),
                "source_date": source_date,
            })
            citation_numbers.append(str(len(sources)))
            evidence_lines.append(
                f"Source [{len(sources)}]: {sources[-1]['source']} — "
                f"{sources[-1]['reference']}"
            )

        citations = " ".join(f"[{number}]" for number in citation_numbers)
        context_parts.append(
            f"[{result['entity_type']}] {result['statement']} {citations}\n"
            f"Detail: {result.get('detail') or 'N/A'}\n"
            + "\n".join(evidence_lines)
        )
    return "\n\n".join(context_parts), sources


def _mock_chat_answer(search_results: List[dict], sources: List[dict]) -> str:
    """Return a useful grounded answer while no external model is configured."""
    if not search_results:
        return (
            "I couldn't find relevant confirmed information in the company brain yet. "
            "Add or confirm a source first, then ask again."
        )

    citation_by_entity: Dict[str, List[int]] = {}
    for index, source in enumerate(sources, 1):
        citation_by_entity.setdefault(source["entity_id"], []).append(index)

    lines = ["Based on the confirmed company brain:"]
    for result in search_results:
        citations = " ".join(
            f"[{index}]" for index in citation_by_entity.get(result["id"], [])
        )
        lines.append(
            f"- [{result['entity_type']}] {result['statement']}"
            + (f" {citations}" if citations else "")
        )
    return "\n".join(lines)


@app.post("/chat")
async def chat_with_brain(request: ChatRequest):
    """
    Chat interface for querying the knowledge graph.
    Uses RAG: embed query → hybrid search → LLM synthesis.
    """
    from fastapi import HTTPException

    try:
        mock_mode = os.getenv("KOMPONIST_AI_MODE", "mock").lower() == "mock"

        # 1. Try to embed user query for semantic search
        query_embedding = None
        if not mock_mode:
            try:
                query_embedding = await embed(request.message)
            except Exception as e:
                print(f"Embedding failed: {e}")

        # 2. Search the confirmed graph, with an index-independent literal fallback.
        search_results = []
        if not mock_mode:
            try:
                search_results = await BrainQueries.hybrid_search(
                    org_id=request.org_id,
                    query_text=request.message,
                    query_embedding=query_embedding,
                    k=8,  # Top 8 results
                    status="confirmed"
                )
            except Exception as search_error:
                print(f"Hybrid search failed: {search_error}")

        try:
            literal_results = await _literal_chat_search(
                request.org_id, request.message, k=8
            )
            merged = {result["id"]: result for result in literal_results}
            for result in search_results:
                merged.setdefault(result["id"], result)
            search_results = list(merged.values())[:8]
        except Exception as fallback_error:
            print(f"Literal fallback search failed: {fallback_error}")

        await _attach_chat_evidence(request.org_id, search_results)

        # 3. Build context from results
        context, sources = _chat_context_and_sources(search_results)

        # 4. Build conversation context
        conversation_context = ""
        if request.conversation_history:
            history_parts = []
            for msg in request.conversation_history[-3:]:  # Last 3 turns
                history_parts.append(f"{msg.role}: {msg.content}")
            conversation_context = "\n".join(history_parts) + "\n\n"

        # 5. Call LLM with RAG context
        system_prompt = """You are Komponist, an AI assistant that helps users query their company's knowledge graph.

You have access to confirmed facts, decisions, goals, and relationships from the knowledge graph.

When answering:
- Base your answers on the provided context from the knowledge graph
- Cite claims with the numbered evidence markers included in the context, such as [1]
- Never invent a citation or use information from proposed/rejected entities
- If the context is empty or doesn't contain the answer, explain that the knowledge graph is empty or doesn't have that information yet
- Suggest that the user should add sources to populate the knowledge graph (via the Onboard page)
- Be concise but complete
- Use the user's language and tone

Context from knowledge graph:
{context}"""

        user_prompt = f"{conversation_context}User question: {request.message}"

        answer = _mock_chat_answer(search_results, sources) if mock_mode else None
        llm = None if mock_mode else get_llm()

        if request.stream:
            # Streaming response
            async def generate_stream():
                try:
                    if answer is not None:
                        yield {
                            "event": "message",
                            "data": json.dumps({"content": answer})
                        }
                    else:
                        async for chunk in llm.stream(
                            prompt=user_prompt,
                            system=system_prompt.format(context=context),
                            max_tokens=2048,
                        ):
                            yield {
                                "event": "message",
                                "data": json.dumps({"content": chunk})
                            }
                    # Send sources at the end
                    yield {
                        "event": "sources",
                        "data": json.dumps({"sources": sources})
                    }
                    yield {"event": "done", "data": ""}
                except Exception as e:
                    yield {
                        "event": "error",
                        "data": json.dumps({"error": str(e)})
                    }

            return EventSourceResponse(generate_stream())
        else:
            # Non-streaming response
            if answer is None:
                response = await llm.call(
                    prompt=user_prompt,
                    system=system_prompt.format(context=context),
                    max_tokens=2048
                )
                answer = response["text"]

            return ChatResponse(
                response=answer,
                sources=sources,
                conversation_id=None  # Can add conversation persistence later
            )

    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Settings API endpoints
# =============================================================================

@app.get("/settings")
async def get_settings(org_id: str = Query("default-org")):
    """Get settings for an organization."""
    return await get_org_settings(org_id)


@app.put("/settings")
async def update_settings(
    payload: Optional[OrgSettingsUpdate] = None,
    org_id: str = Query("default-org"),
    auto_confirm: Optional[bool] = Query(None, description="Auto-confirm extracted entities"),
    parallel_batch_size: Optional[int] = Query(None, description="Parallel processing batch size")
):
    """Update settings for an organization."""
    resolved_auto_confirm = payload.auto_confirm if payload else auto_confirm
    resolved_batch_size = payload.parallel_batch_size if payload else parallel_batch_size
    current = await get_org_settings(org_id)
    saved = await save_org_settings(
        org_id=org_id,
        auto_confirm=(
            resolved_auto_confirm
            if resolved_auto_confirm is not None
            else current["auto_confirm"]
        ),
        parallel_batch_size=(
            max(1, min(10, resolved_batch_size))
            if resolved_batch_size is not None
            else current["parallel_batch_size"]
        ),
    )
    return {**current, **saved}


@app.get("/settings/ai")
async def get_ai_settings(
    request: Request, org_id: str = Query(...)
):
    """Return only non-secret status for the centrally managed provider."""
    await _authorized_org_user(request, org_id)
    mode = os.getenv("KOMPONIST_AI_MODE", "mock").lower()
    return {
        "mode": mode,
        "provider": "openai" if mode == "live" else "mock",
        "model": os.getenv("KOMPONIST_LLM_MODEL", "gpt-5.6-luna"),
        "embedding_model": "text-embedding-3-small",
        "configured": bool(os.getenv("OPENAI_API_KEY")) if mode == "live" else True,
        "managed_by": "komponist",
    }


@app.post("/settings/ai/test")
async def test_ai_settings(request: Request, org_id: str = Query(...)):
    """Test the server-managed provider without exposing its API key."""
    await _authorized_org_user(request, org_id, manage=True)
    try:
        if os.getenv("KOMPONIST_AI_MODE", "mock").lower() == "mock":
            return {"status": "ok", "mode": "mock", "message": "Mock mode is ready"}
        from core.embeddings import get_embedder
        from core.llm import get_llm

        llm_client = get_llm()
        embedding_client = get_embedder()
        response = await llm_client.call(
            "Reply with exactly OK.", max_tokens=16, temperature=0, max_retries=1
        )
        vector = await embedding_client.embed("Komponist connection test")
        return {
            "status": "ok",
            "mode": "live",
            "model": response["model"],
            "embedding_dimensions": len(vector),
            "message": "OpenAI generation and embeddings are ready",
        }
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/auth/organizations/{org_id}/api-keys")
async def get_organization_api_keys(org_id: str, request: Request):
    await _authorized_org_user(request, org_id, manage=True)
    return {"keys": await list_api_keys(org_id)}


@app.post("/auth/organizations/{org_id}/api-keys", status_code=201)
async def add_organization_api_key(
    org_id: str, payload: ApiKeyCreateRequest, request: Request
):
    user = await _authorized_org_user(request, org_id, manage=True)
    return await create_api_key(org_id, payload.name.strip(), user["id"])


@app.delete("/auth/organizations/{org_id}/api-keys/{key_id}", status_code=204)
async def delete_organization_api_key(
    org_id: str, key_id: str, request: Request
):
    await _authorized_org_user(request, org_id, manage=True)
    if not await revoke_api_key(org_id, key_id):
        raise HTTPException(status_code=404, detail="API key not found")


@app.get("/v1/context")
async def api_context_search(request: Request, query: str = Query(..., min_length=1)):
    """Small API-key-authenticated context endpoint for external agents."""
    authorization = request.headers.get("authorization", "")
    raw_key = authorization[7:].strip() if authorization.startswith("Bearer ") else ""
    org_id = await authenticate_api_key(raw_key)
    if not org_id:
        raise HTTPException(status_code=401, detail="Valid Bearer API key required")
    terms = [word.casefold() for word in query.split() if len(word) >= 3][:12]
    rows = await GraphClient.run_query(
        """
        MATCH (e:Entity {org_id: $org_id, status: 'confirmed'})
        WHERE any(term IN $terms WHERE toLower(e.statement) CONTAINS term OR
              toLower(coalesce(e.detail, '')) CONTAINS term)
        RETURN e.id AS id, e.entity_type AS type, e.statement AS statement,
               e.detail AS detail
        LIMIT 20
        """,
        {"org_id": org_id, "terms": terms},
    )
    return {"items": rows, "total": len(rows)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
