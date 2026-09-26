# ==============================================================================
# File: scripts/remediate_ohlcv_duplicates.py
# ==============================================================================

"""
Script Remediasi: Pembersihan Duplikasi PriceOHLCV dan Sinkronisasi Ulang Indikator.

Masalah yang diselesaikan:
1. Menghapus baris duplikat PriceOHLCV (terutama D1 yang tergeser oleh bug broker UTC offset).
2. Memastikan bar D1 kanonikal per tanggal kalender.
3. Menyelaraskan ulang historis bersih dari MT5 (MT5 memiliki 4.300+ bar D1).
4. Menjalankan ulang kalkulasi indikator teknikal (SMA_200, EMA_200) tanpa warning.
"""

import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure trading-agent root is on sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import load_settings
from database.db import get_session
from database.models import PriceOHLCV, TechnicalIndicator
from indicators.technical import TechnicalIndicatorCalculator

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s")
logger = logging.getLogger("RemediateOHLCV")


async def deduplicate_price_ohlcv(session: AsyncSession) -> dict[str, int]:
    """
    Menghapus baris duplikat di tabel PriceOHLCV.
    Untuk D1: Menyimpan 1 bar kanonikal (ID terbesar) per (symbol, tanggal kalender).
    Untuk timeframe intraday: Menyimpan 1 bar per (symbol, timeframe, timestamp).
    """
    logger.info("Memeriksa duplikasi baris di tabel PriceOHLCV...")
    
    # 1. Deduplikasi D1 berbasis tanggal kalender
    d1_stmt = (
        select(
            PriceOHLCV.symbol,
            func.date(PriceOHLCV.timestamp).label("bar_date"),
            func.max(PriceOHLCV.id).label("keep_id"),
            func.count(PriceOHLCV.id).label("total_rows"),
        )
        .where(PriceOHLCV.timeframe == "D1")
        .group_by(PriceOHLCV.symbol, func.date(PriceOHLCV.timestamp))
        .having(func.count(PriceOHLCV.id) > 1)
    )
    d1_dupes = (await session.execute(d1_stmt)).all()
    
    deleted_d1 = 0
    for symbol, bar_date, keep_id, total_rows in d1_dupes:
        del_stmt = (
            delete(PriceOHLCV)
            .where(PriceOHLCV.symbol == symbol)
            .where(PriceOHLCV.timeframe == "D1")
            .where(func.date(PriceOHLCV.timestamp) == bar_date)
            .where(PriceOHLCV.id != keep_id)
        )
        res = await session.execute(del_stmt)
        deleted_d1 += res.rowcount or 0

    # 2. Deduplikasi intraday (M15, H1, H4) berbasis timestamp persis
    intraday_stmt = (
        select(
            PriceOHLCV.symbol,
            PriceOHLCV.timeframe,
            PriceOHLCV.timestamp,
            func.max(PriceOHLCV.id).label("keep_id"),
            func.count(PriceOHLCV.id).label("total_rows"),
        )
        .where(PriceOHLCV.timeframe != "D1")
        .group_by(PriceOHLCV.symbol, PriceOHLCV.timeframe, PriceOHLCV.timestamp)
        .having(func.count(PriceOHLCV.id) > 1)
    )
    intraday_dupes = (await session.execute(intraday_stmt)).all()
    
    deleted_intraday = 0
    for symbol, tf, ts, keep_id, total_rows in intraday_dupes:
        del_stmt = (
            delete(PriceOHLCV)
            .where(PriceOHLCV.symbol == symbol)
            .where(PriceOHLCV.timeframe == tf)
            .where(PriceOHLCV.timestamp == ts)
            .where(PriceOHLCV.id != keep_id)
        )
        res = await session.execute(del_stmt)
        deleted_intraday += res.rowcount or 0

    if deleted_d1 or deleted_intraday:
        await session.commit()
    logger.info(f"Deduplikasi selesai: {deleted_d1} baris D1 dibersihkan, {deleted_intraday} baris intraday dibersihkan.")
    return {"deleted_d1": deleted_d1, "deleted_intraday": deleted_intraday}


async def sync_mt5_history(settings: dict, session: AsyncSession) -> dict[str, int]:
    """Mengambil riwayat bersih hingga 1.000 bar dari MT5 jika tersedia."""
    try:
        from execution.mt5_client import MT5Client
        client = MT5Client(settings)
        if not await client.connect():
            logger.warning("MT5 tidak terhubung, sinkronisasi riwayat MT5 dilewati.")
            return {}

        universe = settings.get("trading", {}).get("asset_universe", ["BTCUSD", "EURUSD", "XAUUSD"])
        logger.info(f"Sinkronisasi riwayat MT5 untuk {len(universe)} simbol (D1, H4, H1 count=1000)...")
        results = await client.fetch_and_save_all(
            session,
            symbols=universe,
            timeframes=["D1", "H4", "H1"],
            count=1000,
        )
        await client.disconnect()
        return results
    except Exception as e:
        logger.warning(f"Gagal menyelaraskan riwayat MT5: {e}")
        return {}


async def recompute_indicators(settings: dict, session: AsyncSession) -> dict[str, int]:
    """Menghitung ulang indikator teknikal dengan data bersih."""
    universe = settings.get("trading", {}).get("asset_universe", ["BTCUSD", "EURUSD", "XAUUSD"])
    calc = TechnicalIndicatorCalculator(session, settings.get("trading", {}))
    logger.info("Menghitung ulang indikator teknikal untuk semua simbol...")
    results = await calc.compute_all_symbols(universe, ["D1", "H4", "H1"])
    return results


async def main():
    logger.info("=== Memulai Remediasi OHLCV & Indikator ===")
    settings = load_settings()

    async with get_session() as session:
        # 1. Bersihkan duplikat database
        dedupe_res = await deduplicate_price_ohlcv(session)

        # 2. Ambil riwayat bersih dari MT5
        mt5_res = await sync_mt5_history(settings, session)

        # 3. Hitung ulang indikator teknikal
        ind_res = await recompute_indicators(settings, session)

        # 4. Ringkasan status akhir BTCUSD D1
        btcusd_d1_cnt = (
            await session.execute(
                select(func.count(PriceOHLCV.id)).where(
                    PriceOHLCV.symbol == "BTCUSD", PriceOHLCV.timeframe == "D1"
                )
            )
        ).scalar_one()

        btcusd_ind_cnt = (
            await session.execute(
                select(func.count(TechnicalIndicator.id)).where(
                    TechnicalIndicator.symbol == "BTCUSD",
                    TechnicalIndicator.timeframe == "D1",
                )
            )
        ).scalar_one()

        logger.info("=== Ringkasan Hasil Remediasi ===")
        logger.info(f"PriceOHLCV duplikat terhapus : {dedupe_res}")
        logger.info(f"MT5 bars diselaraskan       : {sum(mt5_res.values())} bar")
        logger.info(f"Indikator dihitung          : {sum(ind_res.values())} baris")
        logger.info(f"BTCUSD D1 total bar bersih  : {btcusd_d1_cnt} bar")
        logger.info(f"BTCUSD D1 total indikator   : {btcusd_ind_cnt} baris")
        logger.info("Remediasi selesai dengan sukses!")


if __name__ == "__main__":
    asyncio.run(main())
