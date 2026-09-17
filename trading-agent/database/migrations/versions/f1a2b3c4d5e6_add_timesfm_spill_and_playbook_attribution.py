"""Add timesfm_forecasts, context_spill_blobs, and playbook_rule_attributions tables

Revision ID: f1a2b3c4d5e6
Revises: e1b2c3d4e5f6
Create Date: 2026-09-04 13:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'e1b2c3d4e5f6'
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

    # 1. Table: timesfm_forecasts
    if 'timesfm_forecasts' not in existing_tables:
        op.create_table(
            'timesfm_forecasts',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('symbol', sa.String(length=20), nullable=False, index=True),
            sa.Column('timeframe', sa.String(length=10), nullable=False, server_default='H1'),
            sa.Column('generated_at', sa.DateTime(timezone=True), nullable=False, index=True),
            sa.Column('horizon_steps', sa.Integer(), nullable=False, server_default='24'),
            sa.Column('quantiles_json', sa.Text(), nullable=False),
            sa.Column('expected_range', sa.Float(), nullable=False),
            sa.Column('quantile_skew', sa.Float(), nullable=False),
            sa.Column('volatility_expansion_ratio', sa.Float(), nullable=False),
            sa.Column('reachability_envelope', sa.Text(), nullable=True),
        )
        try:
            op.create_index('idx_timesfm_sym_time', 'timesfm_forecasts', ['symbol', 'timeframe', 'generated_at'])
        except Exception:
            pass

    # 2. Table: context_spill_blobs
    if 'context_spill_blobs' not in existing_tables:
        op.create_table(
            'context_spill_blobs',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('blob_id', sa.String(length=64), nullable=False, unique=True, index=True),
            sa.Column('cycle_id', sa.String(length=64), nullable=True, index=True),
            sa.Column('tool_name', sa.String(length=100), nullable=False, index=True),
            sa.Column('token_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('payload_text', sa.Text(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, index=True),
        )
        try:
            op.create_index('idx_spill_cycle_tool', 'context_spill_blobs', ['cycle_id', 'tool_name'])
        except Exception:
            pass

    # 3. Table: playbook_rule_attributions
    if 'playbook_rule_attributions' not in existing_tables:
        op.create_table(
            'playbook_rule_attributions',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('rule_hash', sa.String(length=64), nullable=False, index=True),
            sa.Column('symbol', sa.String(length=20), nullable=False, index=True),
            sa.Column('rule_text', sa.Text(), nullable=False),
            sa.Column('status', sa.String(length=30), nullable=False, server_default='active', index=True),
            sa.Column('times_triggered', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('wins_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('losses_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('total_pnl', sa.Float(), nullable=False, server_default='0.0'),
            sa.Column('win_rate', sa.Float(), nullable=False, server_default='0.0'),
            sa.Column('last_triggered_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('promoted_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('deprecated_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('deprecation_reason', sa.String(length=255), nullable=True),
        )
        try:
            op.create_index('idx_playbook_rule_sym_stat', 'playbook_rule_attributions', ['symbol', 'status'])
        except Exception:
            pass

    # 4. Column: embedding in decision_reflections
    if 'decision_reflections' in existing_tables:
        dr_cols = _get_existing_columns(conn, 'decision_reflections')
        if 'embedding' not in dr_cols:
            op.add_column('decision_reflections', sa.Column('embedding', sa.JSON(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    existing_tables = _get_existing_tables(conn)

    if 'decision_reflections' in existing_tables:
        dr_cols = _get_existing_columns(conn, 'decision_reflections')
        if 'embedding' in dr_cols:
            op.drop_column('decision_reflections', 'embedding')

    if 'playbook_rule_attributions' in existing_tables:
        try:
            op.drop_index('idx_playbook_rule_sym_stat', table_name='playbook_rule_attributions')
        except Exception:
            pass
        op.drop_table('playbook_rule_attributions')

    if 'context_spill_blobs' in existing_tables:
        try:
            op.drop_index('idx_spill_cycle_tool', table_name='context_spill_blobs')
        except Exception:
            pass
        op.drop_table('context_spill_blobs')

    if 'timesfm_forecasts' in existing_tables:
        try:
            op.drop_index('idx_timesfm_sym_time', table_name='timesfm_forecasts')
        except Exception:
            pass
        op.drop_table('timesfm_forecasts')

