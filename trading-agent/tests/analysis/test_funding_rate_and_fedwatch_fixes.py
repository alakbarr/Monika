"""
Unit tests for Funding Rate Resilience and Multi-Meeting FedWatch Dominant Validation Fixes.
"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch

from data_sources.coinglass_funding import CoinglasFundingFetcher
from analysis.tools.tool_executor import ToolExecutor


# ==============================================================================
# 1. CoinglasFundingFetcher Multi-Source Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_funding_rate_fetcher_binance_primary_success():
    """Verify CoinglasFundingFetcher successfully parses Binance Futures premiumIndex."""
    mock_session = AsyncMock()
    fetcher = CoinglasFundingFetcher(session=mock_session)

    binance_response = {
        "symbol": "BTCUSDT",
        "markPrice": "62500.50",
        "indexPrice": "62480.00",
        "lastFundingRate": "0.000125",
        "nextFundingTime": 1724947200000,
        "interestRate": "0.000100"
    }

    with patch("data_sources.coinglass_funding.fetch_with_retry", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = binance_response
        result = await fetcher.fetch()

        assert result.get("symbol") == "BTCUSD"
        assert result.get("average_funding_rate") == 0.000125
        assert result.get("interpretation") == "Moderately long-biased"
        assert result.get("source") == "Binance"
        assert len(result.get("exchanges", [])) == 1


@pytest.mark.asyncio
async def test_funding_rate_fetcher_bybit_fallback_success():
    """Verify CoinglasFundingFetcher falls back to Bybit when Binance fails."""
    mock_session = AsyncMock()
    fetcher = CoinglasFundingFetcher(session=mock_session)

    bybit_response = {
        "retCode": 0,
        "result": {
            "category": "linear",
            "list": [
                {
                    "symbol": "BTCUSDT",
                    "fundingRate": "0.000085",
                    "nextFundingTime": "1724947200000"
                }
            ]
        }
    }

    async def side_effect_fetch(url, *args, **kwargs):
        if "binance" in url:
            return None
        elif "bybit" in url:
            return bybit_response
        return None

    with patch("data_sources.coinglass_funding.fetch_with_retry", side_effect=side_effect_fetch):
        result = await fetcher.fetch()

        assert result.get("symbol") == "BTCUSD"
        assert result.get("average_funding_rate") == 0.000085
        assert result.get("interpretation") == "Neutral"
        assert result.get("source") == "Bybit"


# ==============================================================================
# 2. ToolExecutor _tool_get_funding_rate Resilience Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_tool_get_funding_rate_on_demand_live_fallback():
    """Verify _tool_get_funding_rate performs live on-demand fetch when SystemConfig is empty."""
    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_res

    executor = ToolExecutor(session=mock_session, settings={})

    live_funding_data = {
        "symbol": "BTCUSD",
        "average_funding_rate": 0.000150,
        "interpretation": "Moderately long-biased",
        "source": "Binance"
    }

    with patch("data_sources.coinglass_funding.CoinglasFundingFetcher.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = live_funding_data
        result = await executor._tool_get_funding_rate({})

        assert result.get("average_funding_rate") == 0.000150
        assert result.get("source") == "Binance"
        assert not result.get("error")


@pytest.mark.asyncio
async def test_tool_get_funding_rate_offline_neutral_baseline():
    """Verify _tool_get_funding_rate returns structured neutral baseline if all live endpoints fail."""
    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_res

    executor = ToolExecutor(session=mock_session, settings={})

    with patch("data_sources.coinglass_funding.CoinglasFundingFetcher.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.side_effect = Exception("Network offline")
        result = await executor._tool_get_funding_rate({})

        assert result.get("symbol") == "BTCUSD"
        assert result.get("average_funding_rate") == 0.0001
        assert "warning" in result
        assert "error" not in result


# ==============================================================================
# 3. Multi-Meeting FedWatch Validation Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_fedwatch_validation_multi_meeting_tolerance_match():
    """
    Verify _validate_key_data_points accepts 52.7% when September meeting dominant is 52.7%
    even if December meeting dominant is 39.2%.
    """
    mock_session = AsyncMock()
    executor = ToolExecutor(session=mock_session, settings={})

    # Mock get_fedwatch_probabilities returning multiple upcoming meetings
    fedwatch_payload = {
        "count": 2,
        "meetings": [
            {
                "meeting_date": "2026-09-16",
                "probabilities": {
                    "probabilities": {
                        "4.00-4.25": {"probability": 52.7, "action": "cut_25"},
                        "4.25-4.50": {"probability": 39.2, "action": "maintain"},
                        "3.75-4.00": {"probability": 8.1, "action": "cut_50"}
                    }
                }
            },
            {
                "meeting_date": "2026-12-16",
                "probabilities": {
                    "probabilities": {
                        "3.75-4.00": {"probability": 39.2, "action": "cut_25"},
                        "3.50-3.75": {"probability": 35.0, "action": "cut_50"},
                        "4.00-4.25": {"probability": 25.8, "action": "maintain"}
                    }
                }
            }
        ]
    }

    inp = {
        "key_data_points_used": {
            "fedwatch_dominant_pct": 52.7
        }
    }

    with patch.object(executor, "execute", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = fedwatch_payload
        errors = await executor._validate_key_data_points(inp)

        # 52.7% matches the September meeting dominant exactly -> should NOT raise DATA_MISMATCH
        mismatch_errors = [e for e in errors if "DATA_MISMATCH: Kamu menyatakan FedWatch dominant" in e]
        assert len(mismatch_errors) == 0


@pytest.mark.asyncio
async def test_fedwatch_validation_genuine_mismatch_rejection():
    """Verify _validate_key_data_points rejects when claimed value differs by > 8.0% from ALL meetings."""
    mock_session = AsyncMock()
    executor = ToolExecutor(session=mock_session, settings={})

    fedwatch_payload = {
        "count": 2,
        "meetings": [
            {
                "meeting_date": "2026-09-16",
                "probabilities": {
                    "probabilities": {
                        "4.00-4.25": {"probability": 52.7, "action": "cut_25"},
                        "4.25-4.50": {"probability": 39.2, "action": "maintain"}
                    }
                }
            },
            {
                "meeting_date": "2026-12-16",
                "probabilities": {
                    "probabilities": {
                        "3.75-4.00": {"probability": 39.2, "action": "cut_25"},
                        "3.50-3.75": {"probability": 35.0, "action": "cut_50"}
                    }
                }
            }
        ]
    }

    # Claimed 90.0% which differs from 52.7% and 39.2% by > 8.0%
    inp = {
        "key_data_points_used": {
            "fedwatch_dominant_pct": 90.0
        }
    }

    with patch.object(executor, "execute", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = fedwatch_payload
        errors = await executor._validate_key_data_points(inp)

        mismatch_errors = [e for e in errors if "DATA_MISMATCH: Kamu menyatakan FedWatch dominant" in e]
        assert len(mismatch_errors) == 1
        assert "terdekat=52.7" in mismatch_errors[0]
