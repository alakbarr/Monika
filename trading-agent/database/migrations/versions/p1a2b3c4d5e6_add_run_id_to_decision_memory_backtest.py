"""Add run_id to decision_memory_backtest

Revision ID: p1a2b3c4d5e6
Revises: o1a2b3c4d5e6
Create Date: 2026-09-22 14:40:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'p1a2b3c4d5e6'
down_revision: Union[str, None] = 'o1a2b3c4d5e6'
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

    if 'decision_memory_backtest' in tables:
        insp = sa.inspect(conn)
        cols = {c['name']: c for c in insp.get_columns('decision_memory_backtest')}
        if 'run_id' not in cols:
            op.add_column('decision_memory_backtest', sa.Column('run_id', sa.Integer(), nullable=True))
            op.create_index('ix_decision_memory_backtest_run_id', 'decision_memory_backtest', ['run_id'])


def downgrade() -> None:
    conn = op.get_bind()
    tables = _get_existing_tables(conn)

    if 'decision_memory_backtest' in tables:
        insp = sa.inspect(conn)
        cols = {c['name']: c for c in insp.get_columns('decision_memory_backtest')}
        if 'run_id' in cols:
            op.drop_index('ix_decision_memory_backtest_run_id', table_name='decision_memory_backtest')
            op.drop_column('decision_memory_backtest', 'run_id')
