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
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from monika.infrastructure.llm.rate_limiting.http_retry import fetch_with_retry
from monika.infrastructure.database.models import BondYieldData

logger = logging.getLogger("TradingAgent.BondYields")

ECB_AAA_YIELD_URL = "https://data-api.ecb.europa.eu/service/data/YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y"
ECB_AAA_2Y_URL = "https://data-api.ecb.europa.eu/service/data/YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_2Y"
ECB_AAA_COMBINED_YIELD_URL = "https://data-api.ecb.europa.eu/service/data/YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y+SR_2Y"
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

    _last_ecb_fetch_ts: float = 0.0

    def __init__(self, session: AsyncSession, fred_api_key: Optional[str] = None):
        self.session = session
        self.fred_api_key = fred_api_key or os.getenv("FRED_API_KEY", "")
        self._session_lock = asyncio.Lock()
        self._last_ecb_counts: dict[str, int] = {}

    async def fetch(self, period: str = "15d", cache_ttl_sec: float = 0.0) -> dict[str, int]:
        """
        Mengambil yield obligasi untuk semua negara yang didukung (DE, UK, JP, AU, US) baik 2Y maupun 10Y.
        Jika cache_ttl_sec > 0 dan fetch ECB berhasil dalam rentang TTL, pemanggilan remote ECB dilewati.
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

        try:
            async with asyncio.timeout(35.0):
                # 1. Fetch DE_10Y & DE_2Y via ECB Data Portal API (Unified single SDMX query)
                now_ts = time.time()
                ecb_cached = (
                    cache_ttl_sec > 0.0
                    and BondYieldFetcher._last_ecb_fetch_ts > 0.0
                    and (now_ts - BondYieldFetcher._last_ecb_fetch_ts) < cache_ttl_sec
                )
                if ecb_cached:
                    logger.debug(
                        f"BondYieldFetcher: Menggunakan data yield ECB dari cache recente (< {cache_ttl_sec:.0f}s)"
                    )
                    results["DE_10Y"] = 1
                    results["DE_2Y"] = 1
                else:
                    try:
                        async with asyncio.timeout(15.0):
                            ecb_res = await self._fetch_ecb_yield(ECB_AAA_COMBINED_YIELD_URL, "DE_COMBINED")
                            if isinstance(ecb_res, int) and ecb_res >= 0:
                                counts = getattr(self, "_last_ecb_counts", {})
                                results["DE_10Y"] = counts.get("DE_10Y", max(1, ecb_res))
                                results["DE_2Y"] = counts.get("DE_2Y", max(1, ecb_res))
                                BondYieldFetcher._last_ecb_fetch_ts = now_ts
                                if ecb_res > 0:
                                    logger.info(f"Saved {ecb_res} Euro Area AAA yield records from ECB Data Portal API")
                            else:
                                logger.info("ECB Data Portal returned non-zero error; falling back to CentralBankWatch")
                    except TimeoutError, asyncio.TimeoutError:
                        logger.info("ECB Data Portal fetch timed out (15s budget reached); falling back to CBW")
                    except Exception as e:
                        logger.info(f"ECB Data Portal fetch error: {e}; falling back to CBW")

                # 2. Fetch sovereign curves via CentralBankWatch (DE, UK, JP, AU 2Y & 10Y daily snapshots)
                try:
                    from monika.infrastructure.data_ingestion.sources.central_bank_watch import CentralBankWatchFetcher

                    cbw_fetcher = CentralBankWatchFetcher(self.session)
                    cbw_yields = await cbw_fetcher.fetch_sovereign_yields(cache_ttl_sec=300.0)
                    for k in ("DE_10Y", "DE_2Y", "UK_10Y", "UK_2Y", "JP_10Y", "JP_2Y", "AU_10Y", "AU_2Y"):
                        if k in cbw_yields and results.get(k, 0) == 0:
                            results[k] = 1
                    if cbw_yields:
                        logger.info(f"CentralBankWatch sovereign curves updated: {list(cbw_yields.keys())}")
                except Exception as e:
                    logger.warning(f"CentralBankWatch sovereign curves fetch failed: {e}")

                # 3. Fallback FRED series for countries (UK, JP, AU, and fallback DE if needed)
                if self.fred_api_key:
                    for label, series_id in FRED_BOND_SERIES.items():
                        if results.get(label, 0) > 0:
                            continue  # Sudah terisi dari sumber primer / CBW
                        try:
                            fred_saved = await self._fetch_fred_bond_series(series_id, label)
                            results[label] = max(1, fred_saved) if fred_saved >= 0 else 0
                            if fred_saved > 0:
                                logger.info(f"Saved {fred_saved} {label} records from FRED API ({series_id})")
                        except Exception as e:
                            logger.warning(f"FRED fetch failed for {label} ({series_id}): {e}")
                else:
                    logger.debug("FRED_API_KEY not configured, skipping FRED international bond yields fetch")
        except TimeoutError:
            logger.warning("BondYieldFetcher: Fetch process hit 35s timeout limit; returning partial results")

        return results

    async def _fetch_ecb_yield(
        self,
        url: str = ECB_AAA_COMBINED_YIELD_URL,
        label: str = "DE_COMBINED",
    ) -> int:
        """
        Mengambil data harian Euro Area AAA Yield (10Y dan/atau 2Y) dari ECB Data Portal API.
        Mendukung query SDMX multi-key single-request (SR_10Y+SR_2Y) maupun URL single-series legacy.
        Returns: >= 0 (jumlah baris baru disimpan jika sukses), -1 jika gagal.
        """
        start_period = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%d")
        params = {"startPeriod": start_period, "format": "csvdata", "detail": "dataonly"}
        response = await fetch_with_retry(
            url=url,
            method="GET",
            params=params,
            timeout_seconds=12,
            max_retries=2,
            base_delay=1.0,
            headers={"Accept": "text/csv"},
            response_type="text",
            error_log_level=logging.WARNING,
        )
        if not response or not isinstance(response, str):
            return -1

        csv_text = response
        try:
            df = pd.read_csv(io.StringIO(csv_text))
        except Exception as e:
            logger.warning(f"Failed parsing ECB CSV: {e}")
            return -1

        if df.empty or "TIME_PERIOD" not in df.columns or "OBS_VALUE" not in df.columns:
            return -1

        has_dt_fm = "DATA_TYPE_FM" in df.columns
        if has_dt_fm:
            df = df.groupby("DATA_TYPE_FM").tail(60).reset_index(drop=True)
        elif len(df) > 60:
            df = df.tail(60)

        # Batch query existing dates for target tenors and persist within session lock
        target_tenors = ["DE_10Y", "DE_2Y"] if label == "DE_COMBINED" else [label]
        async with self._session_lock:
            existing_res = await self.session.execute(
                select(BondYieldData.country_tenor, BondYieldData.date).where(
                    BondYieldData.country_tenor.in_(target_tenors)
                )
            )
            existing_pairs = {(ct, d.strftime("%Y-%m-%d")) for ct, d in existing_res.all() if d is not None}

            saved = 0
            counts: dict[str, int] = {"DE_10Y": 0, "DE_2Y": 0}
            time_series = df["TIME_PERIOD"].to_numpy()
            obs_series = df["OBS_VALUE"].to_numpy()
            dt_series = df["DATA_TYPE_FM"].to_numpy() if has_dt_fm else None

            for i in range(len(df)):
                date_raw = time_series[i]
                val_raw = obs_series[i]
                try:
                    date_str = str(date_raw).strip()
                    if bool(pd.isna(val_raw)) or str(val_raw).strip() == ".":
                        continue
                    val = float(str(val_raw))

                    if dt_series is not None:
                        dt_fm = str(dt_series[i]).strip()
                        if dt_fm == "SR_2Y":
                            tenor = "DE_2Y"
                        elif dt_fm == "SR_10Y":
                            tenor = "DE_10Y"
                        elif label != "DE_COMBINED":
                            tenor = label
                        else:
                            tenor = "DE_10Y"
                    else:
                        tenor = label if label != "DE_COMBINED" else "DE_10Y"

                    if (tenor, date_str) in existing_pairs:
                        continue

                    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    self.session.add(BondYieldData(country_tenor=tenor, date=dt, yield_percent=val))
                    existing_pairs.add((tenor, date_str))
                    saved += 1
                    counts[tenor] = counts.get(tenor, 0) + 1
                except Exception:
                    continue

            self._last_ecb_counts = counts
            if saved:
                from monika.infrastructure.database.safe_ops import safe_commit

                await safe_commit(self.session, label="BondYield.ECB")

            return saved

    async def _fetch_fred_bond_series(self, series_id: str, label: str, limit: int = 15) -> int:
        """
        Mengambil data benchmark yield 10-tahun internasional dari FRED API.
        Returns: >= 0 (jumlah baris baru disimpan jika sukses), -1 jika gagal.
        """
        params = {
            "series_id": series_id,
            "api_key": self.fred_api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": str(limit),
        }
        data = await fetch_with_retry(FRED_BASE_URL, params=params, timeout=10, max_retries=2, base_delay=0.5)
        if not data or not isinstance(data, dict):
            return -1

        observations = data.get("observations", [])

        # Batch query existing dates in one query to avoid N roundtrips
        existing_res = await self.session.execute(
            select(BondYieldData.date).where(BondYieldData.country_tenor == label)
        )
        existing_date_strs = {d.strftime("%Y-%m-%d") for d in existing_res.scalars().all() if d is not None}

        saved = 0
        for obs in observations:
            date_str = str(obs.get("date", "")).strip()
            val_str = obs.get("value", ".")
            if not date_str or not val_str or val_str in (".", "ND", "nd"):
                continue

            try:
                val = float(val_str)
            except ValueError, TypeError:
                continue

            if date_str in existing_date_strs:
                continue

            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError, TypeError:
                continue

            self.session.add(BondYieldData(country_tenor=label, date=dt, yield_percent=val))
            existing_date_strs.add(date_str)
            saved += 1

        if saved:
            from monika.infrastructure.database.safe_ops import safe_commit

            await safe_commit(self.session, label=f"BondYield.{label}")

        return saved
