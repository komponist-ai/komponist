"""Add organization departments and department-scoped sources.

Revision ID: 008
Revises: 007
Create Date: 2026-07-17
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "departments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("color", sa.String(20), nullable=False, server_default="orange"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("org_id", "name", name="uq_department_org_name"),
    )
    op.create_index("ix_departments_org_id", "departments", ["org_id"])

    op.create_table(
        "department_memberships",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("department_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "department_id",
            "user_id",
            name="uq_department_membership_department_user",
        ),
    )
    op.create_index(
        "ix_department_memberships_org_id", "department_memberships", ["org_id"]
    )
    op.create_index(
        "ix_department_memberships_department_id",
        "department_memberships",
        ["department_id"],
    )
    op.create_index(
        "ix_department_memberships_user_id", "department_memberships", ["user_id"]
    )

    op.add_column(
        "organization_invitations",
        sa.Column("department_ids", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "connected_sources",
        sa.Column("department_id", sa.String(36), nullable=True),
    )
    op.create_index(
        "ix_connected_sources_department_id", "connected_sources", ["department_id"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_connected_sources_department_id", table_name="connected_sources"
    )
    op.drop_column("connected_sources", "department_id")
    op.drop_column("organization_invitations", "department_ids")
    op.drop_index(
        "ix_department_memberships_user_id", table_name="department_memberships"
    )
    op.drop_index(
        "ix_department_memberships_department_id", table_name="department_memberships"
    )
    op.drop_index(
        "ix_department_memberships_org_id", table_name="department_memberships"
    )
    op.drop_table("department_memberships")
    op.drop_index("ix_departments_org_id", table_name="departments")
    op.drop_table("departments")
