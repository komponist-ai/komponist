"""
Database models and connection.
"""

import os
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, String, DateTime, Integer, Text, Boolean, text, UniqueConstraint
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


# Database URL
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://komponist:devpassword@localhost:5432/komponist"
)

# Engine
engine = create_async_engine(DATABASE_URL, echo=False, pool_size=20, max_overflow=10)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


class Org(Base):
    """Organization."""
    __tablename__ = "orgs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class User(Base):
    """User."""
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(36), index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AuthIdentity(Base):
    """External login identity linked to a Komponist user."""
    __tablename__ = "auth_identities"
    __table_args__ = (
        UniqueConstraint("provider", "subject", name="uq_auth_identity_provider_subject"),
        UniqueConstraint("provider", "user_id", name="uq_auth_identity_provider_user"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    provider: Mapped[str] = mapped_column(String(30), index=True)
    subject: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255))
    avatar_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class PasswordCredential(Base):
    """First-party password credential linked one-to-one with a user."""
    __tablename__ = "password_credentials"

    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    password_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class AuthSession(Base):
    """Revocable browser session. Only a hash of the bearer token is stored."""
    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class OAuthLoginState(Base):
    """Single-use state for the user-login OAuth flow."""
    __tablename__ = "oauth_login_states"

    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    return_to: Mapped[str] = mapped_column(String(500), default="/")
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class OrganizationMembership(Base):
    """A user's role in an organization."""
    __tablename__ = "organization_memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "org_id", name="uq_membership_user_org"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    org_id: Mapped[str] = mapped_column(String(36), index=True)
    role: Mapped[str] = mapped_column(String(20), default="member")
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class Department(Base):
    """A named access boundary inside an organization."""
    __tablename__ = "departments"
    __table_args__ = (
        UniqueConstraint("org_id", "name", name="uq_department_org_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    color: Mapped[str] = mapped_column(String(20), default="orange")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class DepartmentMembership(Base):
    """Assign an organization member to one department."""
    __tablename__ = "department_memberships"
    __table_args__ = (
        UniqueConstraint(
            "department_id", "user_id", name="uq_department_membership_department_user"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(36), index=True)
    department_id: Mapped[str] = mapped_column(String(36), index=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AuthSessionContext(Base):
    """Organization selected for a browser session."""
    __tablename__ = "auth_session_contexts"

    session_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    active_org_id: Mapped[str] = mapped_column(String(36), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class OrganizationInvitation(Base):
    """Single-use invitation to join an organization."""
    __tablename__ = "organization_invitations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(36), index=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    role: Mapped[str] = mapped_column(String(20), default="member")
    department_ids: Mapped[list] = mapped_column(JSON, default=list)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    invited_by_user_id: Mapped[str] = mapped_column(String(36))
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    accepted_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class EventRaw(Base):
    """Raw webhook events landing zone."""
    __tablename__ = "events_raw"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(String(36), index=True)
    source: Mapped[str] = mapped_column(String(50), index=True)  # github, slack, linear
    event_type: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict] = mapped_column(JSON)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class ToolCall(Base):
    """MCP tool call logs (metrics)."""
    __tablename__ = "tool_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(String(36), index=True)
    tool: Mapped[str] = mapped_column(String(100), index=True)
    input: Mapped[dict] = mapped_column(JSON)
    output: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    verdict: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)  # for check_constraint
    agent_client: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class SyncState(Base):
    """Integration sync cursors."""
    __tablename__ = "sync_state"

    org_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source: Mapped[str] = mapped_column(String(50), primary_key=True)
    cursor: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class OrgSetting(Base):
    """Persistent organization-level application settings."""
    __tablename__ = "org_settings"

    org_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    auto_confirm: Mapped[bool] = mapped_column(Boolean, default=False)
    parallel_batch_size: Mapped[int] = mapped_column(Integer, default=5)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class OrganizationApiKey(Base):
    """Hashed API credential for one organization."""
    __tablename__ = "organization_api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(50), index=True)
    name: Mapped[str] = mapped_column(String(100))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    token_prefix: Mapped[str] = mapped_column(String(24))
    created_by_user_id: Mapped[str] = mapped_column(String(36))
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ConnectorOAuthState(Base):
    """Short-lived, single-use connector OAuth state."""
    __tablename__ = "connector_oauth_states"

    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(50), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    consumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ConnectedSource(Base):
    """Persistent connector metadata with encrypted private configuration."""
    __tablename__ = "connected_sources"
    __table_args__ = (
        UniqueConstraint("org_id", "id", name="uq_connected_sources_org_id_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(50), index=True)
    source_type: Mapped[str] = mapped_column(String(50), index=True)
    department_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(50), default="connected")
    last_sync: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    config_ciphertext: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class ApprovalRequest(Base):
    """Persistent human-approval request created by an MCP agent."""
    __tablename__ = "approval_requests"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(50), index=True)
    action: Mapped[str] = mapped_column(Text)
    constraint_id: Mapped[str] = mapped_column(String(64), index=True)
    constraint_statement: Mapped[str] = mapped_column(Text)
    context: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    slack_ts: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    resolved_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class ChatConversation(Base):
    """A private chat thread within an organization."""
    __tablename__ = "chat_conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(36), index=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    title: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True
    )


class ChatMessageRecord(Base):
    """One persisted turn and its evidence in a chat conversation."""
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(36), index=True)
    org_id: Mapped[str] = mapped_column(String(36), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    sources: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class GeneratedArtifact(Base):
    """A private, cited deliverable generated from visible company knowledge."""
    __tablename__ = "generated_artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(36), index=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    artifact_type: Mapped[str] = mapped_column(String(20), index=True)
    title: Mapped[str] = mapped_column(String(160))
    topic: Mapped[str] = mapped_column(String(500))
    audience: Mapped[str] = mapped_column(String(120))
    language: Mapped[str] = mapped_column(String(20), default="english")
    content: Mapped[dict] = mapped_column(JSON)
    sources: Mapped[list] = mapped_column(JSON, default=list)
    source_entity_ids: Mapped[list] = mapped_column(JSON, default=list)
    department_ids: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True
    )


class Workroom(Base):
    """A shared, permission-scoped workspace for people and agents."""
    __tablename__ = "workrooms"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(36), index=True)
    title: Mapped[str] = mapped_column(String(160))
    objective: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    # "organization" | "departments" | "private". Controls who may see the
    # room at all; room roles control what they may do once inside.
    visibility: Mapped[str] = mapped_column(
        String(20), default="organization", index=True
    )
    department_ids: Mapped[list] = mapped_column(JSON, default=list)
    created_by_user_id: Mapped[str] = mapped_column(String(36), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True
    )


class WorkroomMember(Base):
    """One person's explicit role in a Workroom.

    Room membership is deliberately separate from organization membership and
    from department access: joining a room never widens what knowledge a user
    or the agent can read.
    """
    __tablename__ = "workroom_members"
    __table_args__ = (
        UniqueConstraint(
            "workroom_id", "user_id", name="uq_workroom_member_room_user"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workroom_id: Mapped[str] = mapped_column(String(36), index=True)
    org_id: Mapped[str] = mapped_column(String(36), index=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    # "owner" | "editor" | "approver" | "viewer"
    room_role: Mapped[str] = mapped_column(String(20), default="viewer")
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    invited_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class WorkroomTask(Base):
    """One shared unit of work inside a Workroom."""
    __tablename__ = "workroom_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workroom_id: Mapped[str] = mapped_column(String(36), index=True)
    org_id: Mapped[str] = mapped_column(String(36), index=True)
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="todo", index=True)
    assignee_type: Mapped[str] = mapped_column(String(20), default="agent")
    assignee_name: Mapped[str] = mapped_column(String(120), default="Komponist Analyst")
    # Set when a specific person owns the task; agent tasks leave it null.
    assignee_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True, index=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0)
    # Stable key from the generated plan. Hand-made tasks have none, which is
    # what keeps a plan approval from archiving them.
    client_key: Mapped[Optional[str]] = mapped_column(
        String(60), nullable=True, index=True
    )
    plan_version_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True, index=True
    )
    depends_on: Mapped[list] = mapped_column(JSON, default=list)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    artifact_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    created_by_user_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class WorkroomMessage(Base):
    """One intentional message in a Workroom's shared conversation.

    Deliberately distinct from WorkroomEvent: messages are what people and
    agents choose to say, events are the immutable audit trail of what
    happened. A message never commands the agent on its own — redirecting a
    run is a separate, explicit action.
    """
    __tablename__ = "workroom_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workroom_id: Mapped[str] = mapped_column(String(36), index=True)
    org_id: Mapped[str] = mapped_column(String(36), index=True)
    author_type: Mapped[str] = mapped_column(String(20), default="human")
    author_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True, index=True
    )
    author_name: Mapped[str] = mapped_column(String(120), default="Team member")
    body: Mapped[str] = mapped_column(Text)
    reply_to_message_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True, index=True
    )
    # Durable pointers to a task, run, source, or artifact this message is about.
    references: Mapped[list] = mapped_column(JSON, default=list)
    mentions: Mapped[list] = mapped_column(JSON, default=list)
    edited_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True
    )


class WorkroomContextItem(Base):
    """One explicit inclusion or exclusion in a Workroom's context pack.

    These only ever narrow or prioritise within what the room may already
    read. A pin can never reach knowledge outside the room's permission scope.
    """
    __tablename__ = "workroom_context_items"
    __table_args__ = (
        UniqueConstraint(
            "workroom_id",
            "item_kind",
            "reference_id",
            name="uq_workroom_context_item",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workroom_id: Mapped[str] = mapped_column(String(36), index=True)
    org_id: Mapped[str] = mapped_column(String(36), index=True)
    # "source" (an Evidence passage) or "entity" (a confirmed fact)
    item_kind: Mapped[str] = mapped_column(String(20), index=True)
    reference_id: Mapped[str] = mapped_column(String(120), index=True)
    # "include" pins the item; "exclude" removes it from every run
    mode: Mapped[str] = mapped_column(String(20), default="include", index=True)
    label: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    added_by_user_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class WorkroomPlanVersion(Base):
    """One generated-or-edited plan draft and its approval state.

    Plans are versioned rather than overwritten so an approved plan and the
    tasks it produced remain explainable after later revisions.
    """
    __tablename__ = "workroom_plan_versions"
    __table_args__ = (
        UniqueConstraint(
            "workroom_id", "version", name="uq_workroom_plan_room_version"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workroom_id: Mapped[str] = mapped_column(String(36), index=True)
    org_id: Mapped[str] = mapped_column(String(36), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    # "draft" | "approved" | "superseded" | "rejected"
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    spec: Mapped[dict] = mapped_column(JSON, default=dict)
    # Operational metadata only. No model reasoning is requested or stored.
    provider: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    usage: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by_user_id: Mapped[str] = mapped_column(String(36))
    approved_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class WorkroomRun(Base):
    """A versioned agent attempt that can be paused, redirected, or approved."""
    __tablename__ = "workroom_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workroom_id: Mapped[str] = mapped_column(String(36), index=True)
    task_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    org_id: Mapped[str] = mapped_column(String(36), index=True)
    agent_name: Mapped[str] = mapped_column(String(120), default="Komponist Analyst")
    instruction: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    current_step: Mapped[str] = mapped_column(String(80), default="queued")
    context_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    redirected_from_run_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True
    )
    created_by_user_id: Mapped[str] = mapped_column(String(36))
    approved_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True
    )


class WorkroomEvent(Base):
    """Append-only, human-readable activity emitted by a Workroom."""
    __tablename__ = "workroom_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workroom_id: Mapped[str] = mapped_column(String(36), index=True)
    run_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    org_id: Mapped[str] = mapped_column(String(36), index=True)
    actor_type: Mapped[str] = mapped_column(String(20))
    actor_name: Mapped[str] = mapped_column(String(120))
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    message: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class WorkroomJob(Base):
    """A durable unit of agent work owned by Postgres, not by a process.

    Jobs outlive API and worker restarts. A worker claims one with
    ``FOR UPDATE SKIP LOCKED``, holds a time-boxed lease it must renew, and
    an expired lease returns the job to the queue for another attempt.
    """
    __tablename__ = "workroom_jobs"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_workroom_jobs_idempotency_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(36), index=True)
    workroom_id: Mapped[str] = mapped_column(String(36), index=True)
    run_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    job_type: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    idempotency_key: Mapped[str] = mapped_column(String(200))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    available_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True
    )
    lease_owner: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, index=True
    )
    last_heartbeat_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    error_code: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class WorkroomWorker(Base):
    """Liveness record for one Workroom worker process."""
    __tablename__ = "workroom_workers"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    hostname: Mapped[str] = mapped_column(String(200), default="")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True
    )
    claimed_total: Mapped[int] = mapped_column(Integer, default=0)


async def get_db() -> AsyncSession:
    """Dependency for getting database session."""
    async with async_session() as session:
        yield session


async def init_db():
    """Initialize database (create tables)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Existing self-hosted MVP installs historically used create_all without
        # running Alembic. Keep this additive upgrade idempotent so those databases
        # receive the department columns as well; migration 008 remains the source
        # of truth for managed deployments.
        await conn.execute(text(
            "ALTER TABLE organization_invitations "
            "ADD COLUMN IF NOT EXISTS department_ids JSON NOT NULL DEFAULT '[]'"
        ))
        await conn.execute(text(
            "ALTER TABLE connected_sources "
            "ADD COLUMN IF NOT EXISTS department_id VARCHAR(36)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_connected_sources_department_id "
            "ON connected_sources (department_id)"
        ))
        await conn.execute(text(
            "ALTER TABLE workrooms ADD COLUMN IF NOT EXISTS visibility "
            "VARCHAR(20) NOT NULL DEFAULT 'organization'"
        ))
        for column, definition in (
            ("assignee_user_id", "VARCHAR(36)"),
            ("client_key", "VARCHAR(60)"),
            ("plan_version_id", "VARCHAR(36)"),
            ("depends_on", "JSON NOT NULL DEFAULT '[]'"),
            ("requires_approval", "BOOLEAN NOT NULL DEFAULT FALSE"),
            ("archived_at", "TIMESTAMP"),
        ):
            await conn.execute(text(
                f"ALTER TABLE workroom_tasks ADD COLUMN IF NOT EXISTS "
                f"{column} {definition}"
            ))
        # Rooms created before room roles existed keep working: their creator
        # is backfilled as owner. Migration 012 is the source of truth for
        # managed deployments; this keeps create_all installs consistent.
        await conn.execute(text(
            """
            INSERT INTO workroom_members (
                id, workroom_id, org_id, user_id, room_role, status,
                invited_by_user_id, created_at, updated_at
            )
            SELECT
                md5(room.id || ':' || room.created_by_user_id),
                room.id, room.org_id, room.created_by_user_id,
                'owner', 'active', NULL, room.created_at, room.updated_at
            FROM workrooms room
            WHERE NOT EXISTS (
                SELECT 1 FROM workroom_members member
                WHERE member.workroom_id = room.id
                  AND member.user_id = room.created_by_user_id
            )
            """
        ))


async def health_check_db() -> dict:
    """Check database connection health."""
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
            return {"status": "healthy", "url": DATABASE_URL.split("@")[1] if "@" in DATABASE_URL else "hidden"}
    except Exception as e:
        return {"status": "error", "error": str(e)}
