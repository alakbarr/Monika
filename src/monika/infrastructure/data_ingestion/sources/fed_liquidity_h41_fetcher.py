# ==============================================================================
# File: data_sources/fed_liquidity_h41_fetcher.py
# ==============================================================================

"""
Fed H.4.1 Balance Sheet & Real-Time Systemic Liquidity Engine (Async).
Ingests weekly Federal Reserve Factors Affecting Reserve Balances (H.4.1 release).
Calculates Fed Net Liquidity = WALCL - TGA - ON_RRP.
Persists records to `macro_liquidity_credit_metrics` table.
"""

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

import aiohttp
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from monika.core.primitives import clock
from monika.infrastructure.database.models import MacroLiquidityCreditMetric
from monika.infrastructure.database.safe_ops import safe_commit, safe_upsert

logger = logging.getLogger("TradingAgent.FedLiquidityH41Fetcher")

FRED_SERIES_WALCL = "WALCL"  # Total Assets of the Federal Reserve (in Millions)
FRED_SERIES_TGA = "WTREGEN"  # Treasury General Account at the Fed (in Millions)
FRED_SERIES_RRP = "RRPONTSYD"  # Overnight Reverse Repurchase Agreements (in Billions)


class FedLiquidityH41Fetcher:
    """Fetcher for Federal Reserve balance sheet metrics and Net Systemic Liquidity."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def fetch_and_store_liquidity(
        self,
        record_date: Optional[datetime] = None,
        walcl_override_b: Optional[float] = None,
        tga_override_b: Optional[float] = None,
        rrp_override_b: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Calculates Net Liquidity and persists individual components + Net Liquidity.
        Values are stored in USD Billions.
        Fetches live from official FRED API when overrides are not specified.
        """
        dt_record = record_date or clock.now()
        api_key = os.getenv("FRED_API_KEY", "")

        walcl = walcl_override_b
        tga = tga_override_b
        rrp = rrp_override_b

        # Live FRED Ingestion for H.4.1 Components
        if (walcl is None or tga is None or rrp is None) and api_key:
            try:
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                async with aiohttp.ClientSession(headers=headers) as http_client:
                    series_map = {
                        "WALCL": FRED_SERIES_WALCL,
                        "TGA": FRED_SERIES_TGA,
                        "RRP": FRED_SERIES_RRP,
                    }
                    fetched_vals = {}
                    for key, s_id in series_map.items():
                        url = f"https://api.stlouisfed.org/fred/series/observations?series_id={s_id}&api_key={api_key}&file_type=json&sort_order=desc&limit=2"
                        async with http_client.get(url, ssl=False, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                obs = data.get("observations", [])
                                if obs and obs[0].get("value"):
                                    try:
                                        fetched_vals[key] = float(obs[0]["value"])
                                    except ValueError, TypeError:
                                        pass

                    if walcl is None and "WALCL" in fetched_vals:
                        walcl = round(fetched_vals["WALCL"] / 1000.0, 2)  # Millions to Billions
                    if tga is None and "TGA" in fetched_vals:
                        tga = round(fetched_vals["TGA"] / 1000.0, 2)  # Millions to Billions
                    if rrp is None and "RRP" in fetched_vals:
                        rrp = round(fetched_vals["RRP"], 2)  # already Billions
                    logger.info(f"Live FRED H.4.1 Balance Sheet fetched: WALCL=${walcl}B, TGA=${tga}B, RRP=${rrp}B")
            except Exception as e:
                logger.warning(f"FRED H.4.1 live fetch failed: {e}")

        if walcl is None or tga is None or rrp is None:
            logger.warning(
                f"Fed H.4.1 balance sheet components incomplete (WALCL={walcl}, TGA={tga}, RRP={rrp}). Failing closed."
            )
            return {
                "status": "unavailable",
                "message": "Incomplete Federal Reserve H.4.1 balance sheet data",
            }

        net_liquidity = round(walcl - tga - rrp, 2)

        # Query prior record for FED_NET_LIQUIDITY to compute empirical delta
        stmt_prev_net = (
            select(MacroLiquidityCreditMetric)
            .where(
                MacroLiquidityCreditMetric.metric_type == "FED_NET_LIQUIDITY",
                MacroLiquidityCreditMetric.country == "US",
            )
            .order_by(MacroLiquidityCreditMetric.record_date.desc())
            .limit(1)
        )
        prev_net_rec = (await self.session.execute(stmt_prev_net)).scalars().first()
        prev_net = prev_net_rec.value if prev_net_rec else None
        diff_net = round(net_liquidity - prev_net, 2) if prev_net is not None else None
        regime = "EXPANSIONARY" if (diff_net is not None and diff_net >= 0) else "CONTRACTIONARY"

        # Query prior records for individual components
        components_to_process = [
            (
                "FED_WALCL",
                walcl,
                {"desc": "Fed Total Assets", "source": "FRED_Live"},
            ),
            (
                "FED_TGA",
                tga,
                {"desc": "Treasury General Account", "source": "FRED_Live"},
            ),
            (
                "FED_ON_RRP",
                rrp,
                {"desc": "Reverse Repo Facility", "source": "FRED_Live"},
            ),
        ]

        metrics = [
            (
                "FED_NET_LIQUIDITY",
                net_liquidity,
                prev_net,
                diff_net,
                regime,
                {"formula": "WALCL - TGA - RRP", "source": "FRED_H41_Live"},
            ),
        ]

        for comp_key, comp_val, meta_dict in components_to_process:
            stmt_comp_prev = (
                select(MacroLiquidityCreditMetric)
                .where(
                    MacroLiquidityCreditMetric.metric_type == comp_key,
                    MacroLiquidityCreditMetric.country == "US",
                )
                .order_by(MacroLiquidityCreditMetric.record_date.desc())
                .limit(1)
            )
            prev_comp_rec = (await self.session.execute(stmt_comp_prev)).scalars().first()
            p_val = prev_comp_rec.value if prev_comp_rec else None
            c_val = round(comp_val - p_val, 2) if p_val is not None else None

            if comp_key == "FED_WALCL":
                c_regime = "EXPANSIONARY" if (c_val is not None and c_val >= 0) else "CONTRACTIONARY"
            elif comp_key == "FED_TGA":
                c_regime = "CONTRACTIONARY" if comp_val > 800 else "EXPANSIONARY"
            else:  # FED_ON_RRP
                c_regime = "EXPANSIONARY" if comp_val < 250 else "CONTRACTIONARY"

            metrics.append((comp_key, comp_val, p_val, c_val, c_regime, meta_dict))

        inserted_records = []
        for m_type, val, prev, chg, reg, meta in metrics:
            rec = {
                "metric_type": m_type,
                "country": "US",
                "record_date": dt_record,
                "value": val,
                "previous_value": prev,
                "change_value": chg,
                "unit": "USD_BILLIONS",
                "regime": reg,
                "metadata_json": json.dumps(meta),
                "fetched_at": clock.now(),
            }

            await safe_upsert(
                session=self.session,
                model=MacroLiquidityCreditMetric,
                values=rec,
                index_elements=["metric_type", "country", "record_date"],
                update_cols=["value", "previous_value", "change_value", "regime", "metadata_json", "fetched_at"],
            )
            inserted_records.append(rec)

        await safe_commit(self.session)
        delta_str = f"{diff_net:+.1f}B" if diff_net is not None else "N/A"
        logger.info(f"Ingested Fed Net Liquidity: ${net_liquidity:,.1f}B (Regime: {regime}, Delta: {delta_str})")
        return {
            "status": "available",
            "net_liquidity_billions": net_liquidity,
            "regime": regime,
            "walcl_billions": walcl,
            "tga_billions": tga,
            "rrp_billions": rrp,
            "delta_billions": diff_net,
            "record_date": dt_record.isoformat(),
        }
