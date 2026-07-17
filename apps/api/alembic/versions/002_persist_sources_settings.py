"""Persist connected sources and organization settings.

Revision ID: 002
Revises: 001
Create Date: 2026-07-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "org_settings",
        sa.Column("org_id", sa.String(50), primary_key=True),
        sa.Column("auto_confirm", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("parallel_batch_size", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "connected_sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(50), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="connected"),
        sa.Column("last_sync", sa.DateTime(), nullable=True),
        sa.Column("item_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("config_ciphertext", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("org_id", "id", name="uq_connected_sources_org_id_id"),
    )
    op.create_index("ix_connected_sources_org_id", "connected_sources", ["org_id"])
    op.create_index("ix_connected_sources_source_type", "connected_sources", ["source_type"])


def downgrade() -> None:
    op.drop_index("ix_connected_sources_source_type", table_name="connected_sources")
    op.drop_index("ix_connected_sources_org_id", table_name="connected_sources")
    op.drop_table("connected_sources")
    op.drop_table("org_settings")
