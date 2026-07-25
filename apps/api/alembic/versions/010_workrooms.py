"""Add shared Workrooms, tasks, versioned agent runs, and activity events.

Revision ID: 010
Revises: 009
Create Date: 2026-07-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workrooms",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("department_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_by_user_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_workrooms_org_id", "workrooms", ["org_id"])
    op.create_index("ix_workrooms_status", "workrooms", ["status"])
    op.create_index(
        "ix_workrooms_created_by_user_id", "workrooms", ["created_by_user_id"]
    )
    op.create_index("ix_workrooms_updated_at", "workrooms", ["updated_at"])

    op.create_table(
        "workroom_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workroom_id", sa.String(36), nullable=False),
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(24), nullable=False, server_default="todo"),
        sa.Column("assignee_type", sa.String(20), nullable=False, server_default="agent"),
        sa.Column(
            "assignee_name",
            sa.String(120),
            nullable=False,
            server_default="Komponist Analyst",
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("artifact_id", sa.String(36), nullable=True),
        sa.Column("created_by_user_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_workroom_tasks_workroom_id", "workroom_tasks", ["workroom_id"])
    op.create_index("ix_workroom_tasks_org_id", "workroom_tasks", ["org_id"])
    op.create_index("ix_workroom_tasks_status", "workroom_tasks", ["status"])

    op.create_table(
        "workroom_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workroom_id", sa.String(36), nullable=False),
        sa.Column("task_id", sa.String(36), nullable=True),
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column(
            "agent_name",
            sa.String(120),
            nullable=False,
            server_default="Komponist Analyst",
        ),
        sa.Column("instruction", sa.Text(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("current_step", sa.String(80), nullable=False, server_default="queued"),
        sa.Column("context_snapshot", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("result", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("redirected_from_run_id", sa.String(36), nullable=True),
        sa.Column("created_by_user_id", sa.String(36), nullable=False),
        sa.Column("approved_by_user_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_workroom_runs_workroom_id", "workroom_runs", ["workroom_id"])
    op.create_index("ix_workroom_runs_task_id", "workroom_runs", ["task_id"])
    op.create_index("ix_workroom_runs_org_id", "workroom_runs", ["org_id"])
    op.create_index("ix_workroom_runs_status", "workroom_runs", ["status"])
    op.create_index("ix_workroom_runs_updated_at", "workroom_runs", ["updated_at"])

    op.create_table(
        "workroom_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("workroom_id", sa.String(36), nullable=False),
        sa.Column("run_id", sa.String(36), nullable=True),
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("actor_type", sa.String(20), nullable=False),
        sa.Column("actor_name", sa.String(120), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_workroom_events_workroom_id", "workroom_events", ["workroom_id"])
    op.create_index("ix_workroom_events_run_id", "workroom_events", ["run_id"])
    op.create_index("ix_workroom_events_org_id", "workroom_events", ["org_id"])
    op.create_index("ix_workroom_events_event_type", "workroom_events", ["event_type"])
    op.create_index("ix_workroom_events_created_at", "workroom_events", ["created_at"])


def downgrade() -> None:
    op.drop_table("workroom_events")
    op.drop_table("workroom_runs")
    op.drop_table("workroom_tasks")
    op.drop_table("workrooms")
