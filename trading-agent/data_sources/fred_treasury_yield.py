# ==============================================================================
# File: data_sources/fred_treasury_yield.py
# ==============================================================================

"""
Fetcher FRED Treasury Yield & Interest Rate (Async).

Mengambil data kurva yield US Treasury dan suku bunga acuan dari API
Federal Reserve Economic Data (FRED) oleh St. Louis Fed.

Dokumentasi API: https://fred.stlouisfed.org/docs/api/fred/
Memerlukan FRED_API_KEY di .env

Series yang digunakan (dari config/settings.yaml data_sources.fred.series):
  DGS2    — 2-Year Treasury Constant Maturity Rate
  DGS5    — 5-Year Treasury Constant Maturity Rate
  DGS10   — 10-Year Treasury Constant Maturity Rate
  DGS30   — 30-Year Treasury Constant Maturity Rate
  FEDFUNDS — Effective Federal Funds Rate
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import aiohttp
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import TreasuryYield, InterestRate
from utils.api.http_retry import fetch_with_retry

logger = logging.getLogger("TradingAgent.FRED")

FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

# Pemetaan FRED series ID ke tipe/label tenor
TENOR_SERIES = {"DGS2", "DGS5", "DGS10", "DGS30", "DFII10", "T10YIE"}
INTEREST_RATE_SERIES = {"FEDFUNDS", "ECBDFR", "BOERUKM", "IRSTCB01JPM156N", "IRSTCB01AUM156N"}

# Nama tenor yang mudah dibaca
SERIES_TO_TENOR = {
    "DGS2": "2Y",
    "DGS5": "5Y",
    "DGS10": "10Y",
    "DGS30": "30Y",
    "DFII10": "10Y_REAL",
    "T10YIE": "10Y_INFLATION",
}

# Label bank untuk suku bunga
SERIES_TO_BANK = {
    "FEDFUNDS": "FED",
    "ECBDFR": "ECB",
    "BOERUKM": "BOE",    # BOE Base Rate
    "IRSTCB01JPM156N": "BOJ",  # BOJ Policy Rate (OECD series via FRED)
    "IRSTCB01AUM156N": "RBA",  # RBA Cash Rate Target (OECD series via FRED)
}


class FREDDataFetcher:
    """
    Mengambil data treasury yield dan suku bunga dari API FRED.

    Dijalankan harian. Melewati observasi yang sudah tersimpan (berdasarkan tanggal).
    Menangani nilai '.' dari FRED untuk observasi yang kosong.
    """

    def __init__(self, session: AsyncSession, config: dict, api_key: Optional[str] = None):
        """
        Args:
            session: Async SQLAlchemy session.
            config: data_sources.fred section from settings.yaml.
            api_key: FRED API key. Defaults to FRED_API_KEY env var.
        """
        self.session = session
        self.api_key = api_key or os.getenv("FRED_API_KEY", "")
        self.api_url = config.get("api_url", FRED_BASE_URL)
        self.series_map: dict[str, str] = config.get("series", {})  # {label: series_id}
        self.timeout = aiohttp.ClientTimeout(total=30)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def fetch_all(self) -> dict[str, int]:
        """
        Mengambil semua series FRED yang dikonfigurasi.

        Returns:
            Dict dengan keys 'treasury' dan 'interest_rates', berisi jumlah baris baru yang disimpan.
        """
        if not self.api_key:
            logger.error("FRED_API_KEY is not set. Skipping FRED data fetch.")
            return {"treasury": 0, "interest_rates": 0}

        treasury_saved = 0
        rate_saved = 0

        for label, series_id in self.series_map.items():
            try:
                if (
                    series_id in TENOR_SERIES
                    or label.startswith("treasury_")
                    or label.startswith("real_yield_")
                    or label.startswith("inflation_expectation_")
                ):
                    tenor = SERIES_TO_TENOR.get(series_id)
                    if not tenor:
                        tenor = label.split("_")[-1].upper()
                    n = await self._fetch_treasury_series(series_id, tenor)
                    treasury_saved += n
                elif series_id in INTEREST_RATE_SERIES or label.endswith("_rate"):
                    bank = SERIES_TO_BANK.get(series_id)
                    if not bank:
                        bank = label.split("_")[0].upper()
                    n = await self._fetch_interest_rate(series_id, bank)
                    rate_saved += n
                else:
                    logger.warning(f"Unknown FRED series: {series_id} ({label})")
                
            except Exception as e:
                logger.error(f"FRED fetch failed for {series_id}: {e}")
                try:
                    await self.session.rollback()
                except Exception:
                    pass

        logger.info(
            f"FRED fetch complete. Treasury: {treasury_saved} new, "
            f"Interest rates: {rate_saved} new."
        )
        try:
            from data_sources.circuit_breaker import record_feed_heartbeat
            record_feed_heartbeat("fred", metadata={"treasury_saved": treasury_saved, "rate_saved": rate_saved})
        except Exception:
            pass
        return {"treasury": treasury_saved, "interest_rates": rate_saved}

    # ------------------------------------------------------------------
    # Internal — Treasury Yields
    # ------------------------------------------------------------------

    async def _fetch_treasury_series(
        self, series_id: str, tenor: str
    ) -> int:
        """Mengambil data terbaru untuk satu series treasury. Mengembalikan jumlah baris yang disimpan."""
        observations = await self._call_fred(series_id, limit=10)
        saved = 0

        for obs in observations:
            date = self._parse_date(obs.get("date", ""))
            if not date:
                continue
            value_str = obs.get("value", ".")
            if not value_str or value_str in (".", "ND", "nd"):
                continue  # FRED menggunakan '.' atau 'ND' untuk data yang kosong

            try:
                yield_pct = float(value_str)
            except (ValueError, TypeError):
                logger.debug(f"Skipping non-numeric FRED treasury yield value: {value_str}")
                continue

            # Lewati jika sudah ada (duplikat)
            exists = await self.session.execute(
                select(TreasuryYield.id)
                .where(TreasuryYield.tenor == tenor)
                .where(TreasuryYield.date == date)
                .limit(1)
            )
            if exists.scalar_one_or_none() is not None:
                continue

            record = TreasuryYield(
                tenor=tenor,
                yield_percent=yield_pct,
                date=date,
            )
            self.session.add(record)
            saved += 1

        if saved:
            await self.session.commit()
            logger.info(f"Treasury {tenor}: saved {saved} new observations")

        return saved

    # ------------------------------------------------------------------
    # Internal — Interest Rates
    # ------------------------------------------------------------------

    async def _fetch_interest_rate(
        self, series_id: str, bank: str
    ) -> int:
        """Mengambil data suku bunga terbaru. Mengembalikan 1 jika baris baru disimpan."""
        observations = await self._call_fred(series_id, limit=1)
        if not observations:
            return 0

        obs = observations[0]
        value_str = obs.get("value", ".")
        if not value_str or value_str in (".", "ND", "nd"):
            return 0

        effective_date = self._parse_date(obs.get("date", ""))
        if not effective_date:
            return 0
        try:
            rate_pct = float(value_str)
        except (ValueError, TypeError):
            logger.debug(f"Skipping non-numeric FRED interest rate value: {value_str}")
            return 0

        # Lewati jika sudah tersimpan untuk tanggal ini
        exists = await self.session.execute(
            select(InterestRate.id)
            .where(InterestRate.bank == bank)
            .where(InterestRate.effective_date == effective_date)
            .limit(1)
        )
        if exists.scalar_one_or_none() is not None:
            logger.debug(f"Interest rate {bank} already up-to-date ({effective_date.date()})")
            return 0

        record = InterestRate(
            bank=bank,
            rate_percent=rate_pct,
            effective_date=effective_date,
            next_meeting_date=None,  # tidak tersedia langsung dari FRED
        )
        self.session.add(record)
        await self.session.commit()
        logger.info(f"Interest rate saved: {bank} = {rate_pct}% ({effective_date.date()})")
        return 1

    # ------------------------------------------------------------------
    # HTTP helper
    # ------------------------------------------------------------------

    async def _call_fred(
        self,
        series_id: str,
        limit: int = 10,
    ) -> list[dict]:
        """Memanggil endpoint observasi FRED. Mengembalikan daftar dictionary observasi."""
        params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": str(limit),
        }

        data = await fetch_with_retry(self.api_url, params=params, timeout=30)
        if not data or not isinstance(data, dict):
            logger.error(f"FRED API fetch failed for {series_id}")
            return []
            
        observations = data.get("observations", [])
        return observations if isinstance(observations, list) else []

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_date(date_str: str) -> Optional[datetime]:
        """Mengubah format 'YYYY-MM-DD' ke timezone-aware UTC datetime."""
        if not date_str:
            return None
        try:
            dt = datetime.strptime(date_str.strip(), "%Y-%m-%d")
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            logger.warning(f"Cannot parse FRED date: {date_str}")
            return None


# ---------------------------------------------------------------------------
# Quick standalone test
# ---------------------------------------------------------------------------

async def _test():
    import os
    from dotenv import load_dotenv
    from database.db import get_session, init_db

    load_dotenv()
    await init_db()

    from config.settings import load_settings
    settings = load_settings()
    fred_config = settings["data_sources"]["fred"]

    async with get_session() as session:
        fetcher = FREDDataFetcher(session, fred_config)
        result = await fetcher.fetch_all()
        print(f"Saved: {result}")

        # Verify treasury
        rows = await session.execute(select(TreasuryYield).limit(5))
        for r in rows.scalars().all():
            print(f"  Treasury {r.tenor}: {r.yield_percent}% ({r.date.date()})")

        # Verify interest rates
        rows2 = await session.execute(select(InterestRate).limit(5))
        for r in rows2.scalars().all():
            print(f"  Rate {r.bank}: {r.rate_percent}% ({r.effective_date.date()})")


if __name__ == "__main__":
    import sys
    if sys.platform == "win32":
        asyncio.run(_test(), loop_factory=asyncio.SelectorEventLoop)
    else:
        asyncio.run(_test())
