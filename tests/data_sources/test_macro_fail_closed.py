# ==============================================================================
# File: tests/data_sources/test_macro_fail_closed.py
# ==============================================================================

"""
Unit Tests for Fail-Closed Ingestion & Anti-Fabrication Safeguards.
Verifies that when external APIs or network feeds are missing/unreachable:
1. Fetchers return explicit unavailable/empty states.
2. No synthetic, hardcoded or hallucinated market records are written to DB.
3. Calculators handle empty datasets defensively without false confidence.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from monika.application.analysis.calculators.universal_liquidity_analyzer import (
    UniversalLiquidityAnalyzer,
)
from monika.application.analysis.calculators.universal_macro_analyzer import (
    UniversalMacroAnalyzer,
)
from monika.infrastructure.data_ingestion.scrapers.macro.generic_gov_stats_fetcher import (
    GenericGovStatsFetcher,
)
from monika.infrastructure.data_ingestion.sources.fed_liquidity_h41_fetcher import (
    FedLiquidityH41Fetcher,
)
from monika.infrastructure.data_ingestion.sources.gold_physical_radar import (
    GoldPhysicalRadar,
)
from monika.infrastructure.data_ingestion.sources.leading_survey_fetcher import (
    LeadingSurveyFetcher,
)
from monika.infrastructure.data_ingestion.sources.market_stress_auction_fetcher import (
    MarketStressAuctionFetcher,
)


@pytest.mark.asyncio
async def test_leading_survey_fetcher_fail_closed():
    """Verify LeadingSurveyFetcher does not inject hardcoded PMIs when FRED is unavailable."""
    mock_session = AsyncMock()
    fetcher = LeadingSurveyFetcher(mock_session)

    with patch.dict("os.environ", {"FRED_API_KEY": ""}):
        results = await fetcher.fetch_and_store_surveys(period="2026-10")
        assert results == [], "Must fail closed and return empty list when no data is fetched"
        assert mock_session.execute.call_count == 0, "Must not execute database writes when data is absent"

    # Verify global PMI summary with no records in DB
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_res

    with patch.dict("os.environ", {"FRED_API_KEY": ""}):
        summary = await fetcher.get_global_pmi_summary("2026-10")
        assert summary["status"] == "unavailable"
        assert summary["global_composite_pmi"] is None
        assert "No global PMI survey data available" in summary["institutional_implication"]


@pytest.mark.asyncio
async def test_market_stress_auction_fetcher_fail_closed():
    """Verify MarketStressAuctionFetcher fails closed instead of generating fake auction tails."""
    mock_session = AsyncMock()
    fetcher = MarketStressAuctionFetcher(mock_session)

    # 1. Auction fetch with failed network request
    with patch("aiohttp.ClientSession.get", side_effect=Exception("Network error")):
        res = await fetcher.fetch_and_store_treasury_auction(tenor="10Y")
        assert res["status"] == "unavailable"
        assert "Auction yield unavailable" in res["message"]
        assert mock_session.execute.call_count == 0

    # 2. Credit metrics with no FRED API key
    with patch.dict("os.environ", {"FRED_API_KEY": ""}):
        stress_res = await fetcher.fetch_and_store_credit_and_money_market()
        assert stress_res == [], "Must not insert fake credit or TIC records when FRED key is absent"


@pytest.mark.asyncio
async def test_fed_liquidity_h41_fetcher_fail_closed():
    """Verify FedLiquidityH41Fetcher fails closed instead of generating fake balance sheets."""
    mock_session = AsyncMock()
    fetcher = FedLiquidityH41Fetcher(mock_session)

    with patch.dict("os.environ", {"FRED_API_KEY": ""}):
        res = await fetcher.fetch_and_store_liquidity()
        assert res["status"] == "unavailable"
        assert "Incomplete Federal Reserve H.4.1" in res["message"]
        assert mock_session.execute.call_count == 0


@pytest.mark.asyncio
async def test_generic_gov_stats_fetcher_fail_closed():
    """Verify GenericGovStatsFetcher fails closed instead of generating fake CPI/NFP breakdowns."""
    mock_session = AsyncMock()
    fetcher = GenericGovStatsFetcher(mock_session)

    with patch.dict("os.environ", {"FRED_API_KEY": ""}):
        res = await fetcher.fetch_and_store_report("CPI", period="2026-10")
        assert res == [], "Must return empty list without writing fake components to DB"
        assert mock_session.execute.call_count == 0


@pytest.mark.asyncio
async def test_gold_physical_radar_fail_closed():
    """Verify GoldPhysicalRadar marks snapshot as unavailable without fake $245 price."""
    with patch.object(GoldPhysicalRadar, "_fetch_gld_market_sync", return_value=None):
        snapshot = await GoldPhysicalRadar.fetch_radar()
        assert snapshot.is_available is False
        assert snapshot.gld_market_price is None
        assert snapshot.gld_1d_change_pct is None
        assert "unavailable" in snapshot.summary.lower()


@pytest.mark.asyncio
async def test_universal_liquidity_analyzer_empty_handling():
    """Verify UniversalLiquidityAnalyzer handles empty DB records without substitute constants."""
    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_res

    analyzer = UniversalLiquidityAnalyzer(mock_session)
    analyzer.router.ensure_liquidity_and_stress_available = AsyncMock()

    liq = await analyzer.analyze_fed_net_liquidity()
    assert liq["status"] == "unavailable"

    stress = await analyzer.analyze_credit_and_funding_stress()
    assert stress["status"] == "unavailable"

    auc = await analyzer.analyze_treasury_auction_demand("10Y")
    assert auc["status"] == "unavailable"


@pytest.mark.asyncio
async def test_universal_macro_analyzer_insufficient_data():
    """Verify UniversalMacroAnalyzer returns DATA_INSUFFICIENT when contribution bps are zero."""
    mock_session = AsyncMock()
    mock_res = MagicMock()

    headline_mock = MagicMock()
    headline_mock.category = "headline"
    headline_mock.component_name = "Headline CPI"
    headline_mock.value_actual = 3.2
    headline_mock.value_forecast = 3.1
    headline_mock.value_previous = 3.0
    headline_mock.mom_change = 0.2
    headline_mock.yoy_change = 3.2

    # Non-headline items with 0 contribution
    comp_mock = MagicMock()
    comp_mock.category = "transitory"
    comp_mock.component_name = "Energy"
    comp_mock.value_actual = 1.0
    comp_mock.value_forecast = None
    comp_mock.mom_change = 0.1
    comp_mock.contribution_bps = 0.0
    comp_mock.is_noise = True

    mock_res.scalars.return_value.all.return_value = [headline_mock, comp_mock]
    mock_session.execute.return_value = mock_res

    analyzer = UniversalMacroAnalyzer(mock_session)
    analyzer.router.ensure_report_available = AsyncMock()

    report = await analyzer.decompose_report("CPI", period="2026-10")
    assert report["institutional_verdict"]["classification"] == "DATA_INSUFFICIENT"
    assert report["institutional_verdict"]["is_structural_shift"] is False
