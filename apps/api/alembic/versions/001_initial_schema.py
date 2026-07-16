"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-07-11 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Orgs
    op.create_table(
        'orgs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now())
    )

    # Users
    op.create_table(
        'users',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('org_id', sa.String(36), nullable=False),
        sa.Column('email', sa.String(255), nullable=False, unique=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now())
    )
    op.create_index('ix_users_org_id', 'users', ['org_id'])

    # Events raw (webhook landing zone)
    op.create_table(
        'events_raw',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('org_id', sa.String(36), nullable=False),
        sa.Column('source', sa.String(50), nullable=False),
        sa.Column('event_type', sa.String(100), nullable=False),
        sa.Column('payload', postgresql.JSONB(), nullable=False),
        sa.Column('processed_at', sa.DateTime(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now())
    )
    op.create_index('ix_events_raw_org_id', 'events_raw', ['org_id'])
    op.create_index('ix_events_raw_source', 'events_raw', ['source'])
    op.create_index('ix_events_raw_processed_at', 'events_raw', ['processed_at'])
    op.create_index('ix_events_raw_created_at', 'events_raw', ['created_at'])

    # Tool calls (MCP metrics)
    op.create_table(
        'tool_calls',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('org_id', sa.String(36), nullable=False),
        sa.Column('tool', sa.String(100), nullable=False),
        sa.Column('input', postgresql.JSONB(), nullable=False),
        sa.Column('output', postgresql.JSONB(), nullable=True),
        sa.Column('verdict', sa.String(50), nullable=True),
        sa.Column('agent_client', sa.String(100), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now())
    )
    op.create_index('ix_tool_calls_org_id', 'tool_calls', ['org_id'])
    op.create_index('ix_tool_calls_tool', 'tool_calls', ['tool'])
    op.create_index('ix_tool_calls_verdict', 'tool_calls', ['verdict'])
    op.create_index('ix_tool_calls_created_at', 'tool_calls', ['created_at'])

    # Sync state (integration cursors)
    op.create_table(
        'sync_state',
        sa.Column('org_id', sa.String(36), primary_key=True),
        sa.Column('source', sa.String(50), primary_key=True),
        sa.Column('cursor', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now())
    )


def downgrade() -> None:
    op.drop_table('sync_state')
    op.drop_table('tool_calls')
    op.drop_table('events_raw')
    op.drop_table('users')
    op.drop_table('orgs')
