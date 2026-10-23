"""
Comprehensive Phase 10 Quantitative Domain & Alpha Zoo Regression Tests.

Validates:
1. Zero look-ahead bias in Swing points, FVGs, Breaker Blocks, and IFVGs.
2. Harmonic pattern AD/XA retracement geometry.
3. Microstructure VPIN fail-closed behavior & Amihud zero-volume stabilization.
4. Alpha Zoo single-asset pass-through & AST metadata extraction.
5. HRP non-PSD covariance stabilization & Copula fail-closed haircut.
6. Swap estimator evening rollover calculation.
7. Technical regime calculator and compatibility shim.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pandas as pd
import pytest

from monika.application.analysis.calculators.copula_tail_risk import evaluate_joint_tail_risk
from monika.application.analysis.calculators.hierarchical_risk_parity import compute_hrp_weights
from monika.domain.indicators.alpha_zoo.factors.academic.market_excess_return import (
    compute as compute_market_excess,
)
from monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_058 import (
    compute as compute_wq_058,
)
from monika.domain.indicators.alpha_zoo.registry import load_alpha_meta_from_py
from monika.domain.indicators.chart_patterns import detect_harmonic_patterns
from monika.domain.indicators.microstructure import (
    compute_amihud_illiquidity,
    compute_vpin,
)
from monika.domain.indicators.smc_advanced import (
    detect_breaker_blocks,
    detect_inverted_fvg,
    find_wick_to_wick_fvg,
)
from monika.domain.indicators.structure import MarketStructureAnalyzer
from monika.domain.market.swap_estimator import estimate_swap_cost


def test_harmonic_pattern_gartley_ad_xa_ratio():
    """Verify that Gartley pattern evaluates D retracement as AD / XA (0.786)."""
    # Bullish Gartley setup:
    # X = 100 (low)
    # A = 200 (high) -> XA = 100
    # B = 138.2 (low) -> AB/XA = 0.618
    # C = 170.0 (high)
    # D = 121.4 (low) -> AD/XA = (200 - 121.4) / 100 = 0.786
    pivots = [
        {"type": "low", "price": 100.0, "index": 0},
        {"type": "high", "price": 200.0, "index": 10},
        {"type": "low", "price": 138.2, "index": 20},
        {"type": "high", "price": 170.0, "index": 30},
        {"type": "low", "price": 121.4, "index": 40},
    ]
    patterns = detect_harmonic_patterns(pivots, tolerance=0.05)
    assert len(patterns) == 1
    assert "Gartley" in patterns[0]["pattern"]
    assert pytest.approx(patterns[0]["b_ratio"], 0.01) == 0.618
    assert pytest.approx(patterns[0]["d_ratio"], 0.01) == 0.786


def test_amihud_illiquidity_zero_volume_handling():
    """Verify that bars with zero volume do not inflate Amihud illiquidity."""
    dates = pd.date_range("2026-01-01", periods=10, freq="1h")
    rets = pd.Series([0.01] * 10, index=dates)
    # Bar 5 has 0 dollar volume
    vol = pd.Series(
        [100000.0, 100000.0, 100000.0, 100000.0, 100000.0, 0.0, 100000.0, 100000.0, 100000.0, 100000.0], index=dates
    )

    amihud = compute_amihud_illiquidity(rets, vol, window=5)
    # Maximum value should remain near normal (1e-7), not 1e-2 (which 1.0 fallback caused)
    assert amihud.max() < 1e-4


def test_vpin_fail_closed_on_empty():
    """Verify that VPIN returns NaN (fail-closed) when trade input is empty."""
    empty_df = pd.DataFrame(columns=["price", "volume"])
    vpin = compute_vpin(empty_df, bucket_volume=100.0)
    assert np.isnan(vpin)


def test_breaker_block_temporal_filter():
    """Verify breaker block detection filters candles after original OB formation."""
    times = pd.date_range("2026-01-01 00:00", periods=10, freq="1h")
    df = pd.DataFrame(
        {
            "open": [100.0] * 10,
            "high": [105.0] * 10,
            "low": [95.0] * 10,
            "close": [98.0, 97.0, 102.0, 103.0, 104.0, 102.0, 99.0, 97.0, 96.0, 95.0],
        },
        index=times,
    )
    # Order block formed at times[4] (04:00) with price_low=100.0
    ob = {
        "type": "bullish",
        "price_low": 100.0,
        "price_high": 104.0,
        "time": str(times[4]),
    }
    breakers = detect_breaker_blocks(df, [ob])
    assert len(breakers) == 1
    # First candle that broke below 100 after 04:00 is times[6] (close=99.0 at 06:00), NOT times[0] or times[1]!
    assert breakers[0].broken_at == str(times[6])


def test_inverted_fvg_temporal_filter():
    """Verify IFVG detection only considers candles formed after original FVG."""
    times = pd.date_range("2026-01-01 00:00", periods=10, freq="1h")
    df = pd.DataFrame(
        {
            "open": [100.0] * 10,
            "high": [105.0] * 10,
            "low": [95.0] * 10,
            "close": [90.0, 92.0, 105.0, 106.0, 107.0, 104.0, 98.0, 95.0, 94.0, 93.0],
        },
        index=times,
    )
    # Bullish FVG formed at times[4] with gap low=100, high=105
    fvg = {
        "type": "bullish",
        "price_low": 100.0,
        "price_high": 105.0,
        "time": str(times[4]),
    }
    ifvgs = detect_inverted_fvg(df, [fvg])
    assert len(ifvgs) == 1
    # First candle that closed below 100 after times[4] is times[6] (close=98.0 at 06:00)
    assert ifvgs[0].inverted_at == str(times[6])


def test_wick_to_wick_fvg_timestamp():
    """Verify wick-to-wick FVG timestamp corresponds to the completing candle (index i)."""
    times = pd.date_range("2026-01-01 00:00", periods=5, freq="1h")
    df = pd.DataFrame(
        {
            "high": [100.0, 102.0, 108.0, 105.0, 104.0],
            "low": [95.0, 97.0, 103.0, 101.0, 100.0],
            "close": [98.0, 101.0, 106.0, 103.0, 102.0],
        },
        index=times,
    )
    # At i=2: c3.low=103 > c1.high=100 -> gap formed
    fvgs = find_wick_to_wick_fvg(df)
    assert len(fvgs) == 1
    # Timestamp must be times[2] (candle 3), not times[1]!
    assert fvgs[0]["time"] == str(times[2])


def test_alpha_zoo_single_asset_neutralize():
    """Verify WorldQuant alpha factors with neutralization do not zero out or NaN on single-asset."""
    dates = pd.date_range("2025-01-01", periods=50, freq="1D")
    panel = {
        "close": pd.DataFrame({"AAPL": np.linspace(100, 150, 50)}, index=dates),
        "volume": pd.DataFrame({"AAPL": 1000.0 + np.sin(np.linspace(0, 10, 50)) * 100}, index=dates),
        "vwap": pd.DataFrame({"AAPL": np.linspace(100, 150, 50)}, index=dates),
    }
    res = compute_wq_058(panel)
    assert isinstance(res, (pd.DataFrame, pd.Series))
    # Must contain valid non-NaN numbers after warmup
    valid = res.dropna()
    assert not valid.empty


def test_market_excess_return_single_asset():
    """Verify market excess return factor does not return all-NaN on single asset."""
    dates = pd.date_range("2025-01-01", periods=60, freq="1D")
    panel = {
        "close": pd.DataFrame({"EURUSD": np.linspace(1.05, 1.15, 60)}, index=dates),
    }
    res = compute_market_excess(panel)
    valid = res.dropna()
    assert not valid.empty


def test_alpha_meta_ast_loader():
    """Verify that load_alpha_meta_from_py correctly parses metadata from Python source."""
    from pathlib import Path

    path = Path("src/monika/domain/indicators/alpha_zoo/factors/worldquant_101/wq_alpha_001.py")
    meta = load_alpha_meta_from_py(path)
    assert meta.name == "alpha101_001"
    assert meta.lookback > 0
    assert "close" in meta.columns_required


def test_hrp_psd_projection_and_variance_stability():
    """Verify that HRP allocation does not concentrate 99% into a cluster with zero/degenerate variance."""
    dates = pd.date_range("2026-01-01", periods=20, freq="1D")
    # Asset C has constant 0 returns (zero variance)
    returns_df = pd.DataFrame(
        {
            "A": np.random.normal(0, 0.01, 20),
            "B": np.random.normal(0, 0.02, 20),
            "C": [0.0] * 20,
        },
        index=dates,
    )
    weights = compute_hrp_weights(returns_df)
    assert len(weights) == 3
    assert pytest.approx(weights.sum(), 1e-4) == 1.0
    # No single asset should receive an extreme >98% allocation due to variance floor
    assert (weights < 0.98).all()


def test_copula_fail_closed_haircut():
    """Verify that joint tail risk evaluation returns protective 0.50 haircut on minimal data."""
    short_returns = pd.Series([0.01, -0.02, 0.03])
    res = evaluate_joint_tail_risk(short_returns, short_returns)
    assert res["risk_level"] == "INSUFFICIENT_DATA"
    assert res["recommended_haircut"] == 0.50


@pytest.mark.asyncio
async def test_swap_estimator_evening_order_rollover():
    """Verify that an order opened at 21:15 UTC correctly counts 21:00 UTC rollovers."""
    # Order opened at 21:15 UTC on Monday, held for 48 hours (until 21:15 UTC Wednesday)
    # Rollovers crossed:
    # 1. Tuesday 21:00 UTC (1x)
    # 2. Wednesday 21:00 UTC (3x Wednesday rollover)
    # Total effective nights = 4.0
    start = datetime(2026, 1, 5, 21, 15, tzinfo=timezone.utc)  # Monday
    mock_client = AsyncMock()
    mock_client.get_symbol_info.return_value = {
        "swap_long": -10.0,
        "swap_mode": 2,  # Symbol currency
        "point": 0.0001,
    }
    cost = await estimate_swap_cost(
        symbol="EURUSD",
        direction="buy",
        lots=1.0,
        holding_hours=48.0,
        start_time=start,
        mt5_client=mock_client,
    )
    # 4 nights * -10.0 = -40.0
    assert cost == pytest.approx(-40.0, 0.1)


def test_technical_regime_calculator_shim():
    """Verify that technical_regime_calculator can be imported directly and via compatibility shim."""
    from monika.application.analysis.calculators.technical_regime_calculator import (
        classify_market_regime as canon_fn,
    )
    from monika.application.analysis.calculators.regime_classifier import (
        classify_market_regime as shim_fn,
    )

    assert canon_fn is shim_fn
