# ==============================================================================
# File: tests/data_sources/test_sovereign_yield_spreads.py
# ==============================================================================

"""Unit tests for SovereignYieldSpreads and macro carry differential calculations."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from monika.infrastructure.data_ingestion.sources.sovereign_yield_spreads import SovereignYieldSpreads
from monika.infrastructure.database.models import BondYieldData


def test_yield_tickers_isolated_to_valid_us_index():
    """Verify YIELD_TICKERS does not contain non-existent/delisted foreign bond tickers."""
    tickers = SovereignYieldSpreads.YIELD_TICKERS
    assert "US_10Y" in tickers
    assert tickers["US_10Y"] == "^TNX"
    # Foreign tickers must not exist in Yahoo Finance map to prevent HTTP 404 pollution
    assert "GERMANY_10Y" not in tickers
    assert "JAPAN_10Y" not in tickers
    assert "UK_10Y" not in tickers
    assert "AUSTRALIA_10Y" not in tickers


@pytest.mark.asyncio
async def test_sovereign_yield_spreads_async_calculation(db_session):
    """Verify get_spreads calculates correct differentials using DB-backed foreign yields."""
    # Seed verified sovereign yields
    from datetime import datetime, timezone

    today = datetime.now(timezone.utc)
    db_session.add(BondYieldData(country_tenor="DE_10Y", date=today, yield_percent=2.50))
    db_session.add(BondYieldData(country_tenor="JP_10Y", date=today, yield_percent=0.90))
    db_session.add(BondYieldData(country_tenor="UK_10Y", date=today, yield_percent=4.10))
    db_session.add(BondYieldData(country_tenor="AU_10Y", date=today, yield_percent=3.80))
    await db_session.commit()

    with patch.object(
        SovereignYieldSpreads,
        "_fetch_yahoo_chart_async",
        new_callable=AsyncMock,
        return_value=(4.50, 4.40),  # US 10Y current=4.50, prev=4.40
    ) as mock_yahoo:
        res = await SovereignYieldSpreads.get_spreads(session=db_session)

        # Ensure Yahoo API is called ONLY once (for US 10Y ^TNX), not for foreign tickers
        assert mock_yahoo.call_count == 1
        assert mock_yahoo.call_args[0][0] == "^TNX"

        assert res["us_10y_yield"] == 4.50
        spreads = res["spreads"]
        assert "EURUSD" in spreads
        assert "USDJPY" in spreads
        assert "GBPUSD" in spreads
        assert "AUDUSD" in spreads

        # EURUSD: (4.50 - 2.50) * 100 = 200.0 bps
        assert spreads["EURUSD"]["us_yield"] == 4.50
        assert spreads["EURUSD"]["foreign_yield"] == 2.50
        assert spreads["EURUSD"]["spread_bps"] == 200.0


@pytest.mark.asyncio
async def test_sovereign_yield_spreads_fail_closed():
    """Verify fail-closed behavior when US 10Y is unavailable."""
    with patch.object(
        SovereignYieldSpreads,
        "_fetch_yahoo_chart_async",
        new_callable=AsyncMock,
        return_value=None,
    ):
        with patch.object(
            SovereignYieldSpreads,
            "_fetch_db_fallback",
            new_callable=AsyncMock,
            return_value=None,
        ):
            res = await SovereignYieldSpreads.get_spreads()
            assert res["status"] == "error"
            assert res["us_10y_yield"] is None
            assert res["spreads"] == {}


@pytest.mark.asyncio
async def test_db_fallback_on_demand_fetch_on_cold_start():
    """Verify _fetch_db_fallback invokes BondYieldFetcher when database has no records."""
    mock_session = AsyncMock()
    mock_empty_res = MagicMock()
    mock_empty_res.scalars.return_value.all.return_value = []

    mock_populated_res = MagicMock()
    mock_populated_res.scalars.return_value.all.return_value = [3.20, 3.15]

    # Return empty first, then populated after fetch
    mock_session.execute.side_effect = [mock_empty_res, mock_populated_res]

    with patch(
        "monika.infrastructure.data_ingestion.sources.bond_yields_fetcher.BondYieldFetcher.fetch",
        new_callable=AsyncMock,
        return_value={"DE_10Y": 1},
    ) as mock_fetch:
        result = await SovereignYieldSpreads._fetch_db_fallback("GERMANY_10Y", session=mock_session)

        assert mock_fetch.called
        assert result == (3.20, 3.15)


def test_get_spreads_sync_delegation():
    """Verify get_spreads_sync handles execution safely without KeyError."""
    with patch.object(
        SovereignYieldSpreads,
        "get_spreads",
        new_callable=AsyncMock,
        return_value={"us_10y_yield": 4.50, "spreads": {"EURUSD": {"spread_bps": 200.0}}},
    ):
        res = SovereignYieldSpreads.get_spreads_sync()
        assert res["us_10y_yield"] == 4.50
        assert "EURUSD" in res["spreads"]
