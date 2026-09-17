# ==============================================================================
# File: data_sources/cftc_cot.py
# ==============================================================================

"""
CFTC COT Report Fetcher (Async).

Mengambil data Commitments of Traders (COT) disaggregated dari
CFTC Public Reporting Environment (Socrata API).

Dokumentasi: https://publicreporting.cftc.gov/stories/s/r4w3-av2u
Dataset: Disaggregated Futures and Options Combined (futopt)
Kode market dikonfigurasi di config/settings.yaml (data_sources.cftc_cot.markets).
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Any

import aiohttp
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import COTReport
from utils.api.http_retry import fetch_with_retry

logger = logging.getLogger("TradingAgent.CFTC")

# CFTC Socrata dataset IDs
# Disaggregated Futures+Options Combined (komoditas seperti Emas, Minyak)
DISAGGREGATED_DATASET = "kh3c-gbw2"
DISAGGREGATED_URL = f"https://publicreporting.cftc.gov/resource/{DISAGGREGATED_DATASET}.json"

# Traders in Financial Futures (mata uang forex: EUR, GBP, JPY, AUD, dsb.)
FINANCIAL_DATASET = "gpe5-46if"
FINANCIAL_URL = f"https://publicreporting.cftc.gov/resource/{FINANCIAL_DATASET}.json"

# Market yang menggunakan dataset komoditas (disaggregated) - berdasarkan market code
COMMODITY_CODES = {"088691", "067651"}  # Gold, WTI Crude Oil


class CFTCCOTFetcher:
    """
    Fetcher laporan COT dari CFTC Socrata API.

    Dijalankan mingguan (data dirilis tiap Jumat ~15:30 ET untuk posisi Selasa sebelumnya).
    Akan mengabaikan market jika data laporan terbaru sudah tersimpan.
    """

    def __init__(self, session: AsyncSession, config: dict):
        """
        Args:
            session: Async SQLAlchemy session.
            config: data_sources.cftc_cot section from settings.yaml.
        """
        self.session = session
        self.markets: dict[str, str] = config.get("markets", {})  # {name: code}
        self.timeout = aiohttp.ClientTimeout(total=30)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def fetch_all(self) -> int:
        """Mengambil data COT untuk semua market yang dikonfigurasi. Mengembalikan jumlah record baru."""
        if not self.markets:
            logger.warning("No COT markets configured. Check data_sources.cftc_cot.markets in settings.yaml")
            return 0

        total_saved = 0
        for market_name, market_code in self.markets.items():
            try:
                # Pilih dataset endpoint berdasarkan tipe komoditas vs financial futures
                if market_code in COMMODITY_CODES:
                    url = DISAGGREGATED_URL
                else:
                    url = FINANCIAL_URL

                # Query kanonikal CFTC API menggunakan cftc_contract_market_code
                params = {
                    "$where": f"cftc_contract_market_code='{market_code}'",
                    "$order": "report_date_as_yyyy_mm_dd DESC",
                    "$limit": "52",
                }

                saved = await self._fetch_and_save(url, params, market_name, market_code)
                total_saved += saved

                # Rate limiting (delay) untuk free-tier
                await asyncio.sleep(1.5)
            except Exception as e:
                logger.error(f"COT fetch failed for {market_name} ({market_code}): {e}")
                try:
                    await self.session.rollback()
                except Exception:
                    pass
                continue

        logger.info(f"COT fetch complete. {total_saved} new records saved.")
        return total_saved

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _fetch_and_save(
        self,
        url: str,
        params: dict,
        market_name: str,
        market_code: str,
    ) -> int:
        """Fungsi generik: mengambil dari API, parsing respons, dan menyimpan ke DB."""
        data = await fetch_with_retry(url, params=params, timeout=30)

        if not data:
            logger.warning(f"No COT data returned for {market_name} ({market_code})")
            return 0

        if not isinstance(data, list):
            logger.warning(f"Unexpected COT response format for {market_name} ({market_code}): {type(data).__name__}")
            return 0

        records_saved = 0
        for row in data:
            if not isinstance(row, dict):
                continue
            report_date = self._parse_date(row.get("report_date_as_yyyy_mm_dd", ""))
            if not report_date:
                continue

            # Lewati jika tanggal ini sudah ada di DB
            existing = (await self.session.execute(
                select(COTReport.id)
                .where(COTReport.market_code == market_code)
                .where(COTReport.report_date == report_date)
                .limit(1)
            )).scalar_one_or_none()

            if existing is not None:
                continue

            # Multi-fallback parser posisi untuk mendukung skema TFF dan Komoditas
            dealer_long = self._int(
                row.get("dealer_positions_long_all")
                or row.get("dealer_positions_long")
                or row.get("swap_positions_long_all")
                or row.get("swap_positions_long")
                or row.get("prod_merc_positions_long")
            )
            dealer_short = self._int(
                row.get("dealer_positions_short_all")
                or row.get("dealer_positions_short")
                or row.get("swap__positions_short_all")
                or row.get("swap_positions_short_all")
                or row.get("swap_positions_short")
                or row.get("prod_merc_positions_short")
            )
            asset_mgr_long = self._int(
                row.get("asset_mgr_positions_long_all")
                or row.get("asset_mgr_positions_long")
                or row.get("other_rept_positions_long_all")
                or row.get("other_rept_positions_long")
                or row.get("other_rept_positions_long_1")
            )
            asset_mgr_short = self._int(
                row.get("asset_mgr_positions_short_all")
                or row.get("asset_mgr_positions_short")
                or row.get("other_rept_positions_short_all")
                or row.get("other_rept_positions_short")
                or row.get("other_rept_positions_short_1")
            )
            leveraged_long = self._int(
                row.get("lev_money_positions_long")
                or row.get("lev_money_positions_long_all")
                or row.get("m_money_positions_long_all")
                or row.get("m_money_positions_long")
                or row.get("m_money_positions_long_old")
            )
            leveraged_short = self._int(
                row.get("lev_money_positions_short")
                or row.get("lev_money_positions_short_all")
                or row.get("m_money_positions_short_all")
                or row.get("m_money_positions_short")
                or row.get("m_money_positions_short_old")
            )

            record = COTReport(
                report_date=report_date,
                market_code=market_code,
                dealer_long=dealer_long,
                dealer_short=dealer_short,
                asset_mgr_long=asset_mgr_long,
                asset_mgr_short=asset_mgr_short,
                leveraged_long=leveraged_long,
                leveraged_short=leveraged_short,
                fetched_at=datetime.now(timezone.utc),
            )
            self.session.add(record)
            records_saved += 1

        if records_saved > 0:
            await self.session.commit()
            logger.info(f"COT saved: {market_name} ({market_code}) - {records_saved} records")
        else:
            logger.debug(f"COT {market_name} already up-to-date")

        return records_saved

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_date(date_str: Optional[str]) -> Optional[datetime]:
        """Mengubah string tanggal CFTC (ISO) ke UTC datetime."""
        if not date_str or not isinstance(date_str, str):
            return None
        try:
            # Handle "2024-01-09T00:00:00.000" format
            clean = date_str.split("T")[0]
            dt = datetime.strptime(clean, "%Y-%m-%d")
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            logger.warning(f"Cannot parse CFTC date: {date_str}")
            return None

    @staticmethod
    def _int(value: Any) -> int:
        """Konversi aman ke integer."""
        if value is None:
            return 0
        try:
            if isinstance(value, str):
                value = value.replace(",", "").strip()
            return int(float(value))
        except (ValueError, TypeError):
            return 0


# ---------------------------------------------------------------------------
# Quick standalone test
# ---------------------------------------------------------------------------

async def _test():
    import os
    from dotenv import load_dotenv
    from database.db import get_session, init_db

    load_dotenv()
    await init_db()

    config = {
        "markets": {
            "gold": "088691",
            "crude_oil": "067651",
            "euro_fx": "099741",
            "british_pound": "096742",
            "japanese_yen": "097741",
            "australian_dollar": "232741",
        }
    }

    async with get_session() as session:
        fetcher = CFTCCOTFetcher(session, config)
        saved = await fetcher.fetch_all()
        print(f"Saved {saved} COT records")

        # Verify
        result = await session.execute(select(COTReport).limit(5))
        rows = result.scalars().all()
        for r in rows:
            print(f"  {r.market_code}: L={r.leveraged_long} / S={r.leveraged_short} ({r.report_date.date()})")


if __name__ == "__main__":
    import sys
    if sys.platform == "win32":
        asyncio.run(_test(), loop_factory=asyncio.SelectorEventLoop)
    else:
        asyncio.run(_test())
