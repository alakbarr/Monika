import pandas as pd
import pytest
from unittest.mock import AsyncMock, MagicMock
from monika.application.analysis.grounding.market_grounding import MarketGroundingEngine
from monika.application.graph.grounding import MarketGroundingEngine as FacadeEngine


def test_format_grounding_from_df_valid():
    """Verify Markdown table generation from pandas OHLCV DataFrame."""
    data = {
        "open": [100.0, 101.0, 102.0, 103.0, 104.0],
        "high": [105.0, 106.0, 107.0, 108.0, 109.0],
        "low": [99.0, 100.0, 101.0, 102.0, 103.0],
        "close": [104.0, 105.0, 106.0, 107.0, 108.0],
        "volume": [1000, 1200, 1500, 1100, 1300],
    }
    df = pd.DataFrame(data, index=["2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04", "2026-10-05"])
    table_md = MarketGroundingEngine.format_grounding_from_df("XAUUSD", df)
    assert "Ground Truth — Empirical Market Context" in table_md
    assert "XAUUSD" in table_md
    assert "Current Reference Price" in table_md
    assert "108.0000" in table_md
    assert "| Date | Open | High | Low | Close | Volume |" in table_md


def test_format_grounding_from_df_empty_or_none():
    """Verify empty or None DataFrame returns empty string gracefully."""
    assert MarketGroundingEngine.format_grounding_from_df("XAUUSD", None) == ""
    assert MarketGroundingEngine.format_grounding_from_df("XAUUSD", pd.DataFrame()) == ""


@pytest.mark.asyncio
async def test_build_grounding_table_with_mock_repository():
    """Verify build_grounding_table interacts correctly with MarketDataRepository."""
    mock_bar = MagicMock()
    mock_bar.open = 100.0
    mock_bar.high = 105.0
    mock_bar.low = 95.0
    mock_bar.close = 102.0
    mock_bar.volume = 5000
    mock_bar.timestamp = None

    mock_repo = MagicMock()
    mock_repo.get_recent_bars = AsyncMock(return_value=[mock_bar] * 10)

    res = await MarketGroundingEngine.build_grounding_table("BTCUSD", repository=mock_repo)
    assert "BTCUSD" in res
    assert "Current Reference Price" in res
    assert "| Date | Open | High | Low | Close | Volume |" in res


@pytest.mark.asyncio
async def test_grounding_facade_backward_compatibility():
    """Verify graph.grounding facade delegates seamlessly to canonical engine."""
    data = {
        "open": [1.1000, 1.1050],
        "high": [1.1100, 1.1120],
        "low": [1.0950, 1.1000],
        "close": [1.1050, 1.1080],
        "volume": [2000, 2500],
    }
    df = pd.DataFrame(data, index=["2026-10-01", "2026-10-02"])
    facade_res = FacadeEngine.format_grounding_from_df("EURUSD", df)
    assert "EURUSD" in facade_res
    assert "Current Reference Price" in facade_res
