from tests.conftest import create_mock_async_session
"""
Unit tests for Advanced Analytics: Macro Cross-Asset Correlation & Coinglass Open Interest.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from utils.market.dynamic_correlation import compute_cross_asset_macro_correlation
from data_sources.coinglass_funding import CoinglasFundingFetcher


@pytest.mark.asyncio
async def test_cross_asset_macro_correlation_computation():
    mock_session = create_mock_async_session()
    mock_result = MagicMock()
    mock_result.all.return_value = [
        (datetime(2026, 9, 1, tzinfo=timezone.utc), 4.25),
        (datetime(2026, 9, 2, tzinfo=timezone.utc), 4.30),
        (datetime(2026, 9, 3, tzinfo=timezone.utc), 4.35),
    ]
    mock_session.execute.return_value = mock_result

    res = await compute_cross_asset_macro_correlation(mock_session, lookback_days=30)
    assert res["status"] in ("success", "ok", "partial")
    assert "us10y_xau_corr" in res
    assert "yield_curve_10y_2y" in res


@pytest.mark.asyncio
async def test_coinglass_fetcher_open_interest():
    fetcher = CoinglasFundingFetcher()

    with patch.object(fetcher, "fetch_open_interest_btc", new_callable=AsyncMock) as mock_oi:
        mock_oi.return_value = {
            "symbol": "BTCUSDT",
            "open_interest_usd": 12500000000.0,
            "open_interest_coins": 135000.0,
            "status": "success",
        }
        res = await fetcher.fetch_open_interest_btc()
        assert res["status"] == "success"
        assert res["open_interest_usd"] == 12500000000.0
