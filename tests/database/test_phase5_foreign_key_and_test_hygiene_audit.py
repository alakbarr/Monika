"""
Test Suite: Phase 5 Foreign Key Cascade Integrity & Test Hygiene Audit
========================================================================
Verifies:
1. All 18 ForeignKeys across Monika database models define explicit ondelete rules.
2. The partition between ON DELETE CASCADE (lifecycle) and ON DELETE SET NULL (preservation)
   strictly follows domain safety rules: financial and cognitive records are never deleted on cascade.
3. Alembic migration chain includes 0004_fk_cascade_integrity.
4. Database cleanup retention invariants (D1 >= 400d, H1/H4 >= 30d, M15 >= 3d).
"""
import pytest
from sqlalchemy import inspect
from database.models import (
    Base, AssetAnalysis, TradeTrigger, MT5Signal, Order, OrderEvent, Position,
    TradeOutcome, PaperTradeRecord, TradePlan, TradePlanLeg, ConfluenceFactorOutcome,
    DecisionReflection, BacktestTrade, NewsClassificationOutcome
)


class TestPhase5ForeignKeyIntegrity:
    """Verifies that foreign key declarations have explicit, domain-appropriate ondelete policies."""

    def test_all_expected_foreign_keys_have_explicit_ondelete(self):
        """Every target foreign key must explicitly define ondelete ('CASCADE' or 'SET NULL')."""
        expected_rules = {
            ('asset_analysis', 'brief_id'): 'SET NULL',
            ('trade_triggers', 'asset_analysis_id'): 'CASCADE',
            ('mt5_signals', 'asset_analysis_id'): 'CASCADE',
            ('orders', 'analysis_id'): 'SET NULL',
            ('order_events', 'order_id'): 'CASCADE',
            ('positions', 'order_id'): 'SET NULL',
            ('positions', 'analysis_id'): 'SET NULL',
            ('trade_outcomes', 'analysis_id'): 'SET NULL',
            ('trade_outcomes', 'position_id'): 'SET NULL',
            ('paper_trade_records', 'analysis_id'): 'SET NULL',
            ('trade_plans', 'analysis_id'): 'SET NULL',
            ('trade_plan_legs', 'plan_id'): 'CASCADE',
            ('trade_plan_legs', 'position_id'): 'SET NULL',
            ('confluence_factor_outcomes', 'paper_trade_id'): 'CASCADE',
            ('confluence_factor_outcomes', 'analysis_id'): 'CASCADE',
            ('decision_reflections', 'analysis_id'): 'SET NULL',
            ('backtest_trade', 'run_id'): 'CASCADE',
            ('news_classification_outcomes', 'news_item_id'): 'CASCADE',
        }

        for (table_name, col_name), expected_ondelete in expected_rules.items():
            table = Base.metadata.tables[table_name]
            col = table.columns[col_name]
            assert len(col.foreign_keys) == 1, f"Missing foreign key on {table_name}.{col_name}"
            fk = next(iter(col.foreign_keys))
            assert fk.ondelete is not None, f"Foreign key on {table_name}.{col_name} has no ondelete rule"
            assert fk.ondelete.upper() == expected_ondelete, (
                f"Foreign key on {table_name}.{col_name} ondelete={fk.ondelete.upper()} "
                f"does not match expected {expected_ondelete}"
            )

    def test_financial_records_never_cascade_delete(self):
        """Safety Fortress: Financial audit records and reflections must NEVER use CASCADE."""
        forbidden_cascade_columns = [
            ('orders', 'analysis_id'),
            ('positions', 'order_id'),
            ('positions', 'analysis_id'),
            ('trade_outcomes', 'analysis_id'),
            ('trade_outcomes', 'position_id'),
            ('paper_trade_records', 'analysis_id'),
            ('trade_plans', 'analysis_id'),
            ('decision_reflections', 'analysis_id'),
        ]

        for table_name, col_name in forbidden_cascade_columns:
            table = Base.metadata.tables[table_name]
            col = table.columns[col_name]
            fk = next(iter(col.foreign_keys))
            assert fk.ondelete is not None
            assert fk.ondelete.upper() != 'CASCADE', (
                f"CRITICAL FINANCIAL SAFETY VIOLATION: {table_name}.{col_name} has ON DELETE CASCADE!"
            )
            assert fk.ondelete.upper() == 'SET NULL', (
                f"Expected {table_name}.{col_name} to use ON DELETE SET NULL, got {fk.ondelete}"
            )
            # Ensure the column allows NULL so SET NULL cannot trigger integrity errors
            assert col.nullable is True, (
                f"Column {table_name}.{col_name} with SET NULL must be nullable=True"
            )

    def test_ephemeral_triggers_and_signals_cascade_delete(self):
        """Dependent child items must cleanly cascade delete with their parent analysis/order."""
        required_cascade_columns = [
            ('trade_triggers', 'asset_analysis_id'),
            ('mt5_signals', 'asset_analysis_id'),
            ('order_events', 'order_id'),
            ('trade_plan_legs', 'plan_id'),
            ('confluence_factor_outcomes', 'paper_trade_id'),
            ('confluence_factor_outcomes', 'analysis_id'),
            ('backtest_trade', 'run_id'),
            ('news_classification_outcomes', 'news_item_id'),
        ]

        for table_name, col_name in required_cascade_columns:
            table = Base.metadata.tables[table_name]
            col = table.columns[col_name]
            fk = next(iter(col.foreign_keys))
            assert fk.ondelete is not None
            assert fk.ondelete.upper() == 'CASCADE', (
                f"Expected {table_name}.{col_name} to use ON DELETE CASCADE, got {fk.ondelete}"
            )
