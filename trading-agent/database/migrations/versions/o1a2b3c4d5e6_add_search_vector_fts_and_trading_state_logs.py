"""Add search_vector FTS and trading_state_logs table

Revision ID: o1a2b3c4d5e6
Revises: n1a2b3c4d5e6
Create Date: 2026-09-20 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
try:
    from sqlalchemy.dialects.postgresql import TSVECTOR
except ImportError:
    TSVECTOR = sa.Text


# revision identifiers, used by Alembic.
revision: str = 'o1a2b3c4d5e6'
down_revision: Union[str, None] = 'n1a2b3c4d5e6'
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
    bind_dialect = conn.dialect.name

    # 1. decision_reflections
    if 'decision_reflections' in tables:
        insp = sa.inspect(conn)
        cols = {c['name']: c for c in insp.get_columns('decision_reflections')}
        if 'search_vector' not in cols:
            op.add_column('decision_reflections', sa.Column('search_vector', TSVECTOR, nullable=True))
            if bind_dialect == 'postgresql':
                op.create_index('idx_drefl_fts', 'decision_reflections', ['search_vector'], postgresql_using='gin')

    # 2. market_chronicle
    if 'market_chronicle' in tables:
        insp = sa.inspect(conn)
        cols = {c['name']: c for c in insp.get_columns('market_chronicle')}
        if 'search_vector' not in cols:
            op.add_column('market_chronicle', sa.Column('search_vector', TSVECTOR, nullable=True))
            if bind_dialect == 'postgresql':
                op.create_index('idx_chronicle_fts', 'market_chronicle', ['search_vector'], postgresql_using='gin')

    # 3. trading_state_logs
    if 'trading_state_logs' not in tables:
        op.create_table(
            'trading_state_logs',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('cycle_id', sa.String(length=64), nullable=False, index=True),
            sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False, index=True),
            sa.Column('summary_text', sa.Text(), nullable=False),
            sa.Column('state_payload', sa.JSON(), nullable=True),
            sa.Column('search_vector', TSVECTOR, nullable=True),
        )
        op.create_index('idx_tslog_cycle', 'trading_state_logs', ['cycle_id'])
        if bind_dialect == 'postgresql':
            op.create_index('idx_tslog_fts', 'trading_state_logs', ['search_vector'], postgresql_using='gin')

    # 4. cycle_events
    if 'cycle_events' not in tables:
        op.create_table(
            'cycle_events',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('cycle_id', sa.String(length=64), nullable=False, index=True),
            sa.Column('sequence', sa.Integer(), nullable=False),
            sa.Column('event_type', sa.String(length=64), nullable=False),
            sa.Column('payload', sa.JSON(), nullable=False),
            sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint('cycle_id', 'sequence', name='uq_cycle_event_seq'),
        )
        op.create_index('idx_cycle_event_type', 'cycle_events', ['event_type'])


def downgrade() -> None:
    conn = op.get_bind()
    tables = _get_existing_tables(conn)

    if 'cycle_events' in tables:
        op.drop_table('cycle_events')

    if 'trading_state_logs' in tables:
        op.drop_table('trading_state_logs')

    if 'market_chronicle' in tables:
        insp = sa.inspect(conn)
        cols = {c['name']: c for c in insp.get_columns('market_chronicle')}
        if 'search_vector' in cols:
            try:
                op.drop_index('idx_chronicle_fts', table_name='market_chronicle')
            except Exception:
                pass
            op.drop_column('market_chronicle', 'search_vector')

    if 'decision_reflections' in tables:
        insp = sa.inspect(conn)
        cols = {c['name']: c for c in insp.get_columns('decision_reflections')}
        if 'search_vector' in cols:
            try:
                op.drop_index('idx_drefl_fts', table_name='decision_reflections')
            except Exception:
                pass
            op.drop_column('decision_reflections', 'search_vector')
