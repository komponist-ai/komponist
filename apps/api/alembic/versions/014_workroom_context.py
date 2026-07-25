"""Add explicit Workroom context packs.

Additive only. A Workroom with no context items behaves exactly as before:
the agent sees everything inside the room's permission scope.

Revision ID: 014
Revises: 013
Create Date: 2026-07-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workroom_context_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workroom_id", sa.String(36), nullable=False),
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("item_kind", sa.String(20), nullable=False),
        sa.Column("reference_id", sa.String(120), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False, server_default="include"),
        sa.Column("label", sa.String(200), nullable=True),
        sa.Column("added_by_user_id", sa.String(36), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_unique_constraint(
        "uq_workroom_context_item",
        "workroom_context_items",
        ["workroom_id", "item_kind", "reference_id"],
    )
    op.create_index(
        "ix_workroom_context_items_workroom_id",
        "workroom_context_items",
        ["workroom_id"],
    )
    op.create_index(
        "ix_workroom_context_items_org_id", "workroom_context_items", ["org_id"]
    )
    op.create_index(
        "ix_workroom_context_items_item_kind",
        "workroom_context_items",
        ["item_kind"],
    )
    op.create_index(
        "ix_workroom_context_items_reference_id",
        "workroom_context_items",
        ["reference_id"],
    )
    op.create_index(
        "ix_workroom_context_items_mode", "workroom_context_items", ["mode"]
    )


def downgrade() -> None:
    op.drop_table("workroom_context_items")
