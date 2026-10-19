#!/usr/bin/env python3
"""
scripts/cleanup_fvg_duplicates.py

Safely deduplicates identical FVGZone rows in the database caused by
historical duplicate insertions of filled FVGs.
Retains the canonical record (lowest ID) for every unique tuple:
(symbol, timeframe, gap_high, gap_low, direction, formed_at).

Usage:
    python scripts/cleanup_fvg_duplicates.py --dry-run
    python scripts/cleanup_fvg_duplicates.py --execute
"""

import argparse
import asyncio
import logging
import sys

from sqlalchemy import func, select, text

from monika.infrastructure.database.db import get_session
from monika.infrastructure.database.models import FVGZone
from monika.interfaces.cli.platform_compat import ensure_utf8_streams

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("CleanupFVGDuplicates")


async def deduplicate_fvgs(dry_run: bool = True) -> int:
    ensure_utf8_streams()
    async with get_session() as session:
        # 1. Count total rows
        total_stmt = select(func.count(FVGZone.id))
        total_rows = (await session.execute(total_stmt)).scalar() or 0

        # 2. Count unique groups
        count_query = text("""
            SELECT count(*) FROM (
                SELECT symbol, timeframe, gap_high, gap_low, direction, formed_at
                FROM fvg_zones
                GROUP BY symbol, timeframe, gap_high, gap_low, direction, formed_at
            ) sub
        """)
        unique_groups = (await session.execute(count_query)).scalar() or 0
        duplicates_to_remove = total_rows - unique_groups

        logger.info(f"Total FVGZone rows: {total_rows}")
        logger.info(f"Unique canonical FVG groups: {unique_groups}")
        logger.info(f"Duplicate rows to remove: {duplicates_to_remove}")

        if duplicates_to_remove <= 0:
            logger.info("No duplicates found. Database is already clean.")
            return 0

        if dry_run:
            logger.info("[DRY-RUN] No rows were deleted. Pass --execute to apply cleanup.")
            return duplicates_to_remove

        logger.info("[EXECUTE] Removing duplicate rows while preserving lowest ID per canonical group...")
        # PostgreSQL-optimized deduplication
        dedup_sql = text("""
            DELETE FROM fvg_zones
            WHERE id NOT IN (
                SELECT MIN(id)
                FROM fvg_zones
                GROUP BY symbol, timeframe, gap_high, gap_low, direction, formed_at
            )
        """)
        res = await session.execute(dedup_sql)
        await session.commit()
        deleted_count = res.rowcount
        logger.info(f"Successfully deleted {deleted_count} duplicate rows.")

        # Post-cleanup verification
        remaining = (await session.execute(total_stmt)).scalar() or 0
        logger.info(f"Remaining FVGZone rows: {remaining} (matches canonical: {remaining == unique_groups})")
        return deleted_count


def main() -> None:
    parser = argparse.ArgumentParser(description="Deduplicate FVGZone rows in database")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--execute", action="store_true", help="Execute deletion (default is dry-run)")
    group.add_argument("--dry-run", action="store_true", help="Only inspect duplicates without deleting")
    args = parser.parse_args()

    is_dry = True if args.dry_run else (not args.execute)
    deleted = asyncio.run(deduplicate_fvgs(dry_run=is_dry))
    sys.exit(0 if deleted >= 0 else 1)


if __name__ == "__main__":
    main()
