"""Add multi-organization memberships and invitations.

Revision ID: 005
Revises: 004
Create Date: 2026-07-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "organization_memberships",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="member"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "org_id", name="uq_membership_user_org"),
    )
    op.create_index(
        "ix_organization_memberships_user_id", "organization_memberships", ["user_id"]
    )
    op.create_index(
        "ix_organization_memberships_org_id", "organization_memberships", ["org_id"]
    )
    op.create_index(
        "ix_organization_memberships_status", "organization_memberships", ["status"]
    )

    op.create_table(
        "auth_session_contexts",
        sa.Column("session_id", sa.String(36), primary_key=True),
        sa.Column("active_org_id", sa.String(36), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_auth_session_contexts_active_org_id",
        "auth_session_contexts",
        ["active_org_id"],
    )

    op.create_table(
        "organization_invitations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="member"),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("invited_by_user_id", sa.String(36), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(), nullable=True),
        sa.Column("accepted_by_user_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_organization_invitations_org_id", "organization_invitations", ["org_id"]
    )
    op.create_index(
        "ix_organization_invitations_email", "organization_invitations", ["email"]
    )
    op.create_index(
        "ix_organization_invitations_token_hash",
        "organization_invitations",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_organization_invitations_expires_at",
        "organization_invitations",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_organization_invitations_expires_at",
        table_name="organization_invitations",
    )
    op.drop_index(
        "ix_organization_invitations_token_hash",
        table_name="organization_invitations",
    )
    op.drop_index(
        "ix_organization_invitations_email", table_name="organization_invitations"
    )
    op.drop_index(
        "ix_organization_invitations_org_id", table_name="organization_invitations"
    )
    op.drop_table("organization_invitations")
    op.drop_index(
        "ix_auth_session_contexts_active_org_id", table_name="auth_session_contexts"
    )
    op.drop_table("auth_session_contexts")
    op.drop_index(
        "ix_organization_memberships_status", table_name="organization_memberships"
    )
    op.drop_index(
        "ix_organization_memberships_org_id", table_name="organization_memberships"
    )
    op.drop_index(
        "ix_organization_memberships_user_id", table_name="organization_memberships"
    )
    op.drop_table("organization_memberships")
