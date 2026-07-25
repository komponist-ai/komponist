"""Add the shared Workroom conversation.

Additive only. Existing rooms simply start with an empty conversation; the
activity trail in workroom_events is untouched and keeps its own meaning.

Revision ID: 015
Revises: 014
Create Date: 2026-07-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workroom_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workroom_id", sa.String(36), nullable=False),
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("author_type", sa.String(20), nullable=False, server_default="human"),
        sa.Column("author_user_id", sa.String(36), nullable=True),
        sa.Column(
            "author_name", sa.String(120), nullable=False, server_default="Team member"
        ),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("reply_to_message_id", sa.String(36), nullable=True),
        sa.Column("references", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("mentions", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("edited_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_workroom_messages_workroom_id", "workroom_messages", ["workroom_id"]
    )
    op.create_index("ix_workroom_messages_org_id", "workroom_messages", ["org_id"])
    op.create_index(
        "ix_workroom_messages_author_user_id", "workroom_messages", ["author_user_id"]
    )
    op.create_index(
        "ix_workroom_messages_reply_to_message_id",
        "workroom_messages",
        ["reply_to_message_id"],
    )
    op.create_index(
        "ix_workroom_messages_created_at", "workroom_messages", ["created_at"]
    )


def downgrade() -> None:
    op.drop_table("workroom_messages")
