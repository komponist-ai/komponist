"""Add saved Canvases and their immutable version history.

Additive only: two new tables, nothing existing is touched. A deployment
without any Canvas behaves exactly as before.

Revision ID: 017
Revises: 016
Create Date: 2026-07-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "canvases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "visibility", sa.String(20), nullable=False, server_default="private"
        ),
        sa.Column("department_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("current_version_id", sa.String(36), nullable=True),
        sa.Column("current_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_by_user_id", sa.String(36), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_canvases_org_id", "canvases", ["org_id"])
    op.create_index("ix_canvases_visibility", "canvases", ["visibility"])
    op.create_index("ix_canvases_status", "canvases", ["status"])
    op.create_index(
        "ix_canvases_created_by_user_id", "canvases", ["created_by_user_id"]
    )
    op.create_index("ix_canvases_updated_at", "canvases", ["updated_at"])

    op.create_table(
        "canvas_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("canvas_id", sa.String(36), nullable=False),
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("prompt", sa.Text(), nullable=False, server_default=""),
        sa.Column("origin", sa.String(20), nullable=False, server_default="generated"),
        sa.Column("spec", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("context_summary", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("provider", sa.String(40), nullable=True),
        sa.Column("model", sa.String(80), nullable=True),
        sa.Column("restored_from_version", sa.Integer(), nullable=True),
        sa.Column("created_by_user_id", sa.String(36), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_unique_constraint(
        "uq_canvas_version", "canvas_versions", ["canvas_id", "version"]
    )
    op.create_index("ix_canvas_versions_canvas_id", "canvas_versions", ["canvas_id"])
    op.create_index("ix_canvas_versions_org_id", "canvas_versions", ["org_id"])


def downgrade() -> None:
    op.drop_table("canvas_versions")
    op.drop_table("canvases")
