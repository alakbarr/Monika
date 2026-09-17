"""Enhance token_usage_log audit fields

Revision ID: a8d29c4e1f7b
Revises: f39b1a2c3d4e
Create Date: 2026-08-27 10:58:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a8d29c4e1f7b'
down_revision: Union[str, None] = 'f39b1a2c3d4e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new columns to token_usage_log
    op.add_column('token_usage_log', sa.Column('task_role', sa.String(length=100), nullable=True))
    op.add_column('token_usage_log', sa.Column('subsystem', sa.String(length=50), nullable=True))
    op.add_column('token_usage_log', sa.Column('symbol', sa.String(length=20), nullable=True))
    op.add_column('token_usage_log', sa.Column('cycle_id', sa.String(length=64), nullable=True))
    op.add_column('token_usage_log', sa.Column('cached_tokens', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('token_usage_log', sa.Column('cache_creation_tokens', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('token_usage_log', sa.Column('execution_time_ms', sa.Integer(), nullable=True))
    op.add_column('token_usage_log', sa.Column('status', sa.String(length=20), nullable=False, server_default='success'))
    op.add_column('token_usage_log', sa.Column('slot_name', sa.String(length=20), nullable=False, server_default='primary'))

    # Create indexes for efficient analytics queries
    op.create_index(op.f('ix_token_usage_log_task_role'), 'token_usage_log', ['task_role'], unique=False)
    op.create_index(op.f('ix_token_usage_log_subsystem'), 'token_usage_log', ['subsystem'], unique=False)
    op.create_index(op.f('ix_token_usage_log_symbol'), 'token_usage_log', ['symbol'], unique=False)
    op.create_index(op.f('ix_token_usage_log_cycle_id'), 'token_usage_log', ['cycle_id'], unique=False)
    op.create_index(op.f('ix_token_usage_log_status'), 'token_usage_log', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_token_usage_log_status'), table_name='token_usage_log')
    op.drop_index(op.f('ix_token_usage_log_cycle_id'), table_name='token_usage_log')
    op.drop_index(op.f('ix_token_usage_log_symbol'), table_name='token_usage_log')
    op.drop_index(op.f('ix_token_usage_log_subsystem'), table_name='token_usage_log')
    op.drop_index(op.f('ix_token_usage_log_task_role'), table_name='token_usage_log')

    op.drop_column('token_usage_log', 'slot_name')
    op.drop_column('token_usage_log', 'status')
    op.drop_column('token_usage_log', 'execution_time_ms')
    op.drop_column('token_usage_log', 'cache_creation_tokens')
    op.drop_column('token_usage_log', 'cached_tokens')
    op.drop_column('token_usage_log', 'cycle_id')
    op.drop_column('token_usage_log', 'symbol')
    op.drop_column('token_usage_log', 'subsystem')
    op.drop_column('token_usage_log', 'task_role')
