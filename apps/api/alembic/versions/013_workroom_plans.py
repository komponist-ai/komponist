"""Add versioned Workroom plans and richer task management.

Only additive: existing tasks keep their rows and gain nullable columns with
safe defaults. A task with no client_key is treated as hand-made and is never
archived by a plan approval, which is exactly how pre-existing tasks behave.

Revision ID: 013
Revises: 012
Create Date: 2026-07-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workroom_plan_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workroom_id", sa.String(36), nullable=False),
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("spec", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("provider", sa.String(40), nullable=True),
        sa.Column("model", sa.String(80), nullable=True),
        sa.Column("usage", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_by_user_id", sa.String(36), nullable=False),
        sa.Column("approved_by_user_id", sa.String(36), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_unique_constraint(
        "uq_workroom_plan_room_version",
        "workroom_plan_versions",
        ["workroom_id", "version"],
    )
    op.create_index(
        "ix_workroom_plan_versions_workroom_id",
        "workroom_plan_versions",
        ["workroom_id"],
    )
    op.create_index(
        "ix_workroom_plan_versions_org_id", "workroom_plan_versions", ["org_id"]
    )
    op.create_index(
        "ix_workroom_plan_versions_status", "workroom_plan_versions", ["status"]
    )

    op.add_column(
        "workroom_tasks", sa.Column("assignee_user_id", sa.String(36), nullable=True)
    )
    op.add_column(
        "workroom_tasks", sa.Column("client_key", sa.String(60), nullable=True)
    )
    op.add_column(
        "workroom_tasks", sa.Column("plan_version_id", sa.String(36), nullable=True)
    )
    op.add_column(
        "workroom_tasks",
        sa.Column("depends_on", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "workroom_tasks",
        sa.Column(
            "requires_approval",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "workroom_tasks", sa.Column("archived_at", sa.DateTime(), nullable=True)
    )
    op.create_index(
        "ix_workroom_tasks_assignee_user_id", "workroom_tasks", ["assignee_user_id"]
    )
    op.create_index("ix_workroom_tasks_client_key", "workroom_tasks", ["client_key"])
    op.create_index(
        "ix_workroom_tasks_plan_version_id", "workroom_tasks", ["plan_version_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_workroom_tasks_plan_version_id", table_name="workroom_tasks")
    op.drop_index("ix_workroom_tasks_client_key", table_name="workroom_tasks")
    op.drop_index("ix_workroom_tasks_assignee_user_id", table_name="workroom_tasks")
    for column in (
        "archived_at",
        "requires_approval",
        "depends_on",
        "plan_version_id",
        "client_key",
        "assignee_user_id",
    ):
        op.drop_column("workroom_tasks", column)
    op.drop_table("workroom_plan_versions")
