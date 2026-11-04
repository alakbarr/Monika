# ==============================================================================
# File: tests/indicators/test_phase3_performance_and_vectorization.py
# Phase 3 Verification: Vectorized SMC, Delta Checks & Incremental Persistence
# ==============================================================================

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pandas as pd
import pytest

from monika.application.services.market_structure_service import MarketStructureService
from monika.application.services.technical_indicator_service import TechnicalIndicatorService
from monika.domain.indicators.structure import (
    FVGData,
    LiquidityZoneData,
    OrderBlockData,
    StructureBreakData,
    detect_structure_breaks,
    find_fvg,
    find_liquidity_zones,
    find_order_blocks,
    find_sr_zones,
    find_swings,
)
from tests.conftest import create_mock_async_session


# ------------------------------------------------------------------------------
# 1. Vectorized Structure Domain Functions
# ------------------------------------------------------------------------------


def _create_synthetic_ohlcv(periods: int = 50) -> pd.DataFrame:
    """Creates a deterministic synthetic OHLCV DataFrame with predictable swings."""
    base_time = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    timestamps = [base_time + timedelta(hours=i) for i in range(periods)]

    # Triangular/sinusoidal wave with clear peaks and valleys
    prices = [100.0 + 5.0 * np.sin(i * 0.4) for i in range(periods)]

    df = pd.DataFrame(
        {
            "open": prices,
            "high": [p + 1.0 for p in prices],
            "low": [p - 1.0 for p in prices],
            "close": [p + 0.2 for p in prices],
            "volume": [1000.0 + i * 10 for i in range(periods)],
        },
        index=pd.DatetimeIndex(timestamps),
    )
    return df


def test_vectorized_structure_empty_and_short_df():
    """Verify all vectorized SMC functions gracefully handle empty or tiny DataFrames."""
    empty_df = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    empty_swings = pd.DataFrame(columns=["price", "timestamp"])

    highs, lows = find_swings(empty_df, swing_window=5)
    assert highs.empty and lows.empty

    sr = find_sr_zones(empty_swings, empty_swings, empty_df)
    assert sr == []

    liq = find_liquidity_zones(empty_swings, empty_swings, "EURUSD", "H1", empty_df)
    assert liq == []

    fvg = find_fvg(empty_df, "EURUSD", "H1")
    assert fvg == []

    obs = find_order_blocks(empty_df, "EURUSD", "H1")
    assert obs == []

    breaks = detect_structure_breaks(empty_df, empty_swings, empty_swings, "EURUSD", "H1")
    assert breaks == []


def test_vectorized_swings_and_sr_zones():
    """Verify swing points and S/R zones calculation using vectorized arrays."""
    df = _create_synthetic_ohlcv(50)
    swing_highs, swing_lows = find_swings(df, swing_window=2)

    assert not swing_highs.empty
    assert not swing_lows.empty
    assert "price" in swing_highs.columns
    assert "price" in swing_lows.columns

    # Test S/R zones
    sr_zones = find_sr_zones(swing_highs, swing_lows, df, tolerance=0.02, min_touches=1)
    assert len(sr_zones) > 0
    for z in sr_zones:
        assert isinstance(z, dict)
        assert z["price_high"] >= z["price_low"]
        assert z["touches"] >= 1


def test_vectorized_liquidity_zones_and_sweeps():
    """Verify liquidity zones detection and sweep detection with NumPy arrays."""
    df = _create_synthetic_ohlcv(50)
    swing_highs, swing_lows = find_swings(df, swing_window=2)
    zones = find_liquidity_zones(swing_highs, swing_lows, "EURUSD", "H1", df)

    assert isinstance(zones, list)
    for z in zones:
        assert isinstance(z, LiquidityZoneData)
        assert z.symbol == "EURUSD"
        assert z.timeframe == "H1"
        assert z.type in ("above_swing_high", "below_swing_low")


def test_vectorized_fvg_and_fill_detection():
    """Verify Fair Value Gap (FVG) detection and filled status with NumPy arrays."""
    base_time = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    # Candle 0: low 100, high 102
    # Candle 1: large bullish impulse candle low 102, high 112
    # Candle 2: low 105, high 115 -> Bullish FVG gap between Candle 0 high (102) and Candle 2 low (105)
    # Candle 3: retraces to low 101 -> FVG filled!
    timestamps = [base_time + timedelta(hours=i) for i in range(4)]
    df = pd.DataFrame(
        {
            "open": [101.0, 102.5, 110.0, 108.0],
            "high": [102.0, 112.0, 115.0, 109.0],
            "low": [100.0, 102.0, 105.0, 101.0],
            "close": [101.5, 111.0, 113.0, 102.0],
            "volume": [1000.0, 5000.0, 2000.0, 1500.0],
        },
        index=pd.DatetimeIndex(timestamps),
    )

    fvgs = find_fvg(df, "EURUSD", "H1")
    assert len(fvgs) == 1
    fvg = fvgs[0]
    assert isinstance(fvg, FVGData)
    assert fvg.direction == "bullish"
    assert fvg.gap_high == 105.0
    assert fvg.gap_low == 102.0
    assert fvg.filled_at == timestamps[3]


def test_vectorized_order_blocks_and_structure_breaks():
    """Verify Order Block detection and Structure Breaks with vectorized implementation."""
    df = _create_synthetic_ohlcv(60)
    swing_highs, swing_lows = find_swings(df, swing_window=2)

    obs = find_order_blocks(df, "EURUSD", "H1")
    assert isinstance(obs, list)
    for ob in obs:
        assert isinstance(ob, OrderBlockData)
        assert ob.direction in ("bullish", "bearish")
        assert ob.price_high >= ob.price_low

    breaks = detect_structure_breaks(df, swing_highs, swing_lows, "EURUSD", "H1")
    assert isinstance(breaks, list)
    for b in breaks:
        assert isinstance(b, StructureBreakData)
        assert b.break_type in ("BOS", "CHoCH")


# ------------------------------------------------------------------------------
# 2. MarketStructureService Delta-Check Verification
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_market_structure_service_delta_check():
    """Verify MarketStructureService skips recomputation when latest candle signature is unchanged."""
    mock_session = create_mock_async_session()
    service = MarketStructureService(mock_session, {})

    df = _create_synthetic_ohlcv(30)
    service._load_ohlcv = AsyncMock(return_value=df)
    service._prune_old_data = AsyncMock()

    # 1. First run: should execute full analysis and cache counts
    res1 = await service.analyze("EURUSD", "H1")
    assert res1["swing_points"] > 0
    assert ("EURUSD", "H1") in service._last_analyzed_candle
    assert ("EURUSD", "H1") in service._last_analysis_counts

    initial_prune_calls = service._prune_old_data.call_count

    # 2. Second run with exact same data: should bypass recomputation (0 prune calls added)
    res2 = await service.analyze("EURUSD", "H1")
    assert res2 == res1
    assert service._prune_old_data.call_count == initial_prune_calls

    # 3. Third run with updated candle (new close price): should recompute
    df_updated = df.copy()
    df_updated.iloc[-1, df_updated.columns.get_loc("close")] += 2.5
    service._load_ohlcv = AsyncMock(return_value=df_updated)

    res3 = await service.analyze("EURUSD", "H1")
    assert service._prune_old_data.call_count == initial_prune_calls + 1

    # 4. Fourth run with force=True: should recompute even if candle unchanged
    res4 = await service.analyze("EURUSD", "H1", force=True)
    assert service._prune_old_data.call_count == initial_prune_calls + 2


# ------------------------------------------------------------------------------
# 3. TechnicalIndicatorService D1 Normalization Delta-Check
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_technical_indicator_d1_normalization():
    """Verify D1 21:00 UTC vs 00:00 UTC timestamp normalization prevents redundant computation."""
    mock_session = create_mock_async_session()
    service = TechnicalIndicatorService(mock_session, {})

    # Mock DB query results for PriceOHLCV (21:00 UTC) and TechnicalIndicator (00:00 UTC)
    price_ts = datetime(2026, 10, 29, 21, 0, 0, tzinfo=timezone.utc)
    ind_ts = datetime(2026, 10, 29, 0, 0, 0, tzinfo=timezone.utc)

    # When query executes:
    # 1st query: select(PriceOHLCV timestamp) -> returns price_ts
    # 2nd query: select(TechnicalIndicator timestamp) -> returns ind_ts
    mock_price_res = MagicMock(scalar_one_or_none=MagicMock(return_value=price_ts))
    mock_ind_res = MagicMock(scalar_one_or_none=MagicMock(return_value=ind_ts))

    mock_session.execute = AsyncMock(side_effect=[mock_price_res, mock_ind_res])
    service.compute_and_save = AsyncMock(return_value=1500)

    # Calling compute_all_symbols on D1 should recognize same date and bypass compute_and_save
    results = await service.compute_all_symbols(["EURUSD"], ["D1"], force=False)
    assert results.get("EURUSD/D1") == 0
    assert service.compute_and_save.call_count == 0

    # If price_ts is from next day (2026-10-30), compute_and_save should be called
    next_day_price_ts = datetime(2026, 10, 30, 21, 0, 0, tzinfo=timezone.utc)
    mock_session.execute = AsyncMock(
        side_effect=[
            MagicMock(scalar_one_or_none=MagicMock(return_value=next_day_price_ts)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=ind_ts)),
        ]
    )
    results2 = await service.compute_all_symbols(["EURUSD"], ["D1"], force=False)
    assert results2.get("EURUSD/D1") == 1500
    assert service.compute_and_save.call_count == 1


# ------------------------------------------------------------------------------
# 4. TechnicalIndicatorService Incremental Save Verification
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_technical_indicator_incremental_save():
    """Verify incremental save only deletes and inserts 2 bars when historical bars exist."""
    mock_session = create_mock_async_session()
    # Remove mock_name so hasattr(session, '_mock_name') is False for this test
    if hasattr(mock_session, "_mock_name"):
        delattr(mock_session, "_mock_name")
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()

    service = TechnicalIndicatorService(mock_session, {})

    # Generate 5 bars of clean indicator data
    base_time = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    timestamps = [base_time + timedelta(hours=i) for i in range(5)]
    indicators = {ts: [{"name": "RSI_14", "value": 55.0}, {"name": "ATR_14", "value": 0.0015}] for ts in timestamps}

    # Case A: Historical bar (timestamps[-3]) exists in database (scalar returns ID 42)
    mock_res_existing = MagicMock(scalar_one_or_none=MagicMock(return_value=42))
    mock_res_delete = MagicMock()
    mock_res_insert = MagicMock()
    mock_session.execute = AsyncMock(side_effect=[mock_res_existing, mock_res_delete, mock_res_insert])

    saved_count = await service._save("EURUSD", "H1", indicators)
    # Only 2 bars saved (timestamps[-2:]) x 2 indicators = 4 entries
    assert saved_count == 4
    assert mock_session.commit.called

    # Case B: Cold start - historical bar does NOT exist (scalar returns None)
    mock_res_none = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    mock_session.execute = AsyncMock(side_effect=[mock_res_none, mock_res_delete, mock_res_insert])

    saved_all = await service._save("EURUSD", "H1", indicators)
    # All 5 bars saved x 2 indicators = 10 entries
    assert saved_all == 10
    assert mock_session.commit.called
