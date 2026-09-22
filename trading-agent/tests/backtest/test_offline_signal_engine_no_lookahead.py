"""
Unit tests for backtest/offline_signal_engine.py verifying zero look-ahead bias and column normalization.
"""
import pytest
import pandas as pd
import numpy as np
from backtest.offline_signal_engine import OfflineSignalEngine


def test_offline_signal_engine_column_casing():
    """Verify lowercase columns ('open', 'high', 'low', 'close') work seamlessly."""
    engine = OfflineSignalEngine({})
    data = {
        "open": [10.0] * 5,
        "high": [11.0, 12.0, 11.5, 12.5, 13.0],
        "low": [9.0, 9.5, 10.0, 10.5, 11.0],
        "close": [9.5, 10.5, 11.0, 11.2, 12.0],
        "volume": [100.0] * 5
    }
    df = pd.DataFrame(data)
    atr = engine._calculate_atr(df, period=3)
    assert isinstance(atr, pd.Series)
    assert not atr.empty


def test_offline_signal_engine_no_lookahead_shift():
    """Verify signals are shifted by 1 bar so bar t close is actionable only at bar t+1."""
    engine = OfflineSignalEngine({})
    # Generate 250 bars
    np.random.seed(42)
    n = 250
    closes = np.cumsum(np.random.randn(n)) + 100.0
    highs = closes + np.abs(np.random.randn(n))
    lows = closes - np.abs(np.random.randn(n))
    opens = closes + np.random.randn(n) * 0.1

    df = pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
    })

    sig_df = engine.generate_signals(df)
    assert "Signal" in sig_df.columns
    # First bar must have 0 signal due to shift(1)
    assert sig_df["Signal"].iloc[0] == 0

    # Test stop/target calculation uses Open
    stops_df = engine.calculate_stops_and_targets(sig_df)
    buy_indices = stops_df.index[stops_df["Signal"] == 1]
    if len(buy_indices) > 0:
        idx = buy_indices[0]
        # Stop loss should be below Open
        assert stops_df.loc[idx, "StopLoss"] < stops_df.loc[idx, "Open"]
        # Take profit should be above Open
        assert stops_df.loc[idx, "TakeProfit"] > stops_df.loc[idx, "Open"]


def test_offline_signal_engine_atr_shifted_zero_lookahead():
    """Verify ATR used in calculate_stops_and_targets uses only completed prior bar data (shifted by 1)."""
    engine = OfflineSignalEngine({})
    # Create simple dataframe where ATR varies predictably
    # Bar 0, 1, 2, 3
    df = pd.DataFrame({
        "Open": [100.0, 101.0, 102.0, 103.0],
        "High": [105.0, 106.0, 107.0, 115.0],  # Bar 3 has massive high (115.0)
        "Low": [95.0, 96.0, 97.0, 90.0],       # Bar 3 has massive range
        "Close": [101.0, 102.0, 103.0, 104.0],
        "Signal": [0, 0, 0, 1],                # Buy signal executed at Bar 3
        "ATR": [10.0, 10.0, 10.0, 25.0]        # Raw unshifted ATR at Bar 3 is 25.0
    })

    # At bar 3 execution, stops should use bar 2's ATR (10.0), NOT bar 3's unshifted ATR (25.0)!
    res = engine.calculate_stops_and_targets(df, risk_reward_ratio=2.0)

    # Bar 3: Open = 103.0, shifted ATR = 10.0.
    # Expected StopLoss = 103.0 - (10.0 * 1.5) = 88.0
    # Expected TakeProfit = 103.0 + (10.0 * 1.5 * 2.0) = 133.0
    assert res.loc[3, "StopLoss"] == pytest.approx(88.0)
    assert res.loc[3, "TakeProfit"] == pytest.approx(133.0)

