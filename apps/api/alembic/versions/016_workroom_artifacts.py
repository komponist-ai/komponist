"""Link generated deliverables to the Workroom that produced them.

Additive only, and deliberately so: sharing is expressed by the presence of a
link row. Existing artifacts have no link, so they stay private to their
creator and are never retroactively exposed to a room.

Revision ID: 016
Revises: 015
Create Date: 2026-07-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workroom_artifacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workroom_id", sa.String(36), nullable=False),
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("artifact_id", sa.String(36), nullable=False),
        sa.Column("task_id", sa.String(36), nullable=True),
        sa.Column("run_id", sa.String(36), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="shared"),
        sa.Column("created_by_user_id", sa.String(36), nullable=False),
        sa.Column("approved_by_user_id", sa.String(36), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_unique_constraint(
        "uq_workroom_artifact", "workroom_artifacts", ["workroom_id", "artifact_id"]
    )
    op.create_index(
        "ix_workroom_artifacts_workroom_id", "workroom_artifacts", ["workroom_id"]
    )
    op.create_index("ix_workroom_artifacts_org_id", "workroom_artifacts", ["org_id"])
    op.create_index(
        "ix_workroom_artifacts_artifact_id", "workroom_artifacts", ["artifact_id"]
    )
    op.create_index("ix_workroom_artifacts_status", "workroom_artifacts", ["status"])


def downgrade() -> None:
    op.drop_table("workroom_artifacts")
