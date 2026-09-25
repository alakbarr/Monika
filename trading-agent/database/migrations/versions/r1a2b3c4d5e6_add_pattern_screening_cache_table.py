"""Add pattern_screening_cache table for multi-timeframe pattern similarity screening

Revision ID: r1a2b3c4d5e6
Revises: q1a2b3c4d5e6
Create Date: 2026-09-25 20:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'r1a2b3c4d5e6'
down_revision: Union[str, None] = 'q1a2b3c4d5e6'
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

    if 'pattern_screening_cache' not in tables:
        op.create_table(
            'pattern_screening_cache',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('symbol', sa.String(length=20), nullable=False),
            sa.Column('screened_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('overall_bias', sa.String(length=10), nullable=False),
            sa.Column('confidence', sa.String(length=10), nullable=False),
            sa.Column('consensus_bullish_pct', sa.Float(), nullable=False, server_default='0.5'),
            sa.Column('consensus_bearish_pct', sa.Float(), nullable=False, server_default='0.5'),
            sa.Column('has_timeframe_conflict', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('significant_timeframes_json', sa.Text(), nullable=True),
            sa.Column('per_timeframe_json', sa.Text(), nullable=True),
            sa.Column('full_result_json', sa.Text(), nullable=True),
        )
        op.create_index(
            'idx_pattern_cache_sym_at',
            'pattern_screening_cache',
            ['symbol', 'screened_at'],
            unique=False
        )


def downgrade() -> None:
    conn = op.get_bind()
    tables = _get_existing_tables(conn)

    if 'pattern_screening_cache' in tables:
        op.drop_index('idx_pattern_cache_sym_at', table_name='pattern_screening_cache')
        op.drop_table('pattern_screening_cache')
