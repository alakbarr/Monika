"""Add partial fill and slippage columns to positions and paper_trade_records

Revision ID: q1a2b3c4d5e6
Revises: p1a2b3c4d5e6
Create Date: 2026-09-22 15:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'q1a2b3c4d5e6'
down_revision: Union[str, None] = 'p1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_existing_tables(conn) -> set:
    try:
        insp = sa.inspect(conn)
        return set(insp.get_table_names())
    except Exception:
        return set()


def upgrade() -> None:
    conn = op.get_bind()
    tables = _get_existing_tables(conn)

    if 'positions' in tables:
        insp = sa.inspect(conn)
        cols = {c['name']: c for c in insp.get_columns('positions')}
        if 'initial_volume' not in cols:
            op.add_column('positions', sa.Column('initial_volume', sa.Float(), nullable=True))
        if 'requested_volume' not in cols:
            op.add_column('positions', sa.Column('requested_volume', sa.Float(), nullable=True))
        if 'slippage_pips' not in cols:
            op.add_column('positions', sa.Column('slippage_pips', sa.Float(), nullable=True, server_default='0.0'))
        if 'partially_filled' not in cols:
            op.add_column('positions', sa.Column('partially_filled', sa.Boolean(), nullable=False, server_default=sa.false()))

    if 'paper_trade_records' in tables:
        insp = sa.inspect(conn)
        cols = {c['name']: c for c in insp.get_columns('paper_trade_records')}
        if 'partially_filled' not in cols:
            op.add_column('paper_trade_records', sa.Column('partially_filled', sa.Boolean(), nullable=False, server_default=sa.false()))
        if 'requested_lot' not in cols:
            op.add_column('paper_trade_records', sa.Column('requested_lot', sa.Float(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    tables = _get_existing_tables(conn)

    if 'paper_trade_records' in tables:
        insp = sa.inspect(conn)
        cols = {c['name']: c for c in insp.get_columns('paper_trade_records')}
        if 'requested_lot' in cols:
            op.drop_column('paper_trade_records', 'requested_lot')
        if 'partially_filled' in cols:
            op.drop_column('paper_trade_records', 'partially_filled')

    if 'positions' in tables:
        insp = sa.inspect(conn)
        cols = {c['name']: c for c in insp.get_columns('positions')}
        if 'partially_filled' in cols:
            op.drop_column('positions', 'partially_filled')
        if 'slippage_pips' in cols:
            op.drop_column('positions', 'slippage_pips')
        if 'requested_volume' in cols:
            op.drop_column('positions', 'requested_volume')
        if 'initial_volume' in cols:
            op.drop_column('positions', 'initial_volume')
