#!/usr/bin/env python3
"""
scripts/repair_price_ohlcv.py

Safely repairs and deduplicates the price_ohlcv table:
1. Ensures canonical_timestamp column and price_ohlcv_rejected audit table exist.
2. Backfills canonical_timestamp for all existing price_ohlcv rows using BrokerTimeResolver.
3. Archives duplicate rows (same symbol, timeframe, canonical_timestamp) into price_ohlcv_rejected.
4. Deletes duplicate rows from price_ohlcv.
5. Optionally fetches fresh canonical history from MT5 across all 8 watched symbols.
6. Verifies 0.0% duplicate rate across all symbols and timeframes.

Usage:
    venv\\Scripts\\python.exe scripts/repair_price_ohlcv.py --dry-run
    venv\\Scripts\\python.exe scripts/repair_price_ohlcv.py --execute
    venv\\Scripts\\python.exe scripts/repair_price_ohlcv.py --execute --fetch-mt5
"""

import argparse
import asyncio
import logging
import sys
from typing import Any, Dict, List, Tuple

from sqlalchemy import func, select, text

from monika.core.config.settings import load_settings
from monika.infrastructure.brokers.mt5.broker_time import BrokerTimeResolver
from monika.infrastructure.database.db import get_session
from monika.infrastructure.database.models import PriceOHLCV, PriceOHLCVRejected
from monika.interfaces.cli.platform_compat import ensure_utf8_streams

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("RepairPriceOHLCV")


async def ensure_schema_ready(session) -> None:
    """Ensure column canonical_timestamp and table price_ohlcv_rejected exist."""
    # Check column
    col_check = text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'price_ohlcv' AND column_name = 'canonical_timestamp'"
    )
    col_exists = (await session.execute(col_check)).scalar_one_or_none()
    if not col_exists:
        logger.info("Adding column canonical_timestamp to price_ohlcv...")
        await session.execute(text("ALTER TABLE price_ohlcv ADD COLUMN canonical_timestamp TIMESTAMPTZ"))
        await session.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_price_sym_tf_canonical_ts "
                "ON price_ohlcv (symbol, timeframe, canonical_timestamp)"
            )
        )
        await session.commit()

    # Check table price_ohlcv_rejected
    tbl_check = text("SELECT table_name FROM information_schema.tables WHERE table_name = 'price_ohlcv_rejected'")
    tbl_exists = (await session.execute(tbl_check)).scalar_one_or_none()
    if not tbl_exists:
        logger.info("Creating table price_ohlcv_rejected...")
        await session.execute(
            text(
                """
                CREATE TABLE price_ohlcv_rejected (
                    id SERIAL PRIMARY KEY,
                    original_id INT,
                    symbol VARCHAR(20) NOT NULL,
                    timeframe VARCHAR(10) NOT NULL,
                    timestamp TIMESTAMPTZ NOT NULL,
                    canonical_timestamp TIMESTAMPTZ,
                    open DOUBLE PRECISION NOT NULL,
                    high DOUBLE PRECISION NOT NULL,
                    low DOUBLE PRECISION NOT NULL,
                    close DOUBLE PRECISION NOT NULL,
                    volume DOUBLE PRECISION NOT NULL,
                    rejected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    reason VARCHAR(255) NOT NULL
                )
                """
            )
        )
        await session.commit()


async def backfill_canonical_timestamps(session, broker_offset_sec: int) -> int:
    """Backfill canonical_timestamp on rows where it is NULL."""
    stmt = (
        select(PriceOHLCV.id, PriceOHLCV.timestamp, PriceOHLCV.timeframe)
        .where(PriceOHLCV.canonical_timestamp.is_(None))
        .limit(10000)
    )
    res = await session.execute(stmt)
    rows = res.all()
    if not rows:
        return 0

    updated = 0
    batch_updates: List[Dict[str, Any]] = []
    for r_id, ts, tf in rows:
        canon_ts = BrokerTimeResolver.to_canonical_bar_timestamp(ts, tf, offset_seconds=broker_offset_sec)
        batch_updates.append({"_id": r_id, "_canon_ts": canon_ts})
        updated += 1

    if batch_updates:
        update_stmt = text("UPDATE price_ohlcv SET canonical_timestamp = :_canon_ts WHERE id = :_id")
        for chunk_start in range(0, len(batch_updates), 1000):
            chunk = batch_updates[chunk_start : chunk_start + 1000]
            await session.execute(update_stmt, chunk)
        await session.commit()

    return updated


async def deduplicate_price_ohlcv(dry_run: bool = True) -> int:
    """Identify duplicate rows, archive them, and delete them."""
    settings = load_settings()
    offset_sec = BrokerTimeResolver.resolve_offset_seconds(settings)
    logger.info(f"Using broker offset: {offset_sec}s ({offset_sec / 3600:+.1f}h)")

    async with get_session() as session:
        await ensure_schema_ready(session)

        # Backfill canonical timestamps in batches
        logger.info("Backfilling canonical timestamps for unpopulated rows...")
        total_backfilled = 0
        while True:
            n = await backfill_canonical_timestamps(session, offset_sec)
            total_backfilled += n
            if n == 0:
                break
        if total_backfilled > 0:
            logger.info(f"Backfilled canonical_timestamp for {total_backfilled} rows.")

        # Identify duplicates based on (symbol, timeframe, canonical_timestamp)
        dup_query = text(
            """
            SELECT symbol, timeframe, canonical_timestamp, count(*) as count
            FROM price_ohlcv
            WHERE canonical_timestamp IS NOT NULL
            GROUP BY symbol, timeframe, canonical_timestamp
            HAVING count(*) > 1
            """
        )
        dup_groups = (await session.execute(dup_query)).all()
        logger.info(f"Found {len(dup_groups)} timestamp groups with duplicates.")

        if not dup_groups:
            logger.info("No duplicates found in price_ohlcv.")
            return 0

        # Calculate total duplicate excess rows
        total_excess_rows = sum(r[3] - 1 for r in dup_groups)
        logger.info(f"Total duplicate rows to archive and delete: {total_excess_rows}")

        if dry_run:
            logger.info("[DRY-RUN] Aborting before archiving or deletion. Run with --execute to apply.")
            return total_excess_rows

        # Archive and delete duplicates
        # Keep the record with the MAX(id) for each (symbol, timeframe, canonical_timestamp)
        archive_sql = text(
            """
            INSERT INTO price_ohlcv_rejected (
                original_id, symbol, timeframe, timestamp, canonical_timestamp,
                open, high, low, close, volume, reason
            )
            SELECT p.id, p.symbol, p.timeframe, p.timestamp, p.canonical_timestamp,
                   p.open, p.high, p.low, p.close, p.volume, 'DUPLICATE_BAR_CANONICAL_COLLISION'
            FROM price_ohlcv p
            JOIN (
                SELECT symbol, timeframe, canonical_timestamp, MAX(id) as keep_id
                FROM price_ohlcv
                WHERE canonical_timestamp IS NOT NULL
                GROUP BY symbol, timeframe, canonical_timestamp
                HAVING count(*) > 1
            ) d ON p.symbol = d.symbol
               AND p.timeframe = d.timeframe
               AND p.canonical_timestamp = d.canonical_timestamp
               AND p.id != d.keep_id
            """
        )
        logger.info("Archiving duplicate rows into price_ohlcv_rejected...")
        await session.execute(archive_sql)

        delete_sql = text(
            """
            DELETE FROM price_ohlcv p
            USING (
                SELECT symbol, timeframe, canonical_timestamp, MAX(id) as keep_id
                FROM price_ohlcv
                WHERE canonical_timestamp IS NOT NULL
                GROUP BY symbol, timeframe, canonical_timestamp
                HAVING count(*) > 1
            ) d
            WHERE p.symbol = d.symbol
              AND p.timeframe = d.timeframe
              AND p.canonical_timestamp = d.canonical_timestamp
              AND p.id != d.keep_id
            """
        )
        logger.info("Deleting duplicate rows from price_ohlcv...")
        res_del = await session.execute(delete_sql)
        deleted_count = res_del.rowcount
        await session.commit()
        logger.info(f"Successfully archived and deleted {deleted_count} duplicate rows.")

        return deleted_count


async def verify_duplicate_rate() -> bool:
    """Audit check: report duplicate rate across all symbols and timeframes."""
    async with get_session() as session:
        audit_sql = text(
            """
            SELECT symbol, timeframe,
                   count(*) as total_rows,
                   count(DISTINCT canonical_timestamp) as distinct_canonical
            FROM price_ohlcv
            GROUP BY symbol, timeframe
            ORDER BY symbol, timeframe
            """
        )
        rows = (await session.execute(audit_sql)).all()
        print("\n" + "=" * 70)
        print(f"{'SYMBOL':<10} {'TF':<6} {'TOTAL':<8} {'DISTINCT':<10} {'DUPLICATE %':<12} {'STATUS'}")
        print("=" * 70)
        all_clean = True
        for sym, tf, total, distinct in rows:
            dup_pct = ((total - distinct) / total * 100.0) if total > 0 else 0.0
            status = "CLEAN" if dup_pct == 0.0 else "DUPLICATES DETECTED"
            if dup_pct > 0.0:
                all_clean = False
            print(f"{sym:<10} {tf:<6} {total:<8} {distinct:<10} {dup_pct:<11.2f}% {status}")
        print("=" * 70 + "\n")
        return all_clean


async def fetch_clean_from_mt5(symbols: List[str]) -> None:
    """Fetch clean bars from MT5 for the specified symbols across major timeframes."""
    from monika.infrastructure.brokers.mt5.client import MT5Client

    settings = load_settings()
    client = MT5Client(settings)
    connected = await client.ensure_connected()
    if not connected:
        logger.error("Failed to connect to MT5 terminal for historical resync.")
        return

    logger.info(f"Fetching clean bars from MT5 for {symbols}...")
    timeframes = ["H1", "H4", "D1", "W1"]
    async with get_session() as session:
        for sym in symbols:
            for tf in timeframes:
                count = 2000 if tf in ("H1", "H4") else 800
                logger.info(f"Fetching {count} bars of {sym}/{tf} from MT5...")
                df = await client.get_ohlcv(sym, tf, count=count)
                if df is not None and not df.empty:
                    saved = await client.save_ohlcv(session, sym, tf, df)
                    logger.info(f"Saved/updated {saved} bars for {sym}/{tf}")
                else:
                    logger.warning(f"No bars returned for {sym}/{tf}")


async def main() -> None:
    ensure_utf8_streams()
    parser = argparse.ArgumentParser(description="Repair and deduplicate price_ohlcv table.")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Dry run without modifying database.")
    parser.add_argument("--execute", action="store_true", default=False, help="Execute repairs and deletions.")
    parser.add_argument("--fetch-mt5", action="store_true", default=False, help="Fetch fresh bars from MT5.")
    args = parser.parse_args()

    if not args.execute and not args.dry_run:
        logger.info("No action specified. Running dry run by default...")
        args.dry_run = True

    try:
        await deduplicate_price_ohlcv(dry_run=args.dry_run)
        if args.execute and args.fetch_mt5:
            watched_symbols = ["XAUUSD", "EURUSD", "USDJPY", "GBPUSD", "AUDUSD", "BTCUSD", "XTIUSD", "XBRUSD"]
            await fetch_clean_from_mt5(watched_symbols)

        clean = await verify_duplicate_rate()
        if clean:
            logger.info("VERIFICATION PASSED: All symbols and timeframes report 0.0% duplicates.")
        else:
            logger.warning("VERIFICATION WARNING: Some duplicates remain or need execution.")
    except Exception as e:
        logger.exception(f"Fatal error during repair: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
