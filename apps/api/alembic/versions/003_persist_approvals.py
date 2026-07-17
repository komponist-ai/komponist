"""Persist MCP approval requests.

Revision ID: 003
Revises: 002
Create Date: 2026-07-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "approval_requests",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("org_id", sa.String(50), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("constraint_id", sa.String(64), nullable=False),
        sa.Column("constraint_statement", sa.Text(), nullable=False),
        sa.Column("context", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("slack_ts", sa.String(100), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("resolved_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_approval_requests_org_id", "approval_requests", ["org_id"])
    op.create_index(
        "ix_approval_requests_constraint_id", "approval_requests", ["constraint_id"]
    )
    op.create_index("ix_approval_requests_status", "approval_requests", ["status"])


def downgrade() -> None:
    op.drop_index("ix_approval_requests_status", table_name="approval_requests")
    op.drop_index("ix_approval_requests_constraint_id", table_name="approval_requests")
    op.drop_index("ix_approval_requests_org_id", table_name="approval_requests")
    op.drop_table("approval_requests")
