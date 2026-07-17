"""Persist private generated presentations, briefings, and summaries.

Revision ID: 009
Revises: 008
Create Date: 2026-07-17
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "generated_artifacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("artifact_type", sa.String(20), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("topic", sa.String(500), nullable=False),
        sa.Column("audience", sa.String(120), nullable=False),
        sa.Column("language", sa.String(20), nullable=False, server_default="english"),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("sources", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("source_entity_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("department_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_generated_artifacts_org_id", "generated_artifacts", ["org_id"])
    op.create_index("ix_generated_artifacts_user_id", "generated_artifacts", ["user_id"])
    op.create_index(
        "ix_generated_artifacts_artifact_type", "generated_artifacts", ["artifact_type"]
    )
    op.create_index(
        "ix_generated_artifacts_updated_at", "generated_artifacts", ["updated_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_generated_artifacts_updated_at", table_name="generated_artifacts")
    op.drop_index("ix_generated_artifacts_artifact_type", table_name="generated_artifacts")
    op.drop_index("ix_generated_artifacts_user_id", table_name="generated_artifacts")
    op.drop_index("ix_generated_artifacts_org_id", table_name="generated_artifacts")
    op.drop_table("generated_artifacts")
