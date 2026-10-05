# ==============================================================================
# File: tests/test_live_macro_fetching.py
# ==============================================================================

"""
Live Verification Test Suite for Universal Macro Ingestion & Central Bank Scrapers.
Proves empirical, real-world data fetching from:
1. TreasuryDirect API (US Treasury Auctions: High Yield, Tails, Indirect Bidder Demand)
2. Federal Reserve H.4.1 Balance Sheet via FRED (WALCL, WTREGEN TGA, RRPONTSYD)
3. Granular Macro Economic Reports (CPI, NFP Decomposition from BLS via FRED)
4. Central Bank Portals (Federal Reserve FOMC, ECB Governing Council, Bank of Japan)
5. Universal Calculators (Decomposition, Redline Differ, Net Liquidity & Stress)
"""

import asyncio
import os
import pytest
from datetime import datetime, timezone
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

load_dotenv()

from database.models import (
    Base,
    EconomicReportDecomposition,
    CentralBankDocument,
    MacroLiquidityCreditMetric,
)
from data_sources.market_stress_auction_fetcher import MarketStressAuctionFetcher
from data_sources.fed_liquidity_h41_fetcher import FedLiquidityH41Fetcher
from scrapers.macro.generic_gov_stats_fetcher import GenericGovStatsFetcher
from scrapers.macro.central_bank_doc_scraper import CentralBankDocScraper
from analysis.calculators.universal_macro_analyzer import UniversalMacroAnalyzer
from analysis.calculators.universal_cb_differ import UniversalCentralBankDiffer
from analysis.calculators.universal_liquidity_analyzer import UniversalLiquidityAnalyzer


@pytest.fixture
def db_session_factory():
    """Create async session factory connected to local PostgreSQL database."""
    raw_url = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL", "")
    db_url = raw_url if raw_url.startswith("postgresql") else "postgresql+asyncpg://postgres:postgres@localhost:5432/market_intelligence"
    engine = create_async_engine(db_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    return session_factory, engine


@pytest.mark.asyncio
async def test_live_treasury_auction_and_market_stress(db_session_factory):
    """Test live TreasuryDirect API auction ingestion & FRED credit metrics."""
    session_factory, engine = db_session_factory
    async with session_factory() as session:
        fetcher = MarketStressAuctionFetcher(session)

        # 1. Fetch live 10Y Treasury auction
        auction_res = await fetcher.fetch_and_store_treasury_auction(tenor="10Y")
        assert auction_res is not None
        assert auction_res["metric_type"] == "TREASURY_AUCTION_10Y"
        assert auction_res["value"] > 0.0
        assert "regime" in auction_res
        print(f"\n[LIVE TEST] 10Y Treasury Auction: High Yield={auction_res['value']}%, Regime={auction_res['regime']}")

        # 2. Fetch live Credit & Money Market metrics (HY OAS & SOFR from FRED)
        stress_res = await fetcher.fetch_and_store_credit_and_money_market()
        assert len(stress_res) >= 2
        hy_metric = next(m for m in stress_res if m["metric_type"] == "ICE_BOFA_HY_OAS")
        sofr_metric = next(m for m in stress_res if m["metric_type"] == "SOFR_RATE")
        assert hy_metric["value"] > 0.0
        assert sofr_metric["value"] > 0.0
        print(f"[LIVE TEST] Credit & Funding Stress: HY OAS={hy_metric['value']} bps, SOFR={sofr_metric['value']}%")

    await engine.dispose()


@pytest.mark.asyncio
async def test_live_fed_net_liquidity(db_session_factory):
    """Test live Federal Reserve H.4.1 balance sheet ingestion from FRED."""
    session_factory, engine = db_session_factory
    async with session_factory() as session:
        fetcher = FedLiquidityH41Fetcher(session)
        res = await fetcher.fetch_and_store_liquidity()

        assert res is not None
        assert res["net_liquidity_billions"] > 3000.0  # Fed Net Liquidity > $3 Trillion
        assert res["walcl_billions"] > 5000.0          # Fed Assets > $5 Trillion
        assert res["tga_billions"] > 100.0             # Treasury General Account > $100B
        assert "regime" in res
        print(f"\n[LIVE TEST] Fed Net Liquidity: ${res['net_liquidity_billions']:,.1f}B (WALCL=${res['walcl_billions']:,.1f}B, TGA=${res['tga_billions']:,.1f}B, RRP=${res['rrp_billions']:,.1f}B, Regime={res['regime']})")

    await engine.dispose()


@pytest.mark.asyncio
async def test_live_economic_report_decomposition(db_session_factory):
    """Test live economic report decomposition (CPI & NFP) with FRED series integration."""
    session_factory, engine = db_session_factory
    async with session_factory() as session:
        fetcher = GenericGovStatsFetcher(session)

        # 1. CPI Breakdown
        cpi_components = await fetcher.fetch_and_store_report(report_type="CPI")
        assert len(cpi_components) >= 8
        headline_cpi = next(c for c in cpi_components if "Headline" in c["component_name"])
        core_cpi = next(c for c in cpi_components if "Core" in c["component_name"])
        assert headline_cpi["value_actual"] is not None
        assert core_cpi["value_actual"] is not None
        print(f"\n[LIVE TEST] Ingested {len(cpi_components)} CPI components. Headline MoM={headline_cpi['value_actual']}%, Core MoM={core_cpi['value_actual']}%")

        # 2. NFP Breakdown
        nfp_components = await fetcher.fetch_and_store_report(report_type="NFP")
        assert len(nfp_components) >= 6
        headline_nfp = next(c for c in nfp_components if "Total Nonfarm" in c["component_name"])
        unrate = next(c for c in nfp_components if "Unemployment" in c["component_name"])
        assert headline_nfp["value_actual"] is not None
        assert unrate["value_actual"] is not None
        print(f"\n[LIVE TEST] Ingested {len(nfp_components)} NFP components. Payroll Change={headline_nfp['value_actual']}k, Unemployment Rate={unrate['value_actual']}%")

    await engine.dispose()


@pytest.mark.asyncio
async def test_live_central_bank_scraping(db_session_factory):
    """Test live document scraping from Federal Reserve, ECB, and Bank of Japan."""
    session_factory, engine = db_session_factory
    async with session_factory() as session:
        scraper = CentralBankDocScraper(session)

        # 1. Federal Reserve Live Scrape
        fed_doc = await scraper.fetch_live_document(bank="FED", doc_type="STATEMENT")
        assert fed_doc is not None
        assert len(fed_doc["full_text"]) > 100
        assert "hawkish_dovish_score" in fed_doc
        print(f"\n[LIVE TEST] Federal Reserve Live Scrape: {fed_doc['title']}, Tone Score={fed_doc['hawkish_dovish_score']:+.2f}, URL={fed_doc['source_url']}")

        # 2. ECB Live Scrape
        ecb_doc = await scraper.fetch_live_document(bank="ECB", doc_type="STATEMENT")
        assert ecb_doc is not None
        assert len(ecb_doc["full_text"]) > 100
        print(f"[LIVE TEST] ECB Live Scrape: {ecb_doc['title']}, Tone Score={ecb_doc['hawkish_dovish_score']:+.2f}, URL={ecb_doc['source_url']}")

        # 3. Bank of Japan Live Scrape
        boj_doc = await scraper.fetch_live_document(bank="BOJ", doc_type="STATEMENT")
        assert boj_doc is not None
        assert len(boj_doc["full_text"]) > 100
        print(f"[LIVE TEST] BoJ Live Scrape: {boj_doc['title']}, Tone Score={boj_doc['hawkish_dovish_score']:+.2f}, URL={boj_doc['source_url']}")

    await engine.dispose()


@pytest.mark.asyncio
async def test_end_to_end_universal_macro_calculators(db_session_factory):
    """Verify calculators execute against live PostgreSQL database populated by fetchers."""
    session_factory, engine = db_session_factory
    async with session_factory() as session:
        # 1. Universal Macro Analyzer
        macro_analyzer = UniversalMacroAnalyzer(session)
        decomp_analysis = await macro_analyzer.decompose_report(report_type="CPI")
        assert "headline" in decomp_analysis
        assert "institutional_verdict" in decomp_analysis
        print(f"\n[LIVE TEST] Universal Macro Analyzer: Headline MoM={decomp_analysis['headline']['mom']}%, YoY={decomp_analysis['headline']['yoy']}%")
        print(f"   Verdict: {decomp_analysis['institutional_verdict']['classification']}")
        print(f"   Rationale: {decomp_analysis['institutional_verdict']['rationale']}")

        # 2. Universal Liquidity Analyzer
        liq_analyzer = UniversalLiquidityAnalyzer(session)
        net_liq_res = await liq_analyzer.analyze_fed_net_liquidity()
        assert "current_net_liquidity_billions" in net_liq_res
        assert "regime" in net_liq_res
        print(f"[LIVE TEST] Universal Liquidity Analyzer: Net Liquidity=${net_liq_res['current_net_liquidity_billions']:,.1f}B ({net_liq_res['regime']})")

        stress_res = await liq_analyzer.analyze_credit_and_funding_stress()
        assert "hy_oas_bps" in stress_res
        assert "stress_regime" in stress_res
        print(f"   Credit & Funding Stress: HY OAS={stress_res['hy_oas_bps']} bps, Status={stress_res['stress_regime']}")

        auction_res = await liq_analyzer.analyze_treasury_auction_demand(tenor="10Y")
        assert "high_stopping_yield" in auction_res
        assert "auction_health_verdict" in auction_res
        print(f"   10Y Auction Analysis: Stopping Yield={auction_res['high_stopping_yield']}%, Verdict={auction_res['auction_health_verdict']['classification']}")

    await engine.dispose()
