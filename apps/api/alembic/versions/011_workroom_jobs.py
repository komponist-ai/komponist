"""Add the durable Workroom job queue and worker liveness records.

Existing Workrooms, tasks, runs, and events are untouched: this revision only
adds tables. Runs that were in flight when this revision is applied keep their
row and can be re-enqueued by an operator.

Revision ID: 011
Revises: 010
Create Date: 2026-07-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workroom_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("workroom_id", sa.String(36), nullable=False),
        sa.Column("run_id", sa.String(36), nullable=True),
        sa.Column("job_type", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column(
            "available_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("lease_owner", sa.String(64), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(), nullable=True),
        sa.Column("error_code", sa.String(60), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )
    op.create_unique_constraint(
        "uq_workroom_jobs_idempotency_key", "workroom_jobs", ["idempotency_key"]
    )
    op.create_index("ix_workroom_jobs_org_id", "workroom_jobs", ["org_id"])
    op.create_index("ix_workroom_jobs_workroom_id", "workroom_jobs", ["workroom_id"])
    op.create_index("ix_workroom_jobs_run_id", "workroom_jobs", ["run_id"])
    op.create_index("ix_workroom_jobs_job_type", "workroom_jobs", ["job_type"])
    op.create_index("ix_workroom_jobs_status", "workroom_jobs", ["status"])
    op.create_index("ix_workroom_jobs_available_at", "workroom_jobs", ["available_at"])
    op.create_index(
        "ix_workroom_jobs_lease_expires_at", "workroom_jobs", ["lease_expires_at"]
    )
    op.create_index("ix_workroom_jobs_updated_at", "workroom_jobs", ["updated_at"])
    # The claim query orders ready work by availability within a status.
    op.create_index(
        "ix_workroom_jobs_claim", "workroom_jobs", ["status", "available_at"]
    )

    op.create_table(
        "workroom_workers",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("hostname", sa.String(200), nullable=False, server_default=""),
        sa.Column(
            "started_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "last_heartbeat_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("claimed_total", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_workroom_workers_last_heartbeat_at",
        "workroom_workers",
        ["last_heartbeat_at"],
    )


def downgrade() -> None:
    op.drop_table("workroom_workers")
    op.drop_table("workroom_jobs")
