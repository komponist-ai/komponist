"""Add explicit Workroom membership, room roles, and room visibility.

Existing Workrooms are preserved: every room keeps its rows, gains the default
"organization" visibility it effectively already had, and its creator is
backfilled as the room owner so nobody loses access.

Revision ID: 012
Revises: 011
Create Date: 2026-07-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workroom_members",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workroom_id", sa.String(36), nullable=False),
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("room_role", sa.String(20), nullable=False, server_default="viewer"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("invited_by_user_id", sa.String(36), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_unique_constraint(
        "uq_workroom_member_room_user", "workroom_members", ["workroom_id", "user_id"]
    )
    op.create_index(
        "ix_workroom_members_workroom_id", "workroom_members", ["workroom_id"]
    )
    op.create_index("ix_workroom_members_org_id", "workroom_members", ["org_id"])
    op.create_index("ix_workroom_members_user_id", "workroom_members", ["user_id"])
    op.create_index("ix_workroom_members_status", "workroom_members", ["status"])

    op.add_column(
        "workrooms",
        sa.Column(
            "visibility",
            sa.String(20),
            nullable=False,
            server_default="organization",
        ),
    )
    op.create_index("ix_workrooms_visibility", "workrooms", ["visibility"])

    # Backfill: the person who created each room becomes its owner.
    op.execute(
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
    )


def downgrade() -> None:
    op.drop_index("ix_workrooms_visibility", table_name="workrooms")
    op.drop_column("workrooms", "visibility")
    op.drop_table("workroom_members")
