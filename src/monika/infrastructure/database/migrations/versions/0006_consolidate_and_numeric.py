"""consolidate_operational_tables_and_numeric_expansion

Revision ID: 0006_consolidate_and_numeric
Revises: 0005_sync_indexes_constraints
Create Date: 2026-10-13 16:15:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006_consolidate_and_numeric"
down_revision: Union[str, Sequence[str], None] = "0005_sync_indexes_constraints"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: add operational tables and numeric dual-read columns."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())

    def _has_table(tbl: str) -> bool:
        return tbl in existing_tables

    def _has_column(tbl: str, col: str) -> bool:
        if tbl not in existing_tables:
            return False
        return any(c.get("name") == col for c in insp.get_columns(tbl))

    def _has_index(tbl: str, idx_name: str) -> bool:
        if tbl not in existing_tables or not hasattr(insp, "get_indexes"):
            return False
        return any(i.get("name") == idx_name for i in insp.get_indexes(tbl))

    # -------------------------------------------------------------------------
    # 1. Operational Tables Consolidation
    # -------------------------------------------------------------------------

    # 1.1 cron_jobs
    if not _has_table("cron_jobs"):
        op.create_table(
            "cron_jobs",
            sa.Column("job_id", sa.String(length=64), primary_key=True),
            sa.Column("name", sa.String(length=128), server_default=""),
            sa.Column("schedule_expression", sa.String(length=128), nullable=False),
            sa.Column("prompt", sa.Text(), nullable=False),
            sa.Column("target_delivery", sa.String(length=64), nullable=False),
            sa.Column("target_destination", sa.String(length=128), nullable=True),
            sa.Column("workdir", sa.String(length=255), nullable=True),
            sa.Column("monitor_script", sa.Text(), nullable=True),
            sa.Column("last_monitor_hash", sa.String(length=64), nullable=True),
            sa.Column("next_run_at", sa.Float(), nullable=False),
            sa.Column("last_run_at", sa.Float(), nullable=True),
            sa.Column("last_exit_code", sa.Integer(), nullable=True),
            sa.Column("last_output", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Integer(), server_default="1"),
            sa.Column("no_agent", sa.Integer(), server_default="0"),
            sa.Column("pending_slot", sa.Integer(), server_default="0"),
            sa.Column("timeout_seconds", sa.Float(), server_default="300.0"),
            sa.Column("metadata_json", sa.Text(), nullable=True),
        )
        op.create_index("ix_cron_jobs_next_run_at", "cron_jobs", ["next_run_at"])
        op.create_index("ix_cron_jobs_is_active", "cron_jobs", ["is_active"])

    # 1.2 outbox_deliveries
    if not _has_table("outbox_deliveries"):
        op.create_table(
            "outbox_deliveries",
            sa.Column("delivery_id", sa.String(length=64), primary_key=True),
            sa.Column("job_id", sa.String(length=64), nullable=False),
            sa.Column("channel", sa.String(length=64), nullable=False),
            sa.Column("destination", sa.String(length=128), nullable=True),
            sa.Column("payload", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=32), server_default="pending"),
            sa.Column("lease_expires_at", sa.Float(), server_default="0.0"),
            sa.Column("created_at", sa.Float(), nullable=False),
            sa.Column("updated_at", sa.Float(), nullable=False),
            sa.Column("retry_count", sa.Integer(), server_default="0"),
            sa.Column("error_message", sa.Text(), nullable=True),
        )
        op.create_index("ix_outbox_deliveries_job_id", "outbox_deliveries", ["job_id"])
        op.create_index("ix_outbox_deliveries_status", "outbox_deliveries", ["status"])
        op.create_index("idx_outbox_status_lease", "outbox_deliveries", ["status", "lease_expires_at"])

    # 1.3 delivery_records
    if not _has_table("delivery_records"):
        op.create_table(
            "delivery_records",
            sa.Column("idempotency_key", sa.String(length=128), primary_key=True),
            sa.Column("platform", sa.String(length=32), nullable=False),
            sa.Column("recipient_id", sa.String(length=128), nullable=False),
            sa.Column("payload_hash", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("attempts", sa.Integer(), server_default="0"),
            sa.Column("max_attempts", sa.Integer(), server_default="3"),
            sa.Column("created_at", sa.Float(), nullable=False),
            sa.Column("updated_at", sa.Float(), nullable=False),
            sa.Column("delivered_at", sa.Float(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("payload_json", sa.Text(), nullable=True),
            sa.Column("flood_not_before", sa.Float(), server_default="0.0"),
        )
        op.create_index("idx_delivery_status", "delivery_records", ["status"])
        op.create_index("idx_delivery_flood", "delivery_records", ["flood_not_before"])

    # 1.4 session_tool_records
    if not _has_table("session_tool_records"):
        op.create_table(
            "session_tool_records",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("session_id", sa.String(length=64), nullable=False),
            sa.Column("turn_ordinal", sa.Integer(), nullable=False),
            sa.Column("tool_name", sa.String(length=64), nullable=False),
            sa.Column("arguments_json", sa.Text(), nullable=True),
            sa.Column("output_text", sa.Text(), nullable=True),
            sa.Column("is_error", sa.Integer(), server_default="0"),
            sa.Column("has_side_effects", sa.Integer(), server_default="0"),
            sa.Column("created_at", sa.Float(), nullable=False),
        )
        op.create_index("ix_session_tool_records_session_id", "session_tool_records", ["session_id"])
        op.create_index("idx_str_lookup", "session_tool_records", ["session_id", "turn_ordinal"])

    # 1.5 repair_ledger
    if not _has_table("repair_ledger"):
        op.create_table(
            "repair_ledger",
            sa.Column("repair_id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("session_id", sa.String(length=64), nullable=True),
            sa.Column("issue_type", sa.String(length=64), nullable=False),
            sa.Column("action_taken", sa.String(length=128), nullable=False),
            sa.Column("status", sa.String(length=32), server_default="RESOLVED"),
            sa.Column("details_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.Float(), nullable=False),
        )
        op.create_index("idx_repair_session", "repair_ledger", ["session_id"])

    # 1.6 scheduled_jobs & job_deliveries
    if not _has_table("scheduled_jobs"):
        op.create_table(
            "scheduled_jobs",
            sa.Column("job_id", sa.String(length=64), primary_key=True),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("schedule_expr", sa.String(length=128), nullable=True),
            sa.Column("interval_seconds", sa.Float(), nullable=True),
            sa.Column("handler_name", sa.String(length=64), nullable=False),
            sa.Column("payload_json", sa.Text(), nullable=True),
            sa.Column("target_platform", sa.String(length=32), nullable=True),
            sa.Column("target_channel", sa.String(length=128), nullable=True),
            sa.Column("last_run", sa.Float(), nullable=True),
            sa.Column("next_run", sa.Float(), nullable=True),
            sa.Column("is_active", sa.Integer(), server_default="1"),
            sa.Column("created_at", sa.Float(), nullable=False),
        )

    if not _has_table("job_deliveries"):
        op.create_table(
            "job_deliveries",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "job_id",
                sa.String(length=64),
                sa.ForeignKey("scheduled_jobs.job_id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("output_text", sa.Text(), nullable=True),
            sa.Column("delivered_at", sa.Float(), nullable=False),
        )
        op.create_index("ix_job_deliveries_job_id", "job_deliveries", ["job_id"])

    # -------------------------------------------------------------------------
    # 2. Numeric Expanded Columns (D4: Expand Phase)
    # -------------------------------------------------------------------------

    # 2.1 trades
    if _has_table("trades"):
        with op.batch_alter_table("trades") as batch_op:
            if not _has_column("trades", "entry_price_num"):
                batch_op.add_column(sa.Column("entry_price_num", sa.Numeric(18, 8), nullable=True))
            if not _has_column("trades", "take_profit_num"):
                batch_op.add_column(sa.Column("take_profit_num", sa.Numeric(18, 8), nullable=True))
            if not _has_column("trades", "stop_loss_num"):
                batch_op.add_column(sa.Column("stop_loss_num", sa.Numeric(18, 8), nullable=True))
            if not _has_column("trades", "volume_num"):
                batch_op.add_column(sa.Column("volume_num", sa.Numeric(12, 4), nullable=True))
            if not _has_column("trades", "pnl_num"):
                batch_op.add_column(sa.Column("pnl_num", sa.Numeric(18, 4), nullable=True))

    # 2.2 price_ohlcv
    if _has_table("price_ohlcv"):
        with op.batch_alter_table("price_ohlcv") as batch_op:
            if not _has_column("price_ohlcv", "open_num"):
                batch_op.add_column(sa.Column("open_num", sa.Numeric(18, 8), nullable=True))
            if not _has_column("price_ohlcv", "high_num"):
                batch_op.add_column(sa.Column("high_num", sa.Numeric(18, 8), nullable=True))
            if not _has_column("price_ohlcv", "low_num"):
                batch_op.add_column(sa.Column("low_num", sa.Numeric(18, 8), nullable=True))
            if not _has_column("price_ohlcv", "close_num"):
                batch_op.add_column(sa.Column("close_num", sa.Numeric(18, 8), nullable=True))
            if not _has_column("price_ohlcv", "volume_num"):
                batch_op.add_column(sa.Column("volume_num", sa.Numeric(18, 4), nullable=True))

    # 2.3 asset_analysis
    if _has_table("asset_analysis"):
        with op.batch_alter_table("asset_analysis") as batch_op:
            if not _has_column("asset_analysis", "confidence_num"):
                batch_op.add_column(sa.Column("confidence_num", sa.Numeric(8, 4), nullable=True))
            if not _has_column("asset_analysis", "stop_loss_num"):
                batch_op.add_column(sa.Column("stop_loss_num", sa.Numeric(18, 8), nullable=True))
            if not _has_column("asset_analysis", "take_profit_num"):
                batch_op.add_column(sa.Column("take_profit_num", sa.Numeric(18, 8), nullable=True))
            if not _has_column("asset_analysis", "invalidation_price_num"):
                batch_op.add_column(sa.Column("invalidation_price_num", sa.Numeric(18, 8), nullable=True))
            if not _has_column("asset_analysis", "risk_multiplier_num"):
                batch_op.add_column(sa.Column("risk_multiplier_num", sa.Numeric(8, 4), nullable=True))

    # 2.4 orders
    if _has_table("orders"):
        with op.batch_alter_table("orders") as batch_op:
            if not _has_column("orders", "requested_price_num"):
                batch_op.add_column(sa.Column("requested_price_num", sa.Numeric(18, 8), nullable=True))
            if not _has_column("orders", "executed_price_num"):
                batch_op.add_column(sa.Column("executed_price_num", sa.Numeric(18, 8), nullable=True))
            if not _has_column("orders", "slippage_pips_num"):
                batch_op.add_column(sa.Column("slippage_pips_num", sa.Numeric(10, 4), nullable=True))
            if not _has_column("orders", "requested_volume_num"):
                batch_op.add_column(sa.Column("requested_volume_num", sa.Numeric(12, 4), nullable=True))
            if not _has_column("orders", "filled_volume_num"):
                batch_op.add_column(sa.Column("filled_volume_num", sa.Numeric(12, 4), nullable=True))

    # 2.5 positions
    if _has_table("positions"):
        with op.batch_alter_table("positions") as batch_op:
            if not _has_column("positions", "volume_num"):
                batch_op.add_column(sa.Column("volume_num", sa.Numeric(12, 4), nullable=True))
            if not _has_column("positions", "initial_volume_num"):
                batch_op.add_column(sa.Column("initial_volume_num", sa.Numeric(12, 4), nullable=True))
            if not _has_column("positions", "entry_price_num"):
                batch_op.add_column(sa.Column("entry_price_num", sa.Numeric(18, 8), nullable=True))
            if not _has_column("positions", "sl_num"):
                batch_op.add_column(sa.Column("sl_num", sa.Numeric(18, 8), nullable=True))
            if not _has_column("positions", "tp_num"):
                batch_op.add_column(sa.Column("tp_num", sa.Numeric(18, 8), nullable=True))
            if not _has_column("positions", "pnl_num"):
                batch_op.add_column(sa.Column("pnl_num", sa.Numeric(18, 4), nullable=True))
            if not _has_column("positions", "slippage_pips_num"):
                batch_op.add_column(sa.Column("slippage_pips_num", sa.Numeric(10, 4), nullable=True))

    # 2.6 paper_trade_records
    if _has_table("paper_trade_records"):
        with op.batch_alter_table("paper_trade_records") as batch_op:
            if not _has_column("paper_trade_records", "entry_price_num"):
                batch_op.add_column(sa.Column("entry_price_num", sa.Numeric(18, 8), nullable=True))
            if not _has_column("paper_trade_records", "stop_loss_num"):
                batch_op.add_column(sa.Column("stop_loss_num", sa.Numeric(18, 8), nullable=True))
            if not _has_column("paper_trade_records", "take_profit_num"):
                batch_op.add_column(sa.Column("take_profit_num", sa.Numeric(18, 8), nullable=True))
            if not _has_column("paper_trade_records", "exit_price_num"):
                batch_op.add_column(sa.Column("exit_price_num", sa.Numeric(18, 8), nullable=True))
            if not _has_column("paper_trade_records", "risk_pct_num"):
                batch_op.add_column(sa.Column("risk_pct_num", sa.Numeric(8, 4), nullable=True))
            if not _has_column("paper_trade_records", "pnl_pct_num"):
                batch_op.add_column(sa.Column("pnl_pct_num", sa.Numeric(8, 4), nullable=True))
            if not _has_column("paper_trade_records", "requested_lot_num"):
                batch_op.add_column(sa.Column("requested_lot_num", sa.Numeric(12, 4), nullable=True))

    # 2.7 equity_drawdown_snapshots
    if _has_table("equity_drawdown_snapshots"):
        with op.batch_alter_table("equity_drawdown_snapshots") as batch_op:
            if not _has_column("equity_drawdown_snapshots", "balance_num"):
                batch_op.add_column(sa.Column("balance_num", sa.Numeric(18, 4), nullable=True))
            if not _has_column("equity_drawdown_snapshots", "equity_num"):
                batch_op.add_column(sa.Column("equity_num", sa.Numeric(18, 4), nullable=True))
            if not _has_column("equity_drawdown_snapshots", "floating_pnl_num"):
                batch_op.add_column(sa.Column("floating_pnl_num", sa.Numeric(18, 4), nullable=True))
            if not _has_column("equity_drawdown_snapshots", "drawdown_usd_num"):
                batch_op.add_column(sa.Column("drawdown_usd_num", sa.Numeric(18, 4), nullable=True))
            if not _has_column("equity_drawdown_snapshots", "drawdown_pct_num"):
                batch_op.add_column(sa.Column("drawdown_pct_num", sa.Numeric(8, 4), nullable=True))
            if not _has_column("equity_drawdown_snapshots", "peak_equity_num"):
                batch_op.add_column(sa.Column("peak_equity_num", sa.Numeric(18, 4), nullable=True))

    # 2.8 risk_state
    if _has_table("risk_state"):
        with op.batch_alter_table("risk_state") as batch_op:
            if not _has_column("risk_state", "daily_pnl_num"):
                batch_op.add_column(sa.Column("daily_pnl_num", sa.Numeric(18, 4), nullable=True))
            if not _has_column("risk_state", "current_drawdown_num"):
                batch_op.add_column(sa.Column("current_drawdown_num", sa.Numeric(8, 4), nullable=True))

    # -------------------------------------------------------------------------
    # 3. Data Backfill (Dual-Read Synchronization)
    # -------------------------------------------------------------------------
    dialect = bind.dialect.name
    if dialect in ("postgresql", "sqlite"):
        try:
            if _has_table("trades"):
                op.execute(
                    "UPDATE trades SET "
                    "entry_price_num = CAST(entry_price AS NUMERIC), "
                    "take_profit_num = CAST(take_profit AS NUMERIC), "
                    "stop_loss_num = CAST(stop_loss AS NUMERIC), "
                    "volume_num = CAST(volume AS NUMERIC), "
                    "pnl_num = CAST(pnl AS NUMERIC) "
                    "WHERE entry_price_num IS NULL;"
                )
            if _has_table("positions"):
                op.execute(
                    "UPDATE positions SET "
                    "volume_num = CAST(volume AS NUMERIC), "
                    "entry_price_num = CAST(entry_price AS NUMERIC), "
                    "sl_num = CAST(sl AS NUMERIC), "
                    "tp_num = CAST(tp AS NUMERIC), "
                    "pnl_num = CAST(pnl AS NUMERIC) "
                    "WHERE volume_num IS NULL;"
                )
            if _has_table("orders"):
                op.execute(
                    "UPDATE orders SET "
                    "requested_price_num = CAST(requested_price AS NUMERIC), "
                    "requested_volume_num = CAST(requested_volume AS NUMERIC) "
                    "WHERE requested_price_num IS NULL;"
                )
        except Exception:
            pass  # Backfill is best-effort in migration; completed by offline backfill script


def downgrade() -> None:
    """Downgrade schema: remove numeric expanded columns and operational tables."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())

    def _has_table(tbl: str) -> bool:
        return tbl in existing_tables

    def _has_column(tbl: str, col: str) -> bool:
        if tbl not in existing_tables:
            return False
        return any(c.get("name") == col for c in insp.get_columns(tbl))

    # 1. Drop numeric expanded columns
    if _has_table("risk_state"):
        with op.batch_alter_table("risk_state") as batch_op:
            for col in ("daily_pnl_num", "current_drawdown_num"):
                if _has_column("risk_state", col):
                    batch_op.drop_column(col)

    if _has_table("equity_drawdown_snapshots"):
        with op.batch_alter_table("equity_drawdown_snapshots") as batch_op:
            for col in (
                "balance_num",
                "equity_num",
                "floating_pnl_num",
                "drawdown_usd_num",
                "drawdown_pct_num",
                "peak_equity_num",
            ):
                if _has_column("equity_drawdown_snapshots", col):
                    batch_op.drop_column(col)

    if _has_table("paper_trade_records"):
        with op.batch_alter_table("paper_trade_records") as batch_op:
            for col in (
                "entry_price_num",
                "stop_loss_num",
                "take_profit_num",
                "exit_price_num",
                "risk_pct_num",
                "pnl_pct_num",
                "requested_lot_num",
            ):
                if _has_column("paper_trade_records", col):
                    batch_op.drop_column(col)

    if _has_table("positions"):
        with op.batch_alter_table("positions") as batch_op:
            for col in (
                "volume_num",
                "initial_volume_num",
                "entry_price_num",
                "sl_num",
                "tp_num",
                "pnl_num",
                "slippage_pips_num",
            ):
                if _has_column("positions", col):
                    batch_op.drop_column(col)

    if _has_table("orders"):
        with op.batch_alter_table("orders") as batch_op:
            for col in (
                "requested_price_num",
                "executed_price_num",
                "slippage_pips_num",
                "requested_volume_num",
                "filled_volume_num",
            ):
                if _has_column("orders", col):
                    batch_op.drop_column(col)

    if _has_table("asset_analysis"):
        with op.batch_alter_table("asset_analysis") as batch_op:
            for col in (
                "confidence_num",
                "stop_loss_num",
                "take_profit_num",
                "invalidation_price_num",
                "risk_multiplier_num",
            ):
                if _has_column("asset_analysis", col):
                    batch_op.drop_column(col)

    if _has_table("price_ohlcv"):
        with op.batch_alter_table("price_ohlcv") as batch_op:
            for col in ("open_num", "high_num", "low_num", "close_num", "volume_num"):
                if _has_column("price_ohlcv", col):
                    batch_op.drop_column(col)

    if _has_table("trades"):
        with op.batch_alter_table("trades") as batch_op:
            for col in ("entry_price_num", "take_profit_num", "stop_loss_num", "volume_num", "pnl_num"):
                if _has_column("trades", col):
                    batch_op.drop_column(col)

    # 2. Drop operational tables
    if _has_table("job_deliveries"):
        op.drop_table("job_deliveries")
    if _has_table("scheduled_jobs"):
        op.drop_table("scheduled_jobs")
    if _has_table("repair_ledger"):
        op.drop_table("repair_ledger")
    if _has_table("session_tool_records"):
        op.drop_table("session_tool_records")
    if _has_table("delivery_records"):
        op.drop_table("delivery_records")
    if _has_table("outbox_deliveries"):
        op.drop_table("outbox_deliveries")
    if _has_table("cron_jobs"):
        op.drop_table("cron_jobs")
