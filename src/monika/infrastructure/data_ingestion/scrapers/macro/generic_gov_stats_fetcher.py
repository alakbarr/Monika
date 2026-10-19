# ==============================================================================
# File: scrapers/macro/generic_gov_stats_fetcher.py
# ==============================================================================

"""
Generic Government Macro Statistics Fetcher (Async).
Ingests granular economic report decompositions from BLS, BEA, FRED, and global statistical agencies.
Persists records to `economic_report_decompositions` table.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from monika.core.primitives import clock
from monika.infrastructure.api.http_retry import _DEFAULT_SSL_CONTEXT
from monika.infrastructure.database.models import EconomicReportDecomposition
from monika.infrastructure.database.safe_ops import safe_commit, safe_upsert

logger = logging.getLogger("TradingAgent.GenericGovStatsFetcher")

FRED_API_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

# Sub-component mapping for comprehensive institutional decomposition
REPORT_COMPONENT_MAP: Dict[str, List[Dict[str, Any]]] = {
    "CPI": [
        {"name": "Headline CPI", "category": "headline", "weight": 100.0, "is_noise": False, "series_id": "CPIAUCSL"},
        {"name": "Core CPI", "category": "core", "weight": 79.5, "is_noise": False, "series_id": "CPILFESL"},
        {
            "name": "Shelter / Rent",
            "category": "sticky",
            "weight": 36.2,
            "is_noise": False,
            "series_id": "CUSR0000SEHA",
        },
        {
            "name": "Owners' Equivalent Rent (OER)",
            "category": "sticky",
            "weight": 26.8,
            "is_noise": False,
            "series_id": "CUSR0000SEHC",
        },
        {"name": "Energy", "category": "transitory", "weight": 6.9, "is_noise": True, "series_id": "CPIENGSL"},
        {"name": "Food & Beverages", "category": "sticky", "weight": 13.5, "is_noise": False, "series_id": "CPIUFDSL"},
        {
            "name": "Used Cars and Trucks",
            "category": "transitory",
            "weight": 2.1,
            "is_noise": True,
            "series_id": "CUSR0000SETA02",
        },
        {
            "name": "Transportation Services",
            "category": "core",
            "weight": 6.5,
            "is_noise": False,
            "series_id": "CUSR0000SAS4",
        },
        {
            "name": "Medical Care Services",
            "category": "sticky",
            "weight": 6.8,
            "is_noise": False,
            "series_id": "CUSR0000SAM2",
        },
        {
            "name": "Supercore Services (Services ex-Shelter)",
            "category": "core",
            "weight": 24.3,
            "is_noise": False,
            "series_id": "CUSR0000SASLE",
        },
    ],
    "NFP": [
        {
            "name": "Total Nonfarm Payroll",
            "category": "headline",
            "weight": 100.0,
            "is_noise": False,
            "series_id": "PAYEMS",
        },
        {"name": "Private Payrolls", "category": "core", "weight": 85.0, "is_noise": False, "series_id": "USPRIV"},
        {
            "name": "Government Payrolls",
            "category": "transitory",
            "weight": 15.0,
            "is_noise": True,
            "series_id": "USGOVT",
        },
        {
            "name": "Household Survey Employment",
            "category": "leading",
            "weight": 100.0,
            "is_noise": False,
            "series_id": "LNS12000000",
        },
        {
            "name": "2-Month Net Payroll Revision",
            "category": "revision",
            "weight": 0.0,
            "is_noise": False,
            "series_id": "REVISION_NET",
        },
        {
            "name": "Average Hourly Earnings (MoM)",
            "category": "core",
            "weight": 0.0,
            "is_noise": False,
            "series_id": "CES0500000003",
        },
        {
            "name": "Average Weekly Hours",
            "category": "leading",
            "weight": 0.0,
            "is_noise": False,
            "series_id": "AWHAETP",
        },
        {
            "name": "U-3 Unemployment Rate",
            "category": "headline",
            "weight": 0.0,
            "is_noise": False,
            "series_id": "UNRATE",
        },
        {
            "name": "U-6 Underemployment Rate",
            "category": "core",
            "weight": 0.0,
            "is_noise": False,
            "series_id": "U6RATE",
        },
    ],
    "PCE": [
        {
            "name": "Headline PCE Price Index",
            "category": "headline",
            "weight": 100.0,
            "is_noise": False,
            "series_id": "PCEPI",
        },
        {
            "name": "Core PCE Price Index (Fed Target)",
            "category": "core",
            "weight": 82.0,
            "is_noise": False,
            "series_id": "PCEPILFE",
        },
        {
            "name": "PCE Services ex-Energy & Housing",
            "category": "sticky",
            "weight": 50.0,
            "is_noise": False,
            "series_id": "PCE_SUPERCORE",
        },
    ],
    "PPI": [
        {"name": "Final Demand PPI", "category": "headline", "weight": 100.0, "is_noise": False, "series_id": "PPIFIS"},
        {
            "name": "Core PPI (ex-Food & Energy)",
            "category": "core",
            "weight": 75.0,
            "is_noise": False,
            "series_id": "PPIFES",
        },
        {
            "name": "Final Demand Services",
            "category": "sticky",
            "weight": 65.0,
            "is_noise": False,
            "series_id": "WPSFD41",
        },
    ],
    "JOLTS": [
        {
            "name": "Total Job Openings",
            "category": "leading",
            "weight": 100.0,
            "is_noise": False,
            "series_id": "JTSJOL",
        },
        {
            "name": "Quits Rate (Wage Pressure Proxy)",
            "category": "core",
            "weight": 0.0,
            "is_noise": False,
            "series_id": "JTSQUR",
        },
        {
            "name": "Layoffs and Discharges",
            "category": "leading",
            "weight": 0.0,
            "is_noise": False,
            "series_id": "JTSLDR",
        },
    ],
}


class GenericGovStatsFetcher:
    """Ingestion engine for granular macro report breakdowns."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def fetch_and_store_report(
        self,
        report_type: str,
        period: Optional[str] = None,
        country: str = "US",
        currency: str = "USD",
        release_date: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch report sub-components (with live FRED series data where available)
        and upsert into database.
        """
        rtype = report_type.upper()
        if rtype not in REPORT_COMPONENT_MAP:
            logger.warning(f"Unsupported report type for decomposition: {rtype}")
            return []

        dt_now = clock.now()
        rel_date = release_date or dt_now
        rep_period = period or rel_date.strftime("%Y-%m")

        components = REPORT_COMPONENT_MAP[rtype]
        live_series_data = await self._fetch_live_fred_series(components)

        results = []
        for comp in components:
            val_actual, val_forecast, val_previous, mom, yoy, contrib = self._calculate_subcomponent_values(
                rtype, comp["name"], comp["category"], comp.get("series_id"), live_series_data
            )
            if val_actual is None:
                continue

            source_tag = "FRED_Live" if comp.get("series_id") in live_series_data else "GovStatsEngine"
            record = {
                "report_type": rtype,
                "country": country,
                "currency": currency,
                "period": rep_period,
                "release_date": rel_date,
                "component_name": comp["name"],
                "category": comp["category"],
                "weight_pct": comp.get("weight"),
                "value_actual": val_actual,
                "value_forecast": val_forecast,
                "value_previous": val_previous,
                "mom_change": mom,
                "yoy_change": yoy,
                "contribution_bps": contrib,
                "is_noise": comp.get("is_noise", False),
                "metadata_json": json.dumps({"series_id": comp.get("series_id"), "source": source_tag}),
                "fetched_at": dt_now,
            }

            await safe_upsert(
                session=self.session,
                model=EconomicReportDecomposition,
                values=record,
                index_elements=["report_type", "country", "period", "component_name"],
                update_cols=[
                    "value_actual",
                    "value_forecast",
                    "value_previous",
                    "mom_change",
                    "yoy_change",
                    "contribution_bps",
                    "is_noise",
                    "metadata_json",
                    "fetched_at",
                ],
            )
            results.append(record)

        if results:
            await safe_commit(self.session)
            logger.info(f"Ingested {len(results)} authentic decomposition components for {rtype} ({rep_period})")
        else:
            logger.info(f"No live decomposition data available for {rtype} ({rep_period}). Failing closed.")
        return results

    async def _fetch_live_fred_series(self, components: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """Fetch live observations from FRED for series mapped to components."""
        api_key = os.getenv("FRED_API_KEY", "")
        if not api_key:
            return {}

        results = {}
        # Limit live queries to primary 3 key series per report to ensure ultra-fast execution
        key_series = [c["series_id"] for c in components if c.get("series_id")][:4]

        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            async with aiohttp.ClientSession(headers=headers) as http_client:
                for s_id in key_series:
                    if not s_id or s_id in ("REVISION_NET", "PCE_SUPERCORE"):
                        continue
                    url = (
                        f"{FRED_API_BASE_URL}?series_id={s_id}&api_key={api_key}&file_type=json&sort_order=desc&limit=3"
                    )
                    try:
                        async with http_client.get(
                            url, ssl=_DEFAULT_SSL_CONTEXT, timeout=aiohttp.ClientTimeout(total=8)
                        ) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                obs = data.get("observations", [])
                                if len(obs) >= 2:
                                    v0 = float(obs[0]["value"])
                                    v1 = float(obs[1]["value"])
                                    results[s_id] = {
                                        "latest_val": v0,
                                        "prev_val": v1,
                                        "latest_date": obs[0]["date"],
                                    }
                    except Exception:
                        pass
        except Exception as e:
            logger.debug(f"FRED live decomposition query exception: {e}")

        return results

    def _calculate_subcomponent_values(
        self,
        rtype: str,
        comp_name: str,
        category: str,
        series_id: Optional[str] = None,
        live_data: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Tuple[
        Optional[float],
        Optional[float],
        Optional[float],
        Optional[float],
        Optional[float],
        Optional[float],
    ]:
        """
        Determines consistent and realistic quantitative metrics for report breakdown,
        incorporating live FRED observations if available.
        Fails closed with (None, ...) if live data is not available.
        """
        live_data = live_data or {}
        if series_id and series_id in live_data:
            ld = live_data[series_id]
            v0 = ld["latest_val"]
            v1 = ld["prev_val"]

            if rtype == "CPI":
                if v1 != 0.0:
                    mom = round(((v0 - v1) / v1) * 100.0, 2)
                else:
                    mom = 0.0
                weight = 100.0 if "Headline" in comp_name else 79.5
                contrib = round(mom * weight / 100.0, 1)
                return mom, None, None, mom, None, contrib

            elif rtype == "NFP":
                if "Total Nonfarm" in comp_name or "Private" in comp_name:
                    change_k = round(v0 - v1, 1)
                    return change_k, None, None, change_k, None, change_k
                elif "Unemployment Rate" in comp_name:
                    mom = round(v0 - v1, 2)
                    return v0, None, v1, mom, None, None

            elif rtype == "PCE":
                if v1 != 0.0:
                    mom = round(((v0 - v1) / v1) * 100.0, 2)
                else:
                    mom = 0.0
                return mom, None, None, mom, None, None

            elif rtype in ("PPI", "JOLTS"):
                mom = round(v0 - v1, 2)
                return v0, None, v1, mom, None, None

        return None, None, None, None, None, None
