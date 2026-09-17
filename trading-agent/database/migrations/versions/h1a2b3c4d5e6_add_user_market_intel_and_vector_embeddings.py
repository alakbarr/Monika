"""Add user_market_intel table and vector embedding columns

Revision ID: h1a2b3c4d5e6
Revises: g1a2b3c4d5e6
Create Date: 2026-09-05 19:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'h1a2b3c4d5e6'
down_revision: Union[str, None] = 'g1a2b3c4d5e6'
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
        return {col['name'] for col in insp.get_columns(table_name)}
    except Exception:
        return set()


def upgrade() -> None:
    conn = op.get_bind()
    existing_tables = _get_existing_tables(conn)

    # 1. Table: user_market_intel
    if 'user_market_intel' not in existing_tables:
        op.create_table(
            'user_market_intel',
            sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
            sa.Column('telegram_user_id', sa.String(length=50), nullable=False, server_default='0'),
            sa.Column('intel_type', sa.String(length=30), nullable=False, server_default='tactical_directive'),
            sa.Column('title', sa.String(length=300), nullable=False),
            sa.Column('summary', sa.Text(), nullable=False),
            sa.Column('full_content', sa.Text(), nullable=True),
            sa.Column('affected_symbols', sa.String(length=100), nullable=False, server_default='ALL'),
            sa.Column('directive', sa.String(length=30), nullable=False, server_default='neutral'),
            sa.Column('target_cycle', sa.String(length=30), nullable=False, server_default='next_cycle_only'),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('consumed_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('consumed_by_cycle_id', sa.String(length=64), nullable=True),
            sa.Column('metadata_json', sa.Text(), nullable=True),
        )
        try:
            op.create_index('ix_user_market_intel_telegram_user_id', 'user_market_intel', ['telegram_user_id'])
            op.create_index('ix_user_market_intel_is_active', 'user_market_intel', ['is_active'])
            op.create_index('ix_user_market_intel_expires_at', 'user_market_intel', ['expires_at'])
            op.create_index('ix_user_market_intel_active_exp', 'user_market_intel', ['is_active', 'expires_at'])
        except Exception:
            pass

    # 2. Add embedding column to candidate_lessons if not exists
    cl_cols = _get_existing_columns(conn, 'candidate_lessons')
    if 'embedding' not in cl_cols:
        op.add_column('candidate_lessons', sa.Column('embedding', sa.JSON(), nullable=True))

    # 3. Add model_backend and is_fallback to timesfm_forecasts if not exists
    tf_cols = _get_existing_columns(conn, 'timesfm_forecasts')
    if 'model_backend' not in tf_cols:
        op.add_column('timesfm_forecasts', sa.Column('model_backend', sa.String(length=50), nullable=False, server_default='neural_timesfm_3.0'))
    if 'is_fallback' not in tf_cols:
        op.add_column('timesfm_forecasts', sa.Column('is_fallback', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    conn = op.get_bind()
    existing_tables = _get_existing_tables(conn)
    if 'user_market_intel' in existing_tables:
        op.drop_table('user_market_intel')

    cl_cols = _get_existing_columns(conn, 'candidate_lessons')
    if 'embedding' in cl_cols:
        op.drop_column('candidate_lessons', 'embedding')

    tf_cols = _get_existing_columns(conn, 'timesfm_forecasts')
    if 'model_backend' in tf_cols:
        op.drop_column('timesfm_forecasts', 'model_backend')
    if 'is_fallback' in tf_cols:
        op.drop_column('timesfm_forecasts', 'is_fallback')
