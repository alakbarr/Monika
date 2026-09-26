import pytest
import math
from unittest.mock import AsyncMock, MagicMock, patch
from risk.portfolio_correlation_gate import (
    _get_usd_directional_delta,
    compute_portfolio_correlation_matrix,
    filter_correlated_proposals,
)


def test_usd_directional_delta():
    # Long USD
    assert _get_usd_directional_delta("USDJPY", "buy") == 1
    assert _get_usd_directional_delta("EURUSD", "sell") == 1
    assert _get_usd_directional_delta("GBPUSD", "sell") == 1
    assert _get_usd_directional_delta("XAUUSD", "sell") == 1

    # Short USD
    assert _get_usd_directional_delta("USDJPY", "sell") == -1
    assert _get_usd_directional_delta("EURUSD", "buy") == -1
    assert _get_usd_directional_delta("GBPUSD", "buy") == -1
    assert _get_usd_directional_delta("XAUUSD", "buy") == -1

    # Neutral / non-USD
    assert _get_usd_directional_delta("EURGBP", "buy") == 0
    assert _get_usd_directional_delta("USDJPY", "wait") == 0


@pytest.mark.asyncio
async def test_compute_portfolio_correlation_matrix():
    session = AsyncMock()
    symbols = ["EURUSD", "GBPUSD"]

    with patch("risk.portfolio_correlation_gate.get_rolling_correlation", new=AsyncMock(return_value=(0.85, "db"))):
        matrix = await compute_portfolio_correlation_matrix(session, symbols)
        assert matrix["EURUSD"]["EURUSD"] == 1.0
        assert matrix["GBPUSD"]["GBPUSD"] == 1.0
        assert matrix["EURUSD"]["GBPUSD"] == 0.85
        assert matrix["GBPUSD"]["EURUSD"] == 0.85


@pytest.mark.asyncio
async def test_filter_correlated_proposals_nan_handling():
    """Verify that NaN correlation from open position does not raise NameError and defaults safely."""
    session = AsyncMock()
    mock_pos = MagicMock()
    mock_pos.symbol = "EURUSD"
    mock_pos.direction = "buy"

    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [mock_pos]
    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars
    session.execute.return_value = mock_result

    actionable = [
        ("GBPUSD", {"decision": "buy", "confidence": 0.8})
    ]

    # Return float('nan') to trigger math.isnan check
    with patch("risk.portfolio_correlation_gate.get_rolling_correlation", new=AsyncMock(return_value=(float("nan"), "test"))):
        kept, rejected = await filter_correlated_proposals(session, actionable, threshold=0.7)
        assert len(kept) == 1
        assert kept[0][0] == "GBPUSD"
        assert len(rejected) == 0


@pytest.mark.asyncio
async def test_filter_correlated_proposals_max_usd_exposure():
    session = AsyncMock()
    # 3 open long USD positions
    open_positions = []
    for s in ["USDJPY", "USDCHF", "USDCAD"]:
        p = MagicMock()
        p.symbol = s
        p.direction = "buy"
        open_positions.append(p)

    mock_scalars = MagicMock()
    mock_scalars.all.return_value = open_positions
    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars
    session.execute.return_value = mock_result

    # Another buy USD proposal should be rejected by systemic cap (max_usd_exposure=3)
    actionable = [
        ("EURUSD", {"decision": "sell", "confidence": 0.9})  # sell EURUSD = long USD
    ]

    kept, rejected = await filter_correlated_proposals(session, actionable, max_usd_exposure=3)
    assert len(kept) == 0
    assert len(rejected) == 1
    assert "Systemic concentration cap" in rejected[0][2]
