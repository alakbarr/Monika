"""
Unit tests for Verified Market Snapshot Ground Truth (H4).
"""
import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone
from analysis.validators.market_snapshot import VerifiedMarketSnapshot


@pytest.mark.asyncio
async def test_h4_market_snapshot_computation():
    """H4: VerifiedMarketSnapshot generates deterministic ground-truth without LLM."""
    snapshot_gen = VerifiedMarketSnapshot()

    # Mock OHLCV bar
    mock_bar = MagicMock()
    mock_bar.close = 1.08550
    mock_bar.open = 1.08200
    mock_bar.high = 1.08700
    mock_bar.low = 1.08150
    mock_bar.timestamp = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)

    # Mock Indicator rows
    mock_ind1 = MagicMock()
    mock_ind1.indicator_name = "rsi"
    mock_ind1.value_json = json.dumps(48.5)

    mock_ind2 = MagicMock()
    mock_ind2.indicator_name = "macd"
    mock_ind2.value_json = json.dumps({"macd": 0.0012, "signal": 0.0009, "hist": 0.0003})

    mock_session = AsyncMock()

    # Session execute returns bar for first query, indicator list for second query
    mock_exec1 = MagicMock()
    mock_exec1.scalar_one_or_none.return_value = mock_bar

    mock_exec2 = MagicMock()
    mock_exec2.scalars.return_value.all.return_value = [mock_ind1, mock_ind2]

    mock_session.execute.side_effect = [mock_exec1, mock_exec2]

    snapshot = await snapshot_gen.compute("EURUSD", mock_session)

    assert snapshot["symbol"] == "EURUSD"
    assert snapshot["_ground_truth"] is True
    assert snapshot["latest_close"] == 1.08550
    assert snapshot["latest_high"] == 1.08700
    assert snapshot["latest_low"] == 1.08150
    assert snapshot["latest_open"] == 1.08200
    assert snapshot["rsi"] == 48.5
    assert snapshot["macd_macd"] == 0.0012
    assert snapshot["macd_signal"] == 0.0009
    assert snapshot["macd_hist"] == 0.0003


@pytest.mark.asyncio
async def test_h4_market_snapshot_empty_db():
    """H4: VerifiedMarketSnapshot handles missing data gracefully."""
    snapshot_gen = VerifiedMarketSnapshot()
    mock_session = AsyncMock()

    # 4 executes: OHLCV (tf + fallback), indicators (tf + fallback)
    mock_empty_scalar = MagicMock()
    mock_empty_scalar.scalar_one_or_none.return_value = None

    mock_empty_rows = MagicMock()
    mock_empty_rows.scalars.return_value.all.return_value = []

    mock_session.execute.side_effect = [
        mock_empty_scalar,  # OHLCV tf query -> miss
        mock_empty_scalar,  # OHLCV fallback (any timeframe) -> miss
        mock_empty_rows,    # indicators tf query -> miss
        mock_empty_rows,    # indicators fallback -> miss
    ]

    snapshot = await snapshot_gen.compute("GBPUSD", mock_session)

    assert snapshot["symbol"] == "GBPUSD"
    assert snapshot["_ground_truth"] is True
    assert "latest_close" not in snapshot


def test_format_as_markdown():
    snapshot = {
        "symbol": "EURUSD",
        "latest_close": 1.08550,
        "latest_high": 1.08700,
        "latest_low": 1.08150,
        "latest_open": 1.08200,
        "rsi_14": 48.5,
        "atr_14": 0.0045,
        "bar_timestamp": "2026-09-06T12:00:00Z"
    }
    md = VerifiedMarketSnapshot.format_as_markdown(snapshot)
    assert "DETERMINISTIC MARKET GROUND TRUTH" in md
    assert "Close=1.0855" in md
    assert "RSI(14)=48.5" in md
    assert "ATR(14)=0.0045" in md


def test_validate_plan_against_snapshot_valid():
    snapshot = {"latest_close": 1.0850}
    plan = {
        "action": "BUY",
        "entry_price": 1.0850,
        "stop_loss": 1.0800,
        "take_profit": 1.0950,
        "order_type": "MARKET"
    }
    valid, issues = VerifiedMarketSnapshot.validate_plan_against_snapshot(plan, snapshot)
    assert valid is True
    assert len(issues) == 0


def test_validate_plan_against_snapshot_inverted_sl_tp():
    snapshot = {"latest_close": 1.0850}
    # Inverted BUY: SL above entry
    bad_buy = {
        "action": "BUY",
        "entry_price": 1.0850,
        "stop_loss": 1.0900,  # Invalid for BUY
        "take_profit": 1.0800,  # Invalid for BUY
        "order_type": "MARKET"
    }
    valid, issues = VerifiedMarketSnapshot.validate_plan_against_snapshot(bad_buy, snapshot)
    assert valid is False
    assert any("SL" in i for i in issues)
    assert any("TP" in i for i in issues)

    # Inverted SELL: SL below entry
    bad_sell = {
        "action": "SELL",
        "entry_price": 1.0850,
        "stop_loss": 1.0800,  # Invalid for SELL
        "take_profit": 1.0900,  # Invalid for SELL
        "order_type": "MARKET"
    }
    valid, issues = VerifiedMarketSnapshot.validate_plan_against_snapshot(bad_sell, snapshot)
    assert valid is False
    assert any("SL" in i for i in issues)
    assert any("TP" in i for i in issues)


def test_validate_plan_against_snapshot_large_drift():
    snapshot = {"latest_close": 1.0850}
    drifting_plan = {
        "action": "BUY",
        "entry_price": 1.2500,  # > 15% drift on EURUSD
        "stop_loss": 1.2400,
        "take_profit": 1.2700,
        "order_type": "MARKET"
    }
    valid, issues = VerifiedMarketSnapshot.validate_plan_against_snapshot(drifting_plan, snapshot)
    assert valid is False
    assert any("diverges >10%" in i for i in issues)
