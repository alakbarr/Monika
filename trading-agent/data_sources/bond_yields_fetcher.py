# ==============================================================================
# File: data_sources/bond_yields_fetcher.py
# ==============================================================================

"""
Fetcher Yield Obligasi Pemerintah Internasional (Async) menggunakan ECB Data Portal & FRED API.

Mengambil data penutupan yield 10-tahun:
  - Jerman (Bund 10Y): ECB Data Portal API (Euro Area AAA 10Y Yield) & FRED IRLTLT01DEM156N -> Driver EURUSD
  - Inggris (Gilt 10Y): FRED IRLTLT01GBM156N -> Driver GBPUSD
  - Jepang (JGB 10Y): FRED IRLTLT01JPM156N -> Driver USDJPY
  - Australia (ACGB 10Y): FRED IRLTLT01AUM156N -> Driver AUDUSD

ECB Data Portal API menyediakan endpoint SDMX-REST publik gratis tanpa autentikasi.
FRED API menyediakan kurva benchmark yield obligasi pemerintah jangka panjang resmi (OECD).
"""

import asyncio
import io
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import BondYieldData
from utils.api.http_retry import fetch_with_retry

logger = logging.getLogger("TradingAgent.BondYields")

ECB_AAA_YIELD_URL = "https://data-api.ecb.europa.eu/service/data/YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y"
ECB_AAA_2Y_URL = "https://data-api.ecb.europa.eu/service/data/YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_2Y"
FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

# FRED Benchmark 10Y Series per Country
FRED_BOND_SERIES = {
    "DE_10Y": "IRLTLT01DEM156N",
    "UK_10Y": "IRLTLT01GBM156N",
    "JP_10Y": "IRLTLT01JPM156N",
    "AU_10Y": "IRLTLT01AUM156N",
}


class BondYieldFetcher:
    """
    Fetcher yield obligasi pemerintah internasional.
    Menggunakan ECB Data Portal API sebagai sumber data harian resmi untuk DE_10Y & DE_2Y,
    CentralBankWatch untuk kurva sovereign harian UK, JP, AU, US,
    dan FRED API sebagai fallback benchmark OECD.
    """

    def __init__(self, session: AsyncSession, fred_api_key: Optional[str] = None):
        self.session = session
        self.fred_api_key = fred_api_key or os.getenv("FRED_API_KEY", "")

    async def fetch(self, period: str = "15d") -> dict[str, int]:
        """
        Mengambil yield obligasi untuk semua negara yang didukung (DE, UK, JP, AU, US) baik 2Y maupun 10Y.
        """
        results: dict[str, int] = {
            "DE_10Y": 0,
            "DE_2Y": 0,
            "UK_10Y": 0,
            "UK_2Y": 0,
            "JP_10Y": 0,
            "JP_2Y": 0,
            "AU_10Y": 0,
            "AU_2Y": 0,
        }

        # 1. Fetch DE_10Y & DE_2Y via ECB Data Portal API (High-frequency daily Euro AAA Yields)
        try:
            ecb_10y_saved = await self._fetch_ecb_yield(ECB_AAA_YIELD_URL, "DE_10Y")
            results["DE_10Y"] = ecb_10y_saved
            if ecb_10y_saved > 0:
                logger.info(f"Saved {ecb_10y_saved} DE_10Y records from ECB Data Portal API")
        except Exception as e:
            logger.warning(f"ECB Data Portal 10Y fetch failed: {e}")

        try:
            ecb_2y_saved = await self._fetch_ecb_yield(ECB_AAA_2Y_URL, "DE_2Y")
            results["DE_2Y"] = ecb_2y_saved
            if ecb_2y_saved > 0:
                logger.info(f"Saved {ecb_2y_saved} DE_2Y records from ECB Data Portal API")
        except Exception as e:
            logger.warning(f"ECB Data Portal 2Y fetch failed: {e}")

        # 2. Fetch sovereign curves via CentralBankWatch (UK, JP, AU 2Y & 10Y daily snapshots)
        try:
            from data_sources.central_bank_watch import CentralBankWatchFetcher
            cbw_fetcher = CentralBankWatchFetcher(self.session)
            cbw_yields = await cbw_fetcher.fetch_sovereign_yields()
            for k in ("UK_10Y", "UK_2Y", "JP_10Y", "JP_2Y", "AU_10Y", "AU_2Y"):
                if k in cbw_yields:
                    results[k] = 1
            if cbw_yields:
                logger.info(f"CentralBankWatch sovereign curves updated: {list(cbw_yields.keys())}")
        except Exception as e:
            logger.warning(f"CentralBankWatch sovereign curves fetch failed: {e}")

        # 3. Fallback FRED series for countries (UK, JP, AU, and fallback DE if needed)
        if self.fred_api_key:
            for label, series_id in FRED_BOND_SERIES.items():
                if results.get(label, 0) > 0:
                    continue  # Sudah terisi dari sumber primer
                try:
                    fred_saved = await self._fetch_fred_bond_series(series_id, label)
                    results[label] = fred_saved
                    if fred_saved > 0:
                        logger.info(f"Saved {fred_saved} {label} records from FRED API ({series_id})")
                except Exception as e:
                    logger.warning(f"FRED fetch failed for {label} ({series_id}): {e}")
        else:
            logger.debug("FRED_API_KEY not configured, skipping FRED international bond yields fetch")

        return results

    async def _fetch_ecb_yield(self, url: str = ECB_AAA_YIELD_URL, label: str = "DE_10Y") -> int:
        """
        Mengambil data harian Euro Area AAA Yield (10Y atau 2Y) dari ECB Data Portal API.
        Endpoint REST/SDMX gratis tanpa auth.
        """
        params = {"startPeriod": "2024-01-01", "format": "csvdata", "detail": "dataonly"}
        response = await fetch_with_retry(
            url=url,
            method="GET",
            params=params,
            timeout_seconds=20,
            headers={"Accept": "text/csv"},
            response_type="text",
        )
        if not response or not isinstance(response, str):
            return 0

        csv_text = response
        try:
            df = pd.read_csv(io.StringIO(csv_text))
        except Exception as e:
            logger.warning(f"Failed parsing ECB CSV: {e}")
            return 0

        if df.empty or "TIME_PERIOD" not in df.columns or "OBS_VALUE" not in df.columns:
            return 0

        saved = 0
        for _, row in df.iterrows():
            try:
                date_str = str(row["TIME_PERIOD"]).strip()
                val_raw = row["OBS_VALUE"]
                if bool(pd.isna(val_raw)) or str(val_raw).strip() == ".":
                    continue
                val = float(str(val_raw))
                dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)

                exists = await self.session.execute(
                    select(BondYieldData.id)
                    .where(BondYieldData.country_tenor == label)
                    .where(BondYieldData.date == dt)
                    .limit(1)
                )
                if exists.scalar_one_or_none() is not None:
                    continue

                self.session.add(BondYieldData(country_tenor=label, date=dt, yield_percent=val))
                saved += 1
            except Exception:
                continue

        if saved:
            from database.safe_ops import safe_commit
            await safe_commit(self.session, label="BondYield.ECB")

        return saved

    async def _fetch_fred_bond_series(self, series_id: str, label: str, limit: int = 15) -> int:
        """
        Mengambil data benchmark yield 10-tahun internasional dari FRED API.
        """
        params = {
            "series_id": series_id,
            "api_key": self.fred_api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": str(limit),
        }
        data = await fetch_with_retry(FRED_BASE_URL, params=params, timeout=25)
        if not data or not isinstance(data, dict):
            return 0

        observations = data.get("observations", [])
        saved = 0
        for obs in observations:
            date_str = obs.get("date", "")
            val_str = obs.get("value", ".")
            if not date_str or not val_str or val_str in (".", "ND", "nd"):
                continue

            try:
                dt = datetime.strptime(date_str.strip(), "%Y-%m-%d").replace(tzinfo=timezone.utc)
                val = float(val_str)
            except (ValueError, TypeError):
                continue

            try:
                exists = await self.session.execute(
                    select(BondYieldData.id)
                    .where(BondYieldData.country_tenor == label)
                    .where(BondYieldData.date == dt)
                    .limit(1)
                )
                if exists.scalar_one_or_none() is not None:
                    continue

                self.session.add(BondYieldData(country_tenor=label, date=dt, yield_percent=val))
                saved += 1
            except Exception:
                continue

        if saved:
            from database.safe_ops import safe_commit
            await safe_commit(self.session, label=f"BondYield.{label}")

        return saved
