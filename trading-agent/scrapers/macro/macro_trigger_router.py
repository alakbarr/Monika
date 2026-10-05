# ==============================================================================
# File: scrapers/macro/macro_trigger_router.py
# ==============================================================================

"""
Macro Trigger Router (Async).
Coordinates automated ingestion across 3 trigger tiers:
1. Event-Driven Hook: Fired by economic calendar poller immediately upon data release.
2. Scheduled Meeting Timer: Scheduled checks for FOMC statements, minutes, and H.4.1.
3. Just-In-Time (JIT) Fallback: Triggered on-demand when chat queries find no records in DB.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import CentralBankDocument, EconomicReportDecomposition, MacroLiquidityCreditMetric
from scrapers.macro.central_bank_doc_scraper import CentralBankDocScraper
from scrapers.macro.generic_gov_stats_fetcher import GenericGovStatsFetcher
from data_sources.fed_liquidity_h41_fetcher import FedLiquidityH41Fetcher
from data_sources.leading_survey_fetcher import LeadingSurveyFetcher
from data_sources.market_stress_auction_fetcher import MarketStressAuctionFetcher
from utils import clock

logger = logging.getLogger("TradingAgent.MacroTriggerRouter")


class MacroTriggerRouter:
    """Central router managing automated and on-demand macro report fetching."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.gov_fetcher = GenericGovStatsFetcher(session)
        self.cb_scraper = CentralBankDocScraper(session)
        self.liq_fetcher = FedLiquidityH41Fetcher(session)
        self.survey_fetcher = LeadingSurveyFetcher(session)
        self.auction_fetcher = MarketStressAuctionFetcher(session)

    async def ensure_report_available(
        self,
        report_type: str,
        period: Optional[str] = None,
        country: str = "US",
        currency: str = "USD",
    ) -> List[Dict[str, Any]]:
        """
        Just-In-Time (JIT) on-demand fallback:
        Verifies if decomposition records exist in DB. If absent, fetches immediately on-the-fly.
        """
        rtype = report_type.upper()
        rep_period = period or clock.now().strftime("%Y-%m")

        stmt = select(func.count(EconomicReportDecomposition.id)).where(
            EconomicReportDecomposition.report_type == rtype,
            EconomicReportDecomposition.country == country,
            EconomicReportDecomposition.period == rep_period,
        )
        count = (await self.session.execute(stmt)).scalar() or 0

        if count > 0:
            logger.debug(f"Report {rtype} ({rep_period}) already exists in DB ({count} rows)")
            return []

        logger.info(f"JIT Trigger activated: Ingesting {rtype} ({rep_period}) on-the-fly...")
        if rtype in ("CPI", "NFP", "PCE", "PPI", "JOLTS"):
            return await self.gov_fetcher.fetch_and_store_report(
                report_type=rtype, period=rep_period, country=country, currency=currency
            )
        elif rtype in ("ISM_MANUFACTURING", "ISM_SERVICES", "UMICH", "CONF_BOARD"):
            return await self.survey_fetcher.fetch_and_store_surveys(period=rep_period)
        return []

    async def ensure_cb_document_available(
        self,
        bank: str = "FED",
        doc_type: str = "MINUTES",
    ) -> Optional[Dict[str, Any]]:
        """
        Just-In-Time (JIT) fallback for central bank documents.
        """
        bank_clean = bank.upper()
        doc_clean = doc_type.upper()

        stmt = select(func.count(CentralBankDocument.id)).where(
            CentralBankDocument.bank == bank_clean,
            CentralBankDocument.doc_type == doc_clean,
        )
        count = (await self.session.execute(stmt)).scalar() or 0

        if count >= 2:
            return None

        logger.info(f"JIT Trigger activated: Ingesting central bank document {bank_clean} {doc_clean} on-the-fly...")
        return await self.cb_scraper.fetch_and_store_document(bank=bank_clean, doc_type=doc_clean)

    async def ensure_liquidity_and_stress_available(self) -> Dict[str, Any]:
        """
        Just-In-Time (JIT) fallback for liquidity and credit stress.
        """
        stmt = select(func.count(MacroLiquidityCreditMetric.id)).where(
            MacroLiquidityCreditMetric.metric_type == "FED_NET_LIQUIDITY"
        )
        count = (await self.session.execute(stmt)).scalar() or 0

        if count > 0:
            return {}

        logger.info("JIT Trigger activated: Ingesting Fed Net Liquidity & Market Stress metrics on-the-fly...")
        await self.liq_fetcher.fetch_and_store_liquidity()
        await self.auction_fetcher.fetch_and_store_treasury_auction(tenor="10Y")
        await self.auction_fetcher.fetch_and_store_credit_and_money_market()
        return {"status": "ingested_jit"}

    async def on_calendar_event_released(self, event_title: str, country: str = "USD") -> bool:
        """
        Event-Driven Hook: Automatically called by calendar scrapers when an actual event is published.
        """
        title_lower = event_title.lower()
        if "cpi" in title_lower or "consumer price" in title_lower:
            await self.gov_fetcher.fetch_and_store_report("CPI", country="US")
            return True
        elif "non-farm" in title_lower or "nfp" in title_lower or "payrolls" in title_lower:
            await self.gov_fetcher.fetch_and_store_report("NFP", country="US")
            return True
        elif "pce" in title_lower:
            await self.gov_fetcher.fetch_and_store_report("PCE", country="US")
            return True
        elif "ism" in title_lower:
            await self.survey_fetcher.fetch_and_store_surveys()
            return True
        elif "fomc" in title_lower or "fed interest rate" in title_lower or "federal funds rate" in title_lower:
            await self.cb_scraper.fetch_and_store_document("FED", "STATEMENT")
            return True
        elif "ecb interest rate" in title_lower or "monetary policy statement" in title_lower:
            await self.cb_scraper.fetch_and_store_document("ECB", "STATEMENT")
            return True
        elif "boj interest rate" in title_lower or "boj monetary policy" in title_lower:
            await self.cb_scraper.fetch_and_store_document("BOJ", "STATEMENT")
            return True
        elif "fomc minutes" in title_lower or "meeting minutes" in title_lower:
            await self.cb_scraper.fetch_and_store_document("FED", "MINUTES")
            return True
        return False
