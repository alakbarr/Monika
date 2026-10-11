"""fk_cascade_integrity

Revision ID: 0004_fk_cascade_integrity
Revises: 0003_benchmark_cache_cost
Create Date: 2026-10-11 08:50:00.000000

Ensures referential cascade integrity for all foreign key constraints across Monika.
Configures ON DELETE CASCADE on ephemeral and dependent child tables, and
ON DELETE SET NULL on financial records, performance metrics, and cognitive reflections.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '0004_fk_cascade_integrity'
down_revision: Union[str, Sequence[str], None] = '0003_benchmark_cache_cost'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Foreign key specifications:
# (table_name, column_name, ref_table, ref_column, ondelete, constraint_name)
FK_SPECS = [
    ('asset_analysis', 'brief_id', 'fundamental_briefs', 'id', 'SET NULL', 'fk_asset_analysis_brief_id'),
    ('trade_triggers', 'asset_analysis_id', 'asset_analysis', 'id', 'CASCADE', 'fk_trade_triggers_asset_analysis_id'),
    ('mt5_signals', 'asset_analysis_id', 'asset_analysis', 'id', 'CASCADE', 'fk_mt5_signals_asset_analysis_id'),
    ('orders', 'analysis_id', 'asset_analysis', 'id', 'SET NULL', 'fk_orders_analysis_id'),
    ('order_events', 'order_id', 'orders', 'id', 'CASCADE', 'fk_order_events_order_id'),
    ('positions', 'order_id', 'orders', 'id', 'SET NULL', 'fk_positions_order_id'),
    ('positions', 'analysis_id', 'asset_analysis', 'id', 'SET NULL', 'fk_positions_analysis_id'),
    ('trade_outcomes', 'analysis_id', 'asset_analysis', 'id', 'SET NULL', 'fk_trade_outcomes_analysis_id'),
    ('trade_outcomes', 'position_id', 'positions', 'id', 'SET NULL', 'fk_trade_outcomes_position_id'),
    ('paper_trade_records', 'analysis_id', 'asset_analysis', 'id', 'SET NULL', 'fk_paper_trade_records_analysis_id'),
    ('trade_plans', 'analysis_id', 'asset_analysis', 'id', 'SET NULL', 'fk_trade_plans_analysis_id'),
    ('trade_plan_legs', 'plan_id', 'trade_plans', 'id', 'CASCADE', 'fk_trade_plan_legs_plan_id'),
    ('trade_plan_legs', 'position_id', 'positions', 'id', 'SET NULL', 'fk_trade_plan_legs_position_id'),
    ('confluence_factor_outcomes', 'paper_trade_id', 'paper_trade_records', 'id', 'CASCADE', 'fk_cfo_paper_trade_id'),
    ('confluence_factor_outcomes', 'analysis_id', 'asset_analysis', 'id', 'CASCADE', 'fk_cfo_analysis_id'),
    ('decision_reflections', 'analysis_id', 'asset_analysis', 'id', 'SET NULL', 'fk_decision_reflections_analysis_id'),
    ('backtest_trade', 'run_id', 'backtest_run', 'id', 'CASCADE', 'fk_backtest_trade_run_id'),
    ('news_classification_outcomes', 'news_item_id', 'news_items', 'id', 'CASCADE', 'fk_news_cls_outcome_news_id'),
]


def upgrade() -> None:
    bind = op.get_bind()
    dialect_name = getattr(getattr(bind, 'dialect', None), 'name', '')

    if dialect_name == 'postgresql':
        for table, col, ref_table, ref_col, ondel, c_name in FK_SPECS:
            try:
                # Find existing constraint name in PostgreSQL
                q = sa.text("""
                    SELECT tc.constraint_name 
                    FROM information_schema.table_constraints AS tc 
                    JOIN information_schema.key_column_usage AS kcu
                      ON tc.constraint_name = kcu.constraint_name
                      AND tc.table_schema = kcu.table_schema
                    WHERE tc.constraint_type = 'FOREIGN KEY' 
                      AND tc.table_name = :table_name
                      AND kcu.column_name = :column_name;
                """)
                res = bind.execute(q, {"table_name": table, "column_name": col})
                rows = res.fetchall() if hasattr(res, 'fetchall') else []
                existing_names = [r[0] for r in rows if r]
                for old_name in existing_names:
                    op.execute(sa.text(f'ALTER TABLE {table} DROP CONSTRAINT IF EXISTS "{old_name}";'))
                
                # Add updated constraint with explicit ondelete rule
                op.execute(sa.text(
                    f'ALTER TABLE {table} ADD CONSTRAINT "{c_name}" '
                    f'FOREIGN KEY ({col}) REFERENCES {ref_table}({ref_col}) ON DELETE {ondel};'
                ))
            except Exception:
                # Fallback to standard batch_alter_table
                with op.batch_alter_table(table) as batch_op:
                    batch_op.create_foreign_key(c_name, ref_table, [col], [ref_col], ondelete=ondel)
    else:
        for table, col, ref_table, ref_col, ondel, c_name in FK_SPECS:
            with op.batch_alter_table(table) as batch_op:
                batch_op.create_foreign_key(c_name, ref_table, [col], [ref_col], ondelete=ondel)


def downgrade() -> None:
    bind = op.get_bind()
    dialect_name = getattr(getattr(bind, 'dialect', None), 'name', '')

    if dialect_name == 'postgresql':
        for table, col, ref_table, ref_col, _, c_name in FK_SPECS:
            try:
                op.execute(sa.text(f'ALTER TABLE {table} DROP CONSTRAINT IF EXISTS "{c_name}";'))
                op.execute(sa.text(
                    f'ALTER TABLE {table} ADD CONSTRAINT "{c_name}" '
                    f'FOREIGN KEY ({col}) REFERENCES {ref_table}({ref_col});'
                ))
            except Exception:
                with op.batch_alter_table(table) as batch_op:
                    batch_op.create_foreign_key(c_name, ref_table, [col], [ref_col])
    else:
        for table, col, ref_table, ref_col, _, c_name in FK_SPECS:
            with op.batch_alter_table(table) as batch_op:
                batch_op.create_foreign_key(c_name, ref_table, [col], [ref_col])
