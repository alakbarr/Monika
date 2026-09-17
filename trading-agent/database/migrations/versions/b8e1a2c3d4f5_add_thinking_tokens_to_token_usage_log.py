"""Add thinking_tokens to token_usage_log

Revision ID: b8e1a2c3d4f5
Revises: e918c7d6a5b4
Create Date: 2026-08-28 16:20:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8e1a2c3d4f5'
down_revision: Union[str, None] = 'e918c7d6a5b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_existing_columns(conn, table_name: str) -> set:
    try:
        insp = sa.inspect(conn)
        return {col['name'] for col in insp.get_columns(table_name)}
    except Exception:
        return set()


def _get_existing_indexes(conn, table_name: str) -> set:
    try:
        insp = sa.inspect(conn)
        return {idx['name'] for idx in insp.get_indexes(table_name)}
    except Exception:
        return set()


def upgrade() -> None:
    conn = op.get_bind()
    cols = _get_existing_columns(conn, 'token_usage_log')
    if 'thinking_tokens' not in cols:
        op.add_column('token_usage_log', sa.Column('thinking_tokens', sa.Integer(), nullable=False, server_default='0'))
    
    idxs = _get_existing_indexes(conn, 'token_usage_log')
    idx_name = op.f('ix_token_usage_log_thinking_tokens')
    if idx_name not in idxs:
        op.create_index(idx_name, 'token_usage_log', ['thinking_tokens'], unique=False)


def downgrade() -> None:
    conn = op.get_bind()
    idxs = _get_existing_indexes(conn, 'token_usage_log')
    idx_name = op.f('ix_token_usage_log_thinking_tokens')
    if idx_name in idxs:
        op.drop_index(idx_name, table_name='token_usage_log')
    
    cols = _get_existing_columns(conn, 'token_usage_log')
    if 'thinking_tokens' in cols:
        op.drop_column('token_usage_log', 'thinking_tokens')
