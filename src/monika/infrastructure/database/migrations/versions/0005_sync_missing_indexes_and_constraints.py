"""sync_missing_indexes_and_constraints

Revision ID: 0005_sync_indexes_constraints
Revises: 0004_fk_cascade_integrity
Create Date: 2026-10-12 08:48:15.323502

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0005_sync_indexes_constraints"
down_revision: Union[str, Sequence[str], None] = "0004_fk_cascade_integrity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())

    def _has_index(tbl: str, idx_name: str) -> bool:
        if tbl not in existing_tables or not hasattr(insp, "get_indexes"):
            return False
        return any(i.get("name") == idx_name for i in insp.get_indexes(tbl))

    if not _has_index("asset_analysis", "ix_asset_analysis_brief_id"):
        op.create_index(op.f("ix_asset_analysis_brief_id"), "asset_analysis", ["brief_id"], unique=False)
    if not _has_index("backtest_trade", "ix_backtest_trade_run_id"):
        op.create_index(op.f("ix_backtest_trade_run_id"), "backtest_trade", ["run_id"], unique=False)
    if not _has_index("central_bank_documents", "idx_cb_doc_bank_type_date"):
        op.create_index(
            "idx_cb_doc_bank_type_date", "central_bank_documents", ["bank", "doc_type", "meeting_date"], unique=False
        )
    if not _has_index("central_bank_documents", "ix_central_bank_documents_bank"):
        op.create_index(op.f("ix_central_bank_documents_bank"), "central_bank_documents", ["bank"], unique=False)
    if not _has_index("central_bank_documents", "ix_central_bank_documents_doc_type"):
        op.create_index(
            op.f("ix_central_bank_documents_doc_type"), "central_bank_documents", ["doc_type"], unique=False
        )
    if not _has_index("central_bank_documents", "ix_central_bank_documents_meeting_date"):
        op.create_index(
            op.f("ix_central_bank_documents_meeting_date"), "central_bank_documents", ["meeting_date"], unique=False
        )
    if not _has_index("confluence_factor_outcomes", "ix_confluence_factor_outcomes_analysis_id"):
        op.create_index(
            op.f("ix_confluence_factor_outcomes_analysis_id"),
            "confluence_factor_outcomes",
            ["analysis_id"],
            unique=False,
        )
    if not _has_index("confluence_factor_outcomes", "ix_confluence_factor_outcomes_paper_trade_id"):
        op.create_index(
            op.f("ix_confluence_factor_outcomes_paper_trade_id"),
            "confluence_factor_outcomes",
            ["paper_trade_id"],
            unique=False,
        )
    if not _has_index("decision_reflections", "ix_decision_reflections_analysis_id"):
        op.create_index(
            op.f("ix_decision_reflections_analysis_id"), "decision_reflections", ["analysis_id"], unique=False
        )
    if not _has_index("economic_report_decompositions", "idx_report_lookup"):
        op.create_index(
            "idx_report_lookup", "economic_report_decompositions", ["report_type", "currency", "period"], unique=False
        )
    if not _has_index("economic_report_decompositions", "ix_economic_report_decompositions_country"):
        op.create_index(
            op.f("ix_economic_report_decompositions_country"),
            "economic_report_decompositions",
            ["country"],
            unique=False,
        )
    if not _has_index("economic_report_decompositions", "ix_economic_report_decompositions_currency"):
        op.create_index(
            op.f("ix_economic_report_decompositions_currency"),
            "economic_report_decompositions",
            ["currency"],
            unique=False,
        )
    if not _has_index("economic_report_decompositions", "ix_economic_report_decompositions_period"):
        op.create_index(
            op.f("ix_economic_report_decompositions_period"), "economic_report_decompositions", ["period"], unique=False
        )
    if not _has_index("economic_report_decompositions", "ix_economic_report_decompositions_release_date"):
        op.create_index(
            op.f("ix_economic_report_decompositions_release_date"),
            "economic_report_decompositions",
            ["release_date"],
            unique=False,
        )
    if not _has_index("economic_report_decompositions", "ix_economic_report_decompositions_report_type"):
        op.create_index(
            op.f("ix_economic_report_decompositions_report_type"),
            "economic_report_decompositions",
            ["report_type"],
            unique=False,
        )

    if "llm_benchmark_result" in existing_tables:
        with op.batch_alter_table("llm_benchmark_result") as batch_op:
            batch_op.alter_column(
                "cached_tokens", existing_type=sa.INTEGER(), nullable=False, existing_server_default=sa.text("'0'")
            )
            batch_op.alter_column(
                "cost_usd_no_cache", existing_type=sa.FLOAT(), nullable=False, existing_server_default=sa.text("'0.0'")
            )
            batch_op.alter_column(
                "cost_usd_with_cache",
                existing_type=sa.FLOAT(),
                nullable=False,
                existing_server_default=sa.text("'0.0'"),
            )
            batch_op.alter_column(
                "thinking_tokens", existing_type=sa.INTEGER(), nullable=False, existing_server_default=sa.text("'0'")
            )
            batch_op.alter_column(
                "provider_route",
                existing_type=sa.VARCHAR(length=80),
                nullable=False,
                existing_server_default=sa.text("'direct'"),
            )

    if not _has_index("macro_liquidity_credit_metrics", "idx_liq_lookup"):
        op.create_index(
            "idx_liq_lookup", "macro_liquidity_credit_metrics", ["metric_type", "record_date"], unique=False
        )
    if not _has_index("macro_liquidity_credit_metrics", "ix_macro_liquidity_credit_metrics_country"):
        op.create_index(
            op.f("ix_macro_liquidity_credit_metrics_country"),
            "macro_liquidity_credit_metrics",
            ["country"],
            unique=False,
        )
    if not _has_index("macro_liquidity_credit_metrics", "ix_macro_liquidity_credit_metrics_metric_type"):
        op.create_index(
            op.f("ix_macro_liquidity_credit_metrics_metric_type"),
            "macro_liquidity_credit_metrics",
            ["metric_type"],
            unique=False,
        )
    if not _has_index("macro_liquidity_credit_metrics", "ix_macro_liquidity_credit_metrics_record_date"):
        op.create_index(
            op.f("ix_macro_liquidity_credit_metrics_record_date"),
            "macro_liquidity_credit_metrics",
            ["record_date"],
            unique=False,
        )
    if not _has_index("orders_log", "ix_orders_log_timestamp"):
        op.create_index(op.f("ix_orders_log_timestamp"), "orders_log", ["timestamp"], unique=False)
    if not _has_index("token_usage_log", "idx_token_usage_ts_subsys"):
        op.create_index("idx_token_usage_ts_subsys", "token_usage_log", ["timestamp", "subsystem"], unique=False)
    if not _has_index("trade_plan_legs", "ix_trade_plan_legs_position_id"):
        op.create_index(op.f("ix_trade_plan_legs_position_id"), "trade_plan_legs", ["position_id"], unique=False)
    if not _has_index("trading_events", "ix_trading_events_causation_id"):
        op.create_index(op.f("ix_trading_events_causation_id"), "trading_events", ["causation_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_trading_events_causation_id"), table_name="trading_events")
    op.drop_index(op.f("ix_trade_plan_legs_position_id"), table_name="trade_plan_legs")
    op.drop_index("idx_token_usage_ts_subsys", table_name="token_usage_log")
    op.drop_index(op.f("ix_orders_log_timestamp"), table_name="orders_log")
    op.drop_index(op.f("ix_macro_liquidity_credit_metrics_record_date"), table_name="macro_liquidity_credit_metrics")
    op.drop_index(op.f("ix_macro_liquidity_credit_metrics_metric_type"), table_name="macro_liquidity_credit_metrics")
    op.drop_index(op.f("ix_macro_liquidity_credit_metrics_country"), table_name="macro_liquidity_credit_metrics")
    op.drop_index("idx_liq_lookup", table_name="macro_liquidity_credit_metrics")

    with op.batch_alter_table("llm_benchmark_result") as batch_op:
        batch_op.alter_column(
            "provider_route",
            existing_type=sa.VARCHAR(length=80),
            nullable=True,
            existing_server_default=sa.text("'direct'"),
        )
        batch_op.alter_column(
            "thinking_tokens", existing_type=sa.INTEGER(), nullable=True, existing_server_default=sa.text("'0'")
        )
        batch_op.alter_column(
            "cost_usd_with_cache", existing_type=sa.FLOAT(), nullable=True, existing_server_default=sa.text("'0.0'")
        )
        batch_op.alter_column(
            "cost_usd_no_cache", existing_type=sa.FLOAT(), nullable=True, existing_server_default=sa.text("'0.0'")
        )
        batch_op.alter_column(
            "cached_tokens", existing_type=sa.INTEGER(), nullable=True, existing_server_default=sa.text("'0'")
        )

    op.drop_index(op.f("ix_economic_report_decompositions_report_type"), table_name="economic_report_decompositions")
    op.drop_index(op.f("ix_economic_report_decompositions_release_date"), table_name="economic_report_decompositions")
    op.drop_index(op.f("ix_economic_report_decompositions_period"), table_name="economic_report_decompositions")
    op.drop_index(op.f("ix_economic_report_decompositions_currency"), table_name="economic_report_decompositions")
    op.drop_index(op.f("ix_economic_report_decompositions_country"), table_name="economic_report_decompositions")
    op.drop_index("idx_report_lookup", table_name="economic_report_decompositions")
    op.drop_index(op.f("ix_decision_reflections_analysis_id"), table_name="decision_reflections")
    op.drop_index(op.f("ix_confluence_factor_outcomes_paper_trade_id"), table_name="confluence_factor_outcomes")
    op.drop_index(op.f("ix_confluence_factor_outcomes_analysis_id"), table_name="confluence_factor_outcomes")
    op.drop_index(op.f("ix_central_bank_documents_meeting_date"), table_name="central_bank_documents")
    op.drop_index(op.f("ix_central_bank_documents_doc_type"), table_name="central_bank_documents")
    op.drop_index(op.f("ix_central_bank_documents_bank"), table_name="central_bank_documents")
    op.drop_index("idx_cb_doc_bank_type_date", table_name="central_bank_documents")
    op.drop_index(op.f("ix_backtest_trade_run_id"), table_name="backtest_trade")
    op.drop_index(op.f("ix_asset_analysis_brief_id"), table_name="asset_analysis")
