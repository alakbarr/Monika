# ==============================================================================
# File: data_sources/leading_survey_fetcher.py
# ==============================================================================

"""
Leading Surveys & Market Sentiment Ingestion Engine (Async).
Ingests ISM Manufacturing & Services PMIs (Prices Paid, New Orders),
University of Michigan Inflation Expectations, and Consumer Sentiment.
Persists records to `economic_report_decompositions` table.
"""

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiohttp
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from monika.core.primitives import clock
from monika.infrastructure.llm.rate_limiting.http_retry import _DEFAULT_SSL_CONTEXT
from monika.infrastructure.database.models import EconomicReportDecomposition
from monika.infrastructure.database.safe_ops import safe_commit, safe_upsert

logger = logging.getLogger("TradingAgent.LeadingSurveyFetcher")

FRED_API_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"


class LeadingSurveyFetcher:
    """Fetcher for leading macroeconomic surveys and consumer inflation expectations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def fetch_and_store_surveys(
        self,
        period: Optional[str] = None,
        release_date: Optional[datetime] = None,
        survey_metrics: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """Ingests leading survey breakdowns.

        Fetches live survey series from FRED when available (e.g., UMich Sentiment & Inflation Expectations),
        or ingests provided real survey metrics from event-driven scrapers.
        Fails closed with an empty list if data is unavailable — never injects fake numbers.
        """
        dt_now = clock.now()
        rel_date = release_date or dt_now
        rep_period = period or rel_date.strftime("%Y-%m")

        items_to_store: List[Dict[str, Any]] = []

        if survey_metrics:
            for item in survey_metrics:
                items_to_store.append(item)
        else:
            api_key = os.getenv("FRED_API_KEY", "")
            if api_key:
                fred_surveys = [
                    {
                        "series_id": "UMCSENT",
                        "report_type": "UMICH",
                        "component_name": "UMich Consumer Sentiment Index",
                        "category": "leading",
                        "unit": "index_score",
                    },
                    {
                        "series_id": "MICH",
                        "report_type": "UMICH",
                        "component_name": "UMich 1-Year Inflation Expectation",
                        "category": "leading",
                        "unit": "percent",
                    },
                ]
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                try:
                    async with aiohttp.ClientSession(headers=headers) as http_client:
                        for s_cfg in fred_surveys:
                            url = f"{FRED_API_BASE_URL}?series_id={s_cfg['series_id']}&api_key={api_key}&file_type=json&sort_order=desc&limit=2"
                            try:
                                async with http_client.get(
                                    url, ssl=_DEFAULT_SSL_CONTEXT, timeout=aiohttp.ClientTimeout(total=8)
                                ) as resp:
                                    if resp.status == 200:
                                        data = await resp.json()
                                        obs = data.get("observations", [])
                                        if len(obs) >= 1 and obs[0].get("value"):
                                            v_act = float(obs[0]["value"])
                                            v_prev = (
                                                float(obs[1]["value"])
                                                if len(obs) >= 2 and obs[1].get("value")
                                                else None
                                            )
                                            mom = round(v_act - v_prev, 2) if v_prev is not None else None
                                            items_to_store.append(
                                                {
                                                    "report_type": s_cfg["report_type"],
                                                    "country": "US",
                                                    "currency": "USD",
                                                    "component_name": s_cfg["component_name"],
                                                    "category": s_cfg["category"],
                                                    "weight_pct": 100.0
                                                    if "Headline" in s_cfg["component_name"]
                                                    else None,
                                                    "value_actual": v_act,
                                                    "value_forecast": None,
                                                    "value_previous": v_prev,
                                                    "mom_change": mom,
                                                    "yoy_change": None,
                                                    "contribution_bps": None,
                                                    "is_noise": False,
                                                    "unit": s_cfg["unit"],
                                                    "source": "FRED_Live",
                                                }
                                            )
                            except Exception as req_err:
                                logger.debug(f"Failed to fetch FRED survey {s_cfg['series_id']}: {req_err}")
                except Exception as net_err:
                    logger.warning(f"Live FRED survey fetch connection error: {net_err}")

        if not items_to_store:
            logger.info(f"No leading survey metrics available to ingest for period {rep_period}. Failing closed.")
            return []

        results = []
        for item in items_to_store:
            rec = {
                "report_type": item["report_type"],
                "country": item.get("country", "US"),
                "currency": item.get("currency", "USD"),
                "period": rep_period,
                "release_date": rel_date,
                "component_name": item["component_name"],
                "category": item.get("category", "leading"),
                "weight_pct": item.get("weight_pct"),
                "value_actual": item.get("value_actual"),
                "value_forecast": item.get("value_forecast"),
                "value_previous": item.get("value_previous"),
                "mom_change": item.get("mom_change"),
                "yoy_change": item.get("yoy_change"),
                "contribution_bps": item.get("contribution_bps"),
                "is_noise": item.get("is_noise", False),
                "metadata_json": json.dumps(
                    {"unit": item.get("unit"), "source": item.get("source", "LeadingSurveyEngine")}
                ),
                "fetched_at": dt_now,
            }

            await safe_upsert(
                session=self.session,
                model=EconomicReportDecomposition,
                values=rec,
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
            results.append(rec)

        await safe_commit(self.session)
        logger.info(f"Ingested {len(results)} authentic leading survey metrics ({rep_period})")
        return results

    async def get_global_pmi_summary(self, period: Optional[str] = None) -> Dict[str, Any]:
        """
        Retrieves and evaluates Global and regional manufacturing PMI trends.
        Answers: Is global factory activity expanding or contracting? What are regional drivers?
        """
        rep_period = period or clock.now().strftime("%Y-%m")
        stmt = select(EconomicReportDecomposition).where(
            EconomicReportDecomposition.report_type == "GLOBAL_PMI",
            EconomicReportDecomposition.period == rep_period,
        )
        records = (await self.session.execute(stmt)).scalars().all()
        if not records:
            await self.fetch_and_store_surveys(period=rep_period)
            records = (await self.session.execute(stmt)).scalars().all()

        if not records:
            return {
                "period": rep_period,
                "status": "unavailable",
                "global_composite_pmi": None,
                "global_regime": "UNKNOWN",
                "regional_breakdown": {},
                "institutional_implication": f"No global PMI survey data available for period {rep_period}.",
            }

        pmi_breakdown = {}
        global_pmi_val: Optional[float] = None
        for r in records:
            val_act = r.value_actual
            status = "EXPANSION" if (val_act is not None and val_act >= 50.0) else "CONTRACTION"
            pmi_breakdown[r.component_name] = {
                "country": r.country,
                "currency": r.currency,
                "actual": val_act,
                "previous": r.value_previous,
                "mom_change": r.mom_change,
                "status": status,
            }
            if "Global" in r.component_name and r.country == "GLOBAL":
                global_pmi_val = val_act

        if global_pmi_val is None:
            actual_vals = [d["actual"] for d in pmi_breakdown.values() if d["actual"] is not None]
            global_pmi_val = round(sum(actual_vals) / len(actual_vals), 1) if actual_vals else None

        if global_pmi_val is None:
            return {
                "period": rep_period,
                "status": "unavailable",
                "global_composite_pmi": None,
                "global_regime": "UNKNOWN",
                "regional_breakdown": pmi_breakdown,
                "institutional_implication": f"Incomplete PMI values for period {rep_period}.",
            }

        regime = "EXPANSION (>50)" if global_pmi_val >= 50.0 else "CONTRACTION (<50)"
        expanding_regions = [
            d["country"] for d in pmi_breakdown.values() if d["status"] == "EXPANSION" and d["country"] != "GLOBAL"
        ]
        contracting_regions = [
            d["country"] for d in pmi_breakdown.values() if d["status"] == "CONTRACTION" and d["country"] != "GLOBAL"
        ]

        verdict_parts = [f"Global manufacturing sits at {global_pmi_val:.1f} in {regime.lower()}."]
        if expanding_regions:
            verdict_parts.append(f"Expansionary resilience observed in {', '.join(expanding_regions)}.")
        if contracting_regions:
            verdict_parts.append(f"Contraction drag observed in {', '.join(contracting_regions)}.")

        return {
            "period": rep_period,
            "status": "available",
            "global_composite_pmi": global_pmi_val,
            "global_regime": regime,
            "regional_breakdown": pmi_breakdown,
            "institutional_implication": " ".join(verdict_parts),
        }
