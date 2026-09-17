"""Sync all models and missing tables

Revision ID: c1a2b3d4e5f6
Revises: b8e1a2c3d4f5
Create Date: 2026-08-29 11:45:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1a2b3d4e5f6'
down_revision: Union[str, None] = 'b8e1a2c3d4f5'
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

    # 1. Update trade_outcomes columns
    if 'trade_outcomes' in existing_tables:
        to_cols = _get_existing_columns(conn, 'trade_outcomes')
        if 'was_debate_modified' not in to_cols:
            op.add_column('trade_outcomes', sa.Column('was_debate_modified', sa.Boolean(), nullable=True, server_default=sa.text('false')))
        if 'decision_source' not in to_cols:
            op.add_column('trade_outcomes', sa.Column('decision_source', sa.String(length=50), nullable=True))
    else:
        op.create_table(
            'trade_outcomes',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('analysis_id', sa.Integer(), sa.ForeignKey('asset_analysis.id'), nullable=True, index=True),
            sa.Column('position_id', sa.Integer(), sa.ForeignKey('positions.id'), nullable=True, index=True),
            sa.Column('symbol', sa.String(length=20), nullable=False),
            sa.Column('direction', sa.String(length=10), nullable=False),
            sa.Column('entry_price', sa.Float(), nullable=True),
            sa.Column('exit_price', sa.Float(), nullable=True),
            sa.Column('stop_loss', sa.Float(), nullable=True),
            sa.Column('take_profit', sa.Float(), nullable=True),
            sa.Column('pnl_usd', sa.Float(), nullable=True),
            sa.Column('exit_reason', sa.String(length=30), nullable=True),
            sa.Column('confluence_score', sa.Integer(), nullable=True),
            sa.Column('priced_in_score', sa.Integer(), nullable=True),
            sa.Column('analysis_confidence', sa.Float(), nullable=True),
            sa.Column('opened_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('holding_hours', sa.Float(), nullable=True),
            sa.Column('was_profitable', sa.Boolean(), nullable=True),
            sa.Column('was_debate_modified', sa.Boolean(), nullable=True, server_default=sa.text('false')),
            sa.Column('decision_source', sa.String(length=50), nullable=True),
        )
        op.create_index('idx_trade_outcome_symbol', 'trade_outcomes', ['symbol'], unique=False)
        op.create_index('idx_trade_outcome_closed', 'trade_outcomes', ['closed_at'], unique=False)
        op.create_index('idx_trade_outcome_profitable', 'trade_outcomes', ['was_profitable'], unique=False)

    # 2. Update decision_reflections columns (SSVP Quality tracking)
    if 'decision_reflections' in existing_tables:
        drefl_cols = _get_existing_columns(conn, 'decision_reflections')
        if 'context_cds_score' not in drefl_cols:
            op.add_column('decision_reflections', sa.Column('context_cds_score', sa.Float(), nullable=True))
        if 'context_snapshot_id' not in drefl_cols:
            op.add_column('decision_reflections', sa.Column('context_snapshot_id', sa.String(length=64), nullable=True))
        if 'is_context_contaminated' not in drefl_cols:
            op.add_column('decision_reflections', sa.Column('is_context_contaminated', sa.Boolean(), nullable=False, server_default=sa.text('false')))
        if 'contamination_reason' not in drefl_cols:
            op.add_column('decision_reflections', sa.Column('contamination_reason', sa.String(length=255), nullable=True))

    # 3. Update news_items columns
    if 'news_items' in existing_tables:
        news_cols = _get_existing_columns(conn, 'news_items')
        if 'key_data_point' not in news_cols:
            op.add_column('news_items', sa.Column('key_data_point', sa.String(length=300), nullable=True))

    # 4. Create prescreen_log
    if 'prescreen_log' not in existing_tables:
        op.create_table(
            'prescreen_log',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('symbol', sa.String(length=20), nullable=False),
            sa.Column('decision', sa.String(length=10), nullable=False),
            sa.Column('reason', sa.Text(), nullable=False),
            sa.Column('price_at_check', sa.Float(), nullable=True),
            sa.Column('checked_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column('price_4h_after', sa.Float(), nullable=True),
            sa.Column('resolved', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        )
        op.create_index(op.f('ix_prescreen_log_symbol'), 'prescreen_log', ['symbol'], unique=False)
        op.create_index('idx_prescreen_symbol_time', 'prescreen_log', ['symbol', 'checked_at'], unique=False)

    # 5. Create candidate_lessons
    if 'candidate_lessons' not in existing_tables:
        op.create_table(
            'candidate_lessons',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('symbol', sa.String(length=20), nullable=False),
            sa.Column('lesson_text', sa.Text(), nullable=False),
            sa.Column('status', sa.String(length=30), nullable=False, server_default='shadow'),
            sa.Column('proposed_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column('evaluated_trades_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('win_rate_delta', sa.Float(), nullable=False, server_default='0.0'),
            sa.Column('sharpe_delta', sa.Float(), nullable=False, server_default='0.0'),
            sa.Column('promoted_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('rejection_reason', sa.String(length=255), nullable=True),
        )
        op.create_index(op.f('ix_candidate_lessons_symbol'), 'candidate_lessons', ['symbol'], unique=False)
        op.create_index(op.f('ix_candidate_lessons_status'), 'candidate_lessons', ['status'], unique=False)

    # 6. Create backtest_run
    if 'backtest_run' not in existing_tables:
        op.create_table(
            'backtest_run',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('mode', sa.String(length=10), nullable=False),
            sa.Column('start_date', sa.DateTime(timezone=True), nullable=False),
            sa.Column('end_date', sa.DateTime(timezone=True), nullable=False),
            sa.Column('step_hours', sa.Integer(), nullable=False, server_default='6'),
            sa.Column('initial_equity', sa.Float(), nullable=False, server_default='10000.0'),
            sa.Column('final_equity', sa.Float(), nullable=True),
            sa.Column('total_trades', sa.Integer(), nullable=True),
            sa.Column('win_rate', sa.Float(), nullable=True),
            sa.Column('profit_factor', sa.Float(), nullable=True),
            sa.Column('sharpe_ratio', sa.Float(), nullable=True),
            sa.Column('max_drawdown_pct', sa.Float(), nullable=True),
            sa.Column('settings_snapshot', sa.JSON(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    # 7. Create backtest_trade
    if 'backtest_trade' not in existing_tables:
        op.create_table(
            'backtest_trade',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('run_id', sa.Integer(), sa.ForeignKey('backtest_run.id'), nullable=False),
            sa.Column('symbol', sa.String(length=20), nullable=False),
            sa.Column('direction', sa.String(length=10), nullable=False),
            sa.Column('entry_time', sa.DateTime(timezone=True), nullable=False),
            sa.Column('entry_price', sa.Float(), nullable=False),
            sa.Column('stop_loss', sa.Float(), nullable=False),
            sa.Column('take_profit', sa.Float(), nullable=False),
            sa.Column('confidence', sa.Float(), nullable=True),
            sa.Column('confluence_score', sa.Integer(), nullable=True),
            sa.Column('rationale', sa.Text(), nullable=True),
            sa.Column('exit_time', sa.DateTime(timezone=True), nullable=True),
            sa.Column('exit_price', sa.Float(), nullable=True),
            sa.Column('exit_reason', sa.String(length=20), nullable=True),
            sa.Column('pnl_pips', sa.Float(), nullable=True),
            sa.Column('pnl_pct', sa.Float(), nullable=True),
            sa.Column('executed_lots', sa.Float(), nullable=True),
            sa.Column('model_used', sa.String(length=50), nullable=True),
            sa.Column('input_tokens', sa.Integer(), nullable=True),
            sa.Column('output_tokens', sa.Integer(), nullable=True),
        )

    # 8. Create decision_memory_backtest
    if 'decision_memory_backtest' not in existing_tables:
        op.create_table(
            'decision_memory_backtest',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('symbol', sa.String(length=20), nullable=False),
            sa.Column('decision_date', sa.DateTime(timezone=True), nullable=False),
            sa.Column('decision', sa.String(length=10), nullable=False),
            sa.Column('confidence', sa.Float(), nullable=True),
            sa.Column('rationale_summary', sa.Text(), nullable=True),
            sa.Column('raw_return', sa.Float(), nullable=True),
            sa.Column('holding_days', sa.Integer(), nullable=True),
            sa.Column('outcome_status', sa.String(length=20), nullable=False, server_default='pending'),
            sa.Column('reflection', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    conn = op.get_bind()
    existing_tables = _get_existing_tables(conn)

    # Drop backtest tables
    if 'decision_memory_backtest' in existing_tables:
        op.drop_table('decision_memory_backtest')
    if 'backtest_trade' in existing_tables:
        op.drop_table('backtest_trade')
    if 'backtest_run' in existing_tables:
        op.drop_table('backtest_run')

    # Drop candidate_lessons
    if 'candidate_lessons' in existing_tables:
        op.drop_index(op.f('ix_candidate_lessons_status'), table_name='candidate_lessons')
        op.drop_index(op.f('ix_candidate_lessons_symbol'), table_name='candidate_lessons')
        op.drop_table('candidate_lessons')

    # Drop prescreen_log
    if 'prescreen_log' in existing_tables:
        op.drop_index('idx_prescreen_symbol_time', table_name='prescreen_log')
        op.drop_index(op.f('ix_prescreen_log_symbol'), table_name='prescreen_log')
        op.drop_table('prescreen_log')

    # Drop news_items column
    if 'news_items' in existing_tables:
        news_cols = _get_existing_columns(conn, 'news_items')
        if 'key_data_point' in news_cols:
            op.drop_column('news_items', 'key_data_point')

    # Drop decision_reflections columns
    if 'decision_reflections' in existing_tables:
        drefl_cols = _get_existing_columns(conn, 'decision_reflections')
        if 'contamination_reason' in drefl_cols:
            op.drop_column('decision_reflections', 'contamination_reason')
        if 'is_context_contaminated' in drefl_cols:
            op.drop_column('decision_reflections', 'is_context_contaminated')
        if 'context_snapshot_id' in drefl_cols:
            op.drop_column('decision_reflections', 'context_snapshot_id')
        if 'context_cds_score' in drefl_cols:
            op.drop_column('decision_reflections', 'context_cds_score')

    # Drop trade_outcomes columns
    if 'trade_outcomes' in existing_tables:
        to_cols = _get_existing_columns(conn, 'trade_outcomes')
        if 'decision_source' in to_cols:
            op.drop_column('trade_outcomes', 'decision_source')
        if 'was_debate_modified' in to_cols:
            op.drop_column('trade_outcomes', 'was_debate_modified')
