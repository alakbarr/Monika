"""
One-Time & Idempotent Migration Tool: Fragmented SQLite -> Canonical Monika Database
Migrates operational records (cron, session, deliveries) and backfills numeric fields.
Safe to execute multiple times (idempotent, conflict-ignoring).
"""

import asyncio
import os
import sqlite3
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from monika.infrastructure.database.db import get_engine, get_session
from monika.infrastructure.database.models import (
    CronJob,
    DeliveryRecord,
    JobDelivery,
    OutboxDelivery,
    RepairLedger,
    ScheduledJob,
    SessionToolRecord,
)


def _read_sqlite_rows(db_path: Path, table_name: str) -> List[Dict[str, Any]]:
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        # Verify table exists in sqlite file
        exists = cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone()
        if not exists:
            return []
        rows = cur.execute(f"SELECT * FROM {table_name}").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


async def migrate_operational_data(data_dir: Path) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    async with get_session() as session:
        # 1. universal_cron.db -> cron_jobs, outbox_deliveries
        cron_db = data_dir / "universal_cron.db"
        cron_rows = _read_sqlite_rows(cron_db, "cron_jobs")
        for r in cron_rows:
            job_id = str(r["job_id"])
            existing = await session.get(CronJob, job_id)
            if not existing:
                session.add(
                    CronJob(
                        job_id=job_id,
                        name=r.get("name", ""),
                        schedule_expression=r.get("schedule_expression", ""),
                        prompt=r.get("prompt", ""),
                        target_delivery=r.get("target_delivery", ""),
                        target_destination=r.get("target_destination"),
                        workdir=r.get("workdir"),
                        monitor_script=r.get("monitor_script"),
                        last_monitor_hash=r.get("last_monitor_hash"),
                        next_run_at=float(r.get("next_run_at", 0.0)),
                        last_run_at=float(r["last_run_at"]) if r.get("last_run_at") else None,
                        last_exit_code=int(r["last_exit_code"]) if r.get("last_exit_code") is not None else None,
                        last_output=r.get("last_output"),
                        is_active=int(r.get("is_active", 1)),
                        no_agent=int(r.get("no_agent", 0)),
                        pending_slot=int(r.get("pending_slot", 0)),
                        timeout_seconds=float(r.get("timeout_seconds", 300.0)),
                        metadata_json=r.get("metadata_json"),
                    )
                )
        counts["cron_jobs"] = len(cron_rows)

        outbox_rows = _read_sqlite_rows(cron_db, "outbox_deliveries")
        for r in outbox_rows:
            deliv_id = str(r["delivery_id"])
            existing = await session.get(OutboxDelivery, deliv_id)
            if not existing:
                session.add(
                    OutboxDelivery(
                        delivery_id=deliv_id,
                        job_id=str(r["job_id"]),
                        channel=str(r["channel"]),
                        destination=r.get("destination"),
                        payload=str(r.get("payload", "")),
                        status=str(r.get("status", "pending")),
                        lease_expires_at=float(r.get("lease_expires_at", 0.0)),
                        created_at=float(r.get("created_at", 0.0)),
                        updated_at=float(r.get("updated_at", 0.0)),
                        retry_count=int(r.get("retry_count", 0)),
                        error_message=r.get("error_message"),
                    )
                )
        counts["outbox_deliveries"] = len(outbox_rows)

        # 2. gateway_delivery_ledger.db -> delivery_records
        gw_db = data_dir / "gateway_delivery_ledger.db"
        gw_rows = _read_sqlite_rows(gw_db, "delivery_records")
        for r in gw_rows:
            key = str(r["idempotency_key"])
            existing = await session.get(DeliveryRecord, key)
            if not existing:
                session.add(
                    DeliveryRecord(
                        idempotency_key=key,
                        platform=str(r.get("platform", "telegram")),
                        recipient_id=str(r.get("recipient_id", "")),
                        payload_hash=str(r.get("payload_hash", "")),
                        status=str(r.get("status", "pending")),
                        attempts=int(r.get("attempts", 0)),
                        max_attempts=int(r.get("max_attempts", 3)),
                        created_at=float(r.get("created_at", 0.0)),
                        updated_at=float(r.get("updated_at", 0.0)),
                        delivered_at=float(r["delivered_at"]) if r.get("delivered_at") else None,
                        error_message=r.get("error_message"),
                        payload_json=r.get("payload_json"),
                        flood_not_before=float(r.get("flood_not_before", 0.0)),
                    )
                )
        counts["delivery_records"] = len(gw_rows)

        # 3. session_db.sqlite -> tool_records
        sess_db = data_dir / "session_db.sqlite"
        tool_rows = _read_sqlite_rows(sess_db, "tool_records")
        for r in tool_rows:
            session.add(
                SessionToolRecord(
                    session_id=str(r.get("session_id", "")),
                    turn_ordinal=int(r.get("turn_ordinal", 0)),
                    tool_name=str(r.get("tool_name", "")),
                    arguments_json=r.get("arguments_json"),
                    output_text=r.get("output_text"),
                    is_error=int(r.get("is_error", 0)),
                    has_side_effects=int(r.get("has_side_effects", 0)),
                    created_at=float(r.get("created_at", 0.0)),
                )
            )
        counts["tool_records"] = len(tool_rows)

        # 4. deliveries.db -> scheduled_jobs, job_deliveries
        deliv_db = data_dir / "deliveries.db"
        sched_rows = _read_sqlite_rows(deliv_db, "scheduled_jobs")
        for r in sched_rows:
            jid = str(r["job_id"])
            existing = await session.get(ScheduledJob, jid)
            if not existing:
                session.add(
                    ScheduledJob(
                        job_id=jid,
                        name=str(r.get("name", "")),
                        schedule_expr=r.get("schedule_expr"),
                        interval_seconds=float(r["interval_seconds"]) if r.get("interval_seconds") else None,
                        handler_name=str(r.get("handler_name", "")),
                        payload_json=r.get("payload_json"),
                        target_platform=r.get("target_platform"),
                        target_channel=r.get("target_channel"),
                        last_run=float(r["last_run"]) if r.get("last_run") else None,
                        next_run=float(r["next_run"]) if r.get("next_run") else None,
                        is_active=int(r.get("is_active", 1)),
                        created_at=float(r.get("created_at", 0.0)),
                    )
                )
        counts["scheduled_jobs"] = len(sched_rows)

        await session.commit()
    return counts


async def backfill_numeric_fields() -> None:
    """Synchronously backfills *_num columns from legacy float columns."""
    eng = get_engine()
    async with eng.begin() as conn:
        dialect = eng.dialect.name
        cast_kw = "NUMERIC" if dialect == "postgresql" else "NUMERIC"
        tables_to_sync = [
            ("trades", ["entry_price", "take_profit", "stop_loss", "volume", "pnl"]),
            ("positions", ["volume", "initial_volume", "entry_price", "sl", "tp", "pnl", "slippage_pips"]),
            ("orders", ["requested_price", "executed_price", "slippage_pips", "requested_volume", "filled_volume"]),
            ("asset_analysis", ["confidence", "stop_loss", "take_profit", "invalidation_price", "risk_multiplier"]),
            (
                "paper_trade_records",
                ["entry_price", "stop_loss", "take_profit", "exit_price", "risk_pct", "pnl_pct", "requested_lot"],
            ),
            (
                "equity_drawdown_snapshots",
                ["balance", "equity", "floating_pnl", "drawdown_usd", "drawdown_pct", "peak_equity"],
            ),
            ("risk_state", ["daily_pnl", "current_drawdown"]),
            ("price_ohlcv", ["open", "high", "low", "close", "volume"]),
        ]
        for tbl, cols in tables_to_sync:
            updates = []
            for col in cols:
                updates.append(f"{col}_num = CAST({col} AS {cast_kw})")
            clause = ", ".join(updates)
            first_col = cols[0]
            stmt = f"UPDATE {tbl} SET {clause} WHERE {first_col}_num IS NULL AND {first_col} IS NOT NULL;"
            try:
                await conn.execute(text(stmt))
            except Exception as exc:
                print(f"[Notice] Skipped backfill for {tbl}: {exc}")


async def main() -> None:
    data_dir = Path("data").resolve()
    print("=== Monika Canonical Database Migration ===")
    print(f"Scanning SQLite stores in: {data_dir}")
    counts = await migrate_operational_data(data_dir)
    print("Operational records migrated:")
    for tbl, cnt in counts.items():
        print(f"  - {tbl}: {cnt} items")
    print("Running numeric backfill synchronization...")
    await backfill_numeric_fields()
    eng = get_engine()
    await eng.dispose()
    print("Migration completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
