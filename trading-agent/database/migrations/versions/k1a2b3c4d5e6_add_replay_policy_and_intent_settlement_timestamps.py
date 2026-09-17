"""Add replay_policy and intent/settlement timestamps to orders for two-phase crash safety

Revision ID: k1a2b3c4d5e6
Revises: ce03bbdda5af
Create Date: 2026-09-13 23:05:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'k1a2b3c4d5e6'
down_revision: Union[str, None] = 'ce03bbdda5af'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_existing_tables(conn) -> set:
    try:
        insp = sa.inspect(conn)
        return set(insp.get_table_names())
    except Exception:
        return set()


def _get_existing_columns(conn, table_name: str) -> set:
    try:
        insp = sa.inspect(conn)
        return {c['name'] for c in insp.get_columns(table_name)}
    except Exception:
        return set()


def upgrade() -> None:
    conn = op.get_bind()
    tables = _get_existing_tables(conn)

    if 'orders' in tables:
        cols = _get_existing_columns(conn, 'orders')
        if 'replay_policy' not in cols:
            op.add_column(
                'orders',
                sa.Column('replay_policy', sa.String(length=20), nullable=False, server_default='never')
            )
        if 'intent_committed_at' not in cols:
            op.add_column(
                'orders',
                sa.Column('intent_committed_at', sa.DateTime(timezone=True), nullable=True)
            )
        if 'settlement_committed_at' not in cols:
            op.add_column(
                'orders',
                sa.Column('settlement_committed_at', sa.DateTime(timezone=True), nullable=True)
            )


def downgrade() -> None:
    conn = op.get_bind()
    tables = _get_existing_tables(conn)

    if 'orders' in tables:
        cols = _get_existing_columns(conn, 'orders')
        if 'settlement_committed_at' in cols:
            op.drop_column('orders', 'settlement_committed_at')
        if 'intent_committed_at' in cols:
            op.drop_column('orders', 'intent_committed_at')
        if 'replay_policy' in cols:
            op.drop_column('orders', 'replay_policy')
