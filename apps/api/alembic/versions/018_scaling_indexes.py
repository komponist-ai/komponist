"""Add composite indexes for high-volume lists and message histories.

Revision ID: 018
Revises: 017
Create Date: 2026-07-26
"""

from typing import Sequence, Union

from alembic import op


revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


INDEXES = (
    (
        "ix_chat_conversations_org_user_updated",
        "chat_conversations",
        ["org_id", "user_id", "updated_at"],
    ),
    (
        "ix_chat_messages_conversation_created_id",
        "chat_messages",
        ["conversation_id", "created_at", "id"],
    ),
    (
        "ix_generated_artifacts_org_user_updated",
        "generated_artifacts",
        ["org_id", "user_id", "updated_at"],
    ),
    (
        "ix_workrooms_org_status_updated",
        "workrooms",
        ["org_id", "status", "updated_at"],
    ),
    (
        "ix_workroom_messages_room_created_id",
        "workroom_messages",
        ["workroom_id", "created_at", "id"],
    ),
)


def upgrade() -> None:
    for name, table, columns in INDEXES:
        op.create_index(name, table, columns)


def downgrade() -> None:
    for name, table, _ in reversed(INDEXES):
        op.drop_index(name, table_name=table)
