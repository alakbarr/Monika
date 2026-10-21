"""Roundtrip test for migration 0010's downgrade PnL restoration."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

pytestmark = pytest.mark.integration

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "monika"
    / "infrastructure"
    / "database"
    / "migrations"
    / "versions"
    / "0010_paper_trade_initial_risk.py"
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migration_0010_roundtrip", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _create_pre_0010_schema(connection: sa.Connection) -> None:
    metadata = sa.MetaData()
    sa.Table(
        "asset_analysis",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("stop_loss", sa.Float),
    )
    sa.Table(
        "paper_trade_records",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("analysis_id", sa.Integer),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("direction", sa.String(10), nullable=False),
        sa.Column("entry_price", sa.Float, nullable=False),
        sa.Column("stop_loss", sa.Float, nullable=False),
        sa.Column("take_profit", sa.Float, nullable=False),
        sa.Column("opened_at", sa.DateTime, nullable=False),
        sa.Column("is_pending_fill", sa.Boolean, nullable=False),
        sa.Column("partially_filled", sa.Boolean, nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("exit_price", sa.Float),
        sa.Column("exit_reason", sa.String(30)),
        sa.Column("risk_pct", sa.Float),
        sa.Column("pnl_pct", sa.Float),
    )
    metadata.create_all(connection)
    connection.execute(sa.text("INSERT INTO asset_analysis (id, stop_loss) VALUES (1, 98.0)"))
    connection.execute(
        sa.text(
            "INSERT INTO paper_trade_records "
            "(id, analysis_id, symbol, direction, entry_price, stop_loss, take_profit, "
            "opened_at, is_pending_fill, partially_filled, status, exit_price, exit_reason, "
            "risk_pct, pnl_pct) "
            "VALUES (1, 1, 'EURUSD', 'buy', 100.0, 101.0, 105.0, "
            "'2026-10-16 10:00:00', 0, 0, 'closed', 99.0, 'trailing_stop', 1.0, -1.05)"
        )
    )


def _row(connection: sa.Connection) -> sa.RowMapping:
    return (
        connection.execute(
            sa.text(
                "SELECT initial_stop_loss, initial_risk_pct, pnl_pct, accounting_status "
                "FROM paper_trade_records WHERE id = 1"
            )
        )
        .mappings()
        .one()
    )


def test_migration_0010_downgrade_restores_legacy_pnl_without_compounding() -> None:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        _create_pre_0010_schema(connection)
        migration = _load_migration()
        migration.op = Operations(MigrationContext.configure(connection))

        migration.upgrade()
        first = _row(connection)
        assert first["initial_stop_loss"] == 98.0
        assert first["initial_risk_pct"] == 1.0
        assert first["pnl_pct"] == pytest.approx(-0.55)
        assert first["accounting_status"] == "ok"

        migration.downgrade()
        columns = {column["name"] for column in sa.inspect(connection).get_columns("paper_trade_records")}
        assert "initial_stop_loss" not in columns
        assert "initial_risk_pct" not in columns
        assert "accounting_status" not in columns
        legacy_pnl = connection.execute(sa.text("SELECT pnl_pct FROM paper_trade_records WHERE id = 1")).scalar_one()
        assert legacy_pnl == pytest.approx(-1.05)

        migration.upgrade()
        second = _row(connection)
        assert second["initial_stop_loss"] == 98.0
        assert second["initial_risk_pct"] == 1.0
        assert second["pnl_pct"] == pytest.approx(-0.55)
        assert second["accounting_status"] == "ok"
