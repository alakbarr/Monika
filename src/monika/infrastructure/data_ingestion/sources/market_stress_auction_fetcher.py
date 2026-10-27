# ==============================================================================
# File: data_sources/market_stress_auction_fetcher.py
# ==============================================================================

"""
Market Stress, Treasury Auctions & Foreign Capital Flows Ingestion Engine (Async).
Ingests US Treasury auction tails, Bid-to-Cover, foreign indirect bidding demand,
ICE BofA US High Yield Option-Adjusted Spread (HY OAS), and SOFR.
Persists records to `macro_liquidity_credit_metrics` table.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import aiohttp
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from monika.core.primitives import clock
from monika.infrastructure.llm.rate_limiting.http_retry import _DEFAULT_SSL_CONTEXT
from monika.infrastructure.database.models import MacroLiquidityCreditMetric
from monika.infrastructure.database.safe_ops import safe_commit, safe_upsert

logger = logging.getLogger("TradingAgent.MarketStressAuctionFetcher")

TREASURY_DIRECT_API = "https://www.treasurydirect.gov/TA_WS/securities/auctioned?format=json"

TENOR_TERM_MAP = {
    "2Y": "2-Year",
    "3Y": "3-Year",
    "5Y": "5-Year",
    "7Y": "7-Year",
    "10Y": "10-Year",
    "20Y": "20-Year",
    "30Y": "30-Year",
}


class MarketStressAuctionFetcher:
    """Fetcher for debt auctions, credit risk spreads, and money market funding stress."""

    def __init__(self, session: AsyncSession, api_key: Optional[str] = None):
        self.session = session
        self.api_key = api_key

    async def fetch_and_store_treasury_auction(
        self,
        tenor: str = "10Y",
        record_date: Optional[datetime] = None,
        high_yield: Optional[float] = None,
        when_issued_yield: Optional[float] = None,
        bid_to_cover: Optional[float] = None,
        indirect_bidder_pct: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Fetches live Treasury auction results from TreasuryDirect API or stores provided results,
        including auction tail, bid-to-cover, and foreign indirect bidder demand.
        Fails closed if auction yield is unavailable — never fabricates fallback yields.
        """
        tenor_clean = tenor.strip().upper()
        target_term = TENOR_TERM_MAP.get(tenor_clean, f"{tenor_clean}-Year")
        dt_record = record_date

        h_yield = high_yield
        wi_yield = when_issued_yield
        b_cover = bid_to_cover
        ind_pct = indirect_bidder_pct

        # Live TreasuryDirect Ingestion if values are not provided
        if h_yield is None or b_cover is None or ind_pct is None:
            try:
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                async with aiohttp.ClientSession(headers=headers) as http_client:
                    async with http_client.get(
                        TREASURY_DIRECT_API, ssl=_DEFAULT_SSL_CONTEXT, timeout=aiohttp.ClientTimeout(total=12)
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json(content_type=None)
                            if isinstance(data, list):
                                # Filter notes/bonds matching tenor
                                candidates = [
                                    d
                                    for d in data
                                    if d.get("securityType") in ("Note", "Bond", "TIPS")
                                    and d.get("securityTerm") == target_term
                                ]
                                if candidates:
                                    top = candidates[0]
                                    if h_yield is None and top.get("highYield"):
                                        try:
                                            h_yield = float(top["highYield"])
                                        except ValueError, TypeError:
                                            pass
                                    if b_cover is None and top.get("bidToCoverRatio"):
                                        try:
                                            b_cover = float(top["bidToCoverRatio"])
                                        except ValueError, TypeError:
                                            pass
                                    if ind_pct is None:
                                        total_acc = float(top.get("totalAccepted") or 0)
                                        ind_acc = float(top.get("indirectBidderAccepted") or 0)
                                        if total_acc > 0 and ind_acc > 0:
                                            ind_pct = round((ind_acc / total_acc) * 100.0, 1)
                                    if dt_record is None and top.get("issueDate"):
                                        try:
                                            dt_record = datetime.fromisoformat(top["issueDate"]).replace(
                                                tzinfo=timezone.utc
                                            )
                                        except Exception:
                                            pass
                                    logger.info(
                                        f"Live TreasuryDirect fetched for {tenor_clean} ({target_term}): Yield={h_yield}%, BTC={b_cover}, Indirect={ind_pct}%"
                                    )
            except Exception as e:
                logger.warning(f"TreasuryDirect live fetch failed: {e}")

        if h_yield is None:
            logger.warning(f"Treasury auction data unavailable for {tenor_clean}. Failing closed.")
            return {
                "status": "unavailable",
                "metric_type": f"TREASURY_AUCTION_{tenor_clean}",
                "message": f"Auction yield unavailable for {tenor_clean}",
            }

        tail_bps = round((h_yield - wi_yield) * 100.0, 2) if wi_yield is not None else None
        dt_record = dt_record or clock.now()

        regime = "NORMAL"
        if tail_bps is not None and ind_pct is not None:
            if tail_bps <= 0.0 and ind_pct >= 65.0:
                regime = "STRONG_DEMAND"
            elif tail_bps > 1.0:
                regime = "WEAK_TAIL"

        meta = {
            "tenor": tenor_clean,
            "when_issued_yield": wi_yield,
            "tail_bps": tail_bps,
            "bid_to_cover": b_cover,
            "indirect_bidder_pct": ind_pct,
            "dealer_pct": round(max(0.0, 100.0 - ind_pct - 15.0), 1) if ind_pct is not None else None,
            "source": "TreasuryDirect_Live",
        }

        metric_key = f"TREASURY_AUCTION_{tenor_clean}"

        stmt_prev = (
            select(MacroLiquidityCreditMetric)
            .where(
                MacroLiquidityCreditMetric.metric_type == metric_key,
                MacroLiquidityCreditMetric.country == "US",
            )
            .order_by(MacroLiquidityCreditMetric.record_date.desc())
            .limit(1)
        )
        prev_record = (await self.session.execute(stmt_prev)).scalars().first()
        prev_val = prev_record.value if prev_record else None
        chg_val = round(h_yield - prev_val, 3) if prev_val is not None else None

        rec = {
            "metric_type": metric_key,
            "country": "US",
            "record_date": dt_record,
            "value": h_yield,
            "previous_value": prev_val,
            "change_value": chg_val,
            "unit": "PERCENT",
            "regime": regime,
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
        await safe_commit(self.session)

        tail_str = f"{tail_bps:+.1f} bps" if tail_bps is not None else "N/A"
        ind_str = f"{ind_pct:.1f}%" if ind_pct is not None else "N/A"
        logger.info(f"Ingested {metric_key} Auction: High Yield {h_yield:.3f}%, Tail {tail_str}, Indirects {ind_str}")
        return rec

    async def fetch_and_store_credit_and_money_market(
        self,
        record_date: Optional[datetime] = None,
        hy_oas_override: Optional[float] = None,
        sofr_override: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Stores ICE BofA High Yield OAS credit spreads and SOFR overnight rate.
        Fetches live from FRED API if available. Fails closed if data is unavailable.
        """
        dt_record = record_date or clock.now()
        api_key = self.api_key or os.getenv("FRED_API_KEY", "")

        hy_oas = hy_oas_override
        sofr = sofr_override

        # Live FRED Ingestion for Credit Risk & Overnight Funding
        if (hy_oas is None or sofr is None) and api_key:
            try:
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                async with aiohttp.ClientSession(headers=headers) as http_client:
                    if hy_oas is None:
                        url_hy = f"https://api.stlouisfed.org/fred/series/observations?series_id=BAMLH0A0HYM2&api_key={api_key}&file_type=json&sort_order=desc&limit=2"
                        async with http_client.get(
                            url_hy, ssl=_DEFAULT_SSL_CONTEXT, timeout=aiohttp.ClientTimeout(total=10)
                        ) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                obs = data.get("observations", [])
                                if obs and obs[0].get("value"):
                                    try:
                                        hy_oas = round(float(obs[0]["value"]) * 100.0, 1)  # percent to bps
                                        logger.info(f"Live FRED HY OAS fetched: {hy_oas} bps")
                                    except ValueError, TypeError:
                                        pass

                    if sofr is None:
                        url_sofr = f"https://api.stlouisfed.org/fred/series/observations?series_id=SOFR&api_key={api_key}&file_type=json&sort_order=desc&limit=2"
                        async with http_client.get(
                            url_sofr, ssl=_DEFAULT_SSL_CONTEXT, timeout=aiohttp.ClientTimeout(total=10)
                        ) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                obs = data.get("observations", [])
                                if obs and obs[0].get("value"):
                                    try:
                                        sofr = round(float(obs[0]["value"]), 2)
                                        logger.info(f"Live FRED SOFR fetched: {sofr}%")
                                    except ValueError, TypeError:
                                        pass
            except Exception as e:
                logger.warning(f"FRED live credit fetch failed: {e}")

        items = []
        if hy_oas is not None:
            # Query prior DB record
            stmt_prev_hy = (
                select(MacroLiquidityCreditMetric)
                .where(
                    MacroLiquidityCreditMetric.metric_type == "ICE_BOFA_HY_OAS",
                    MacroLiquidityCreditMetric.country == "US",
                )
                .order_by(MacroLiquidityCreditMetric.record_date.desc())
                .limit(1)
            )
            prev_hy_rec = (await self.session.execute(stmt_prev_hy)).scalars().first()
            prev_hy_val = prev_hy_rec.value if prev_hy_rec else None
            chg_hy = round(hy_oas - prev_hy_val, 1) if prev_hy_val is not None else None
            credit_regime = "STRESS" if hy_oas > 450.0 else ("ELEVATED" if hy_oas > 380.0 else "BENIGN")
            items.append(
                (
                    "ICE_BOFA_HY_OAS",
                    hy_oas,
                    prev_hy_val,
                    chg_hy,
                    "BPS",
                    credit_regime,
                    {"threshold_stress": 450.0, "source": "FRED_Live"},
                )
            )

        if sofr is not None:
            stmt_prev_sofr = (
                select(MacroLiquidityCreditMetric)
                .where(
                    MacroLiquidityCreditMetric.metric_type == "SOFR_RATE",
                    MacroLiquidityCreditMetric.country == "US",
                )
                .order_by(MacroLiquidityCreditMetric.record_date.desc())
                .limit(1)
            )
            prev_sofr_rec = (await self.session.execute(stmt_prev_sofr)).scalars().first()
            prev_sofr_val = prev_sofr_rec.value if prev_sofr_rec else None
            chg_sofr = round(sofr - prev_sofr_val, 2) if prev_sofr_val is not None else None
            items.append(
                (
                    "SOFR_RATE",
                    sofr,
                    prev_sofr_val,
                    chg_sofr,
                    "PERCENT",
                    "BENIGN",
                    {"desc": "Secured Overnight Financing Rate", "source": "FRED_Live"},
                )
            )

        if not items:
            logger.info("No credit and money market metrics available. Failing closed.")
            return []

        inserted = []
        for m_type, val, prev, chg, unit, reg, meta in items:
            rec = {
                "metric_type": m_type,
                "country": "US",
                "record_date": dt_record,
                "value": val,
                "previous_value": prev,
                "change_value": chg,
                "unit": unit,
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
            inserted.append(rec)

        await safe_commit(self.session)
        logger.info(f"Ingested {len(inserted)} Market Credit & Funding Metrics")
        return inserted
