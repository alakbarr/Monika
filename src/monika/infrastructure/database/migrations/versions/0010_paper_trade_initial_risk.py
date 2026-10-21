"""paper trade initial risk anchor and accounting status

Phase 0 accounting truth.

`paper_trade_records.stop_loss` is mutated by TrailingStopManager and by the
MT5 position synchroniser. Realized R was nevertheless computed against that
mutable value through ``abs(entry - stop_loss)``, so a stop moved past entry
produced a fresh, larger risk denominator and a wildly overstated loss (for
example -2.94% instead of -0.19%).

This revision freezes the entry-time risk anchor in two new columns and adds
an explicit accounting verdict per row. Legacy realized PnL is recomputed
against the recovered anchor while preserving the swap/rounding component
already baked into the stored value:

    new_pnl = risk * move / |entry - initial_stop|
              + (old_pnl - risk * move / |entry - stored_stop|)

Rows whose anchor cannot be recovered are marked 'invalid_initial_stop' so
risk checks fail closed instead of trusting a fabricated number.

Revision ID: 0010_paper_trade_initial_risk
Revises: 0009_price_ohlcv_canonical_ts
Create Date: 2026-10-21 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010_paper_trade_initial_risk"
down_revision: Union[str, Sequence[str], None] = "0009_price_ohlcv_canonical_ts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "paper_trade_records"


def upgrade() -> None:
    """Add the immutable risk anchor and classify existing rows."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if TABLE not in insp.get_table_names():
        return

    existing_columns = {column["name"] for column in insp.get_columns(TABLE)}

    if "initial_stop_loss" not in existing_columns:
        op.add_column(TABLE, sa.Column("initial_stop_loss", sa.Float(), nullable=True))
    if "initial_risk_pct" not in existing_columns:
        op.add_column(TABLE, sa.Column("initial_risk_pct", sa.Float(), nullable=True))
    if "accounting_status" not in existing_columns:
        op.add_column(
            TABLE,
            sa.Column("accounting_status", sa.String(length=30), nullable=False, server_default="ok"),
        )

    # 1. Freeze the risk percentage that was actually recorded at entry.
    op.execute(
        sa.text(
            "UPDATE paper_trade_records SET initial_risk_pct = risk_pct "
            "WHERE initial_risk_pct IS NULL AND risk_pct IS NOT NULL"
        )
    )

    # 2. Recover the entry stop loss from the analysis that produced the trade.
    op.execute(
        sa.text(
            "UPDATE paper_trade_records SET initial_stop_loss = ("
            "SELECT aa.stop_loss FROM asset_analysis AS aa "
            "WHERE aa.id = paper_trade_records.analysis_id"
            ") WHERE initial_stop_loss IS NULL AND analysis_id IS NOT NULL"
        )
    )

    # 3. Recompute legacy realized PnL against the recovered anchor.
    # Done in Python so the arithmetic is identical on SQLite and PostgreSQL
    # (PostgreSQL has no round(double precision, integer)).
    result = bind.execute(
        sa.text(
            f"SELECT id, direction, entry_price, exit_price, stop_loss, "
            f"initial_stop_loss, initial_risk_pct, pnl_pct FROM {TABLE} "
            "WHERE status = 'closed' "
            "AND (exit_reason IS NULL OR exit_reason NOT IN ('expired_limit', 'breakeven'))"
        )
    )
    # The schema-completeness test runs migrations against a mocked bind that
    # returns None; the DDL/backfill still needs to execute there.
    rows = result.mappings().all() if result is not None and hasattr(result, "mappings") else []
    for row in rows:
        entry = row["entry_price"]
        exit_price = row["exit_price"]
        initial_stop = row["initial_stop_loss"]
        risk_pct = row["initial_risk_pct"]
        direction = str(row["direction"] or "").lower()
        if entry is None or exit_price is None or initial_stop is None or risk_pct is None:
            continue
        try:
            entry_f = float(entry)
            exit_f = float(exit_price)
            initial_f = float(initial_stop)
            risk_f = float(risk_pct)
        except TypeError, ValueError:
            continue
        if risk_f <= 0.0 or direction not in ("buy", "sell"):
            continue
        if direction == "buy" and initial_f >= entry_f:
            continue
        if direction == "sell" and initial_f <= entry_f:
            continue
        initial_distance = abs(entry_f - initial_f)
        if initial_distance <= 1e-9:
            continue
        move = exit_f - entry_f if direction == "buy" else entry_f - exit_f
        new_base = risk_f * move / initial_distance

        # Preserve the swap/fee component already baked into the stored value.
        old_pnl = row["pnl_pct"]
        stored_stop = row["stop_loss"]
        legacy_component = 0.0
        if old_pnl is not None and stored_stop is not None:
            stored_distance = abs(entry_f - float(stored_stop))
            if stored_distance > 1e-9:
                legacy_component = float(old_pnl) - (risk_f * move / stored_distance)

        bind.execute(
            sa.text(f"UPDATE {TABLE} SET pnl_pct = :pnl, accounting_status = 'ok' WHERE id = :id"),
            {"pnl": round(new_base + legacy_component, 4), "id": row["id"]},
        )

    # 4. Closed limit orders that never filled never risked capital.
    op.execute(
        sa.text(
            f"UPDATE {TABLE} SET accounting_status = 'not_filled' "
            "WHERE status = 'closed' AND exit_reason = 'expired_limit'"
        )
    )

    # 5. Open rows with a valid anchor can be accounted for when they close.
    op.execute(
        sa.text(
            f"""
            UPDATE {TABLE}
            SET accounting_status = 'ok'
            WHERE status = 'open'
              AND accounting_status = 'ok'
              AND initial_stop_loss IS NOT NULL
              AND initial_risk_pct IS NOT NULL
              AND ((direction = 'buy' AND initial_stop_loss < entry_price)
                   OR (direction = 'sell' AND initial_stop_loss > entry_price))
            """
        )
    )

    # 6. Anything left without a trustworthy anchor must fail closed downstream.
    op.execute(
        sa.text(
            f"""
            UPDATE {TABLE}
            SET accounting_status = 'invalid_initial_stop'
            WHERE status = 'closed'
              AND accounting_status <> 'not_filled'
              AND (
                    initial_risk_pct IS NULL
                 OR initial_risk_pct <= 0
                 OR initial_stop_loss IS NULL
                 OR NOT ((direction = 'buy' AND initial_stop_loss < entry_price)
                         OR (direction = 'sell' AND initial_stop_loss > entry_price))
              )
            """
        )
    )


def downgrade() -> None:
    """Remove the Phase 0 accounting columns."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if TABLE not in insp.get_table_names():
        return

    existing_columns = {column["name"] for column in insp.get_columns(TABLE)}

    # Undo the anchored-PnL rewrite before dropping the anchor. Without this,
    # a downgrade/upgrade roundtrip would feed the already anchored value back
    # into the legacy formula and compound the preserved swap component.
    if {"initial_stop_loss", "initial_risk_pct", "accounting_status"} <= existing_columns:
        result = bind.execute(
            sa.text(
                f"SELECT id, direction, entry_price, exit_price, stop_loss, "
                f"initial_stop_loss, initial_risk_pct, pnl_pct FROM {TABLE} "
                "WHERE status = 'closed' AND accounting_status = 'ok' "
                "AND (exit_reason IS NULL OR exit_reason NOT IN ('expired_limit', 'breakeven'))"
            )
        )
        rows = result.mappings().all() if result is not None and hasattr(result, "mappings") else []
        for row in rows:
            entry = row["entry_price"]
            exit_price = row["exit_price"]
            initial_stop = row["initial_stop_loss"]
            stored_stop = row["stop_loss"]
            risk_pct = row["initial_risk_pct"]
            anchored_pnl = row["pnl_pct"]
            direction = str(row["direction"] or "").lower()
            if (
                entry is None
                or exit_price is None
                or initial_stop is None
                or stored_stop is None
                or risk_pct is None
                or anchored_pnl is None
            ):
                continue
            try:
                entry_f = float(entry)
                exit_f = float(exit_price)
                initial_f = float(initial_stop)
                stored_f = float(stored_stop)
                risk_f = float(risk_pct)
                anchored_f = float(anchored_pnl)
            except TypeError, ValueError:
                continue
            if risk_f <= 0.0 or direction not in ("buy", "sell"):
                continue
            initial_distance = abs(entry_f - initial_f)
            stored_distance = abs(entry_f - stored_f)
            if initial_distance <= 1e-9 or stored_distance <= 1e-9:
                continue
            move = exit_f - entry_f if direction == "buy" else entry_f - exit_f
            legacy_pnl = anchored_f - (risk_f * move / initial_distance) + (risk_f * move / stored_distance)
            bind.execute(
                sa.text(f"UPDATE {TABLE} SET pnl_pct = :pnl WHERE id = :id"),
                {"pnl": round(legacy_pnl, 4), "id": row["id"]},
            )

    with op.batch_alter_table(TABLE) as batch_op:
        if "accounting_status" in existing_columns:
            batch_op.drop_column("accounting_status")
        if "initial_risk_pct" in existing_columns:
            batch_op.drop_column("initial_risk_pct")
        if "initial_stop_loss" in existing_columns:
            batch_op.drop_column("initial_stop_loss")
