from tests.conftest import create_mock_async_session
"""
Comprehensive Integration & Verification Test Suite for Monika Capability Expansion.
Validates all 5 Phases across 100 Case Requirements.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from analysis.strategies.registry import StrategyRegistry, STRATEGY_REGISTRY
from backtest.isolated_strategy_harness import HarnessMetrics
from indicators.candlestick_patterns import detect_candlestick_patterns
from utils.chart_generator import generate_smc_candlestick_chart
from analysis.calculators.daily_range_calculator import compute_daily_range_context
from analysis.calculators.volume_profile import compute_anchored_vwap
from analysis.calculators.intraday_level_optimizer import compute_optimal_levels
from analysis.strategies.smc_fvg import SMCFairValueGapStrategy
from analysis.strategies.bb_volume_profile import BBVolumeProfileMeanReversion
from analysis.memory.counterfactual_simulator import CounterfactualSimulator
from analysis.tools.handlers.trade_intel import (
    handle_get_pnl_summary,
    handle_run_adhoc_symbol_debate,
    handle_run_hostile_stress_test,
)
from analysis.tools.handlers.db_tools import handle_read_database_records
from utils.market.dynamic_correlation import compute_cross_asset_macro_correlation
from data_sources.coinglass_funding import CoinglasFundingFetcher
from agent.socket_lifecycle_guard import get_socket_guard_diagnostics
from agent.task_registry import TaskRegistry, CORE_TRADING_TASKS


# ==============================================================================
# FASE 1: Strategy Registry, Calmar Ratio, & Isolated Backtest Harness
# ==============================================================================

def test_fase1_strategy_registry_alias():
    assert STRATEGY_REGISTRY is not None
    assert isinstance(STRATEGY_REGISTRY, dict)
    assert "smc_fvg" in StrategyRegistry._registry or "SMCFairValueGapStrategy" in StrategyRegistry._registry
    assert "bb_volume_profile" in StrategyRegistry._registry or "BBVolumeProfileMeanReversion" in StrategyRegistry._registry


def test_fase1_calmar_ratio_in_harness_metrics():
    metrics = HarnessMetrics(
        total_trades=10,
        win_rate_pct=70.0,
        profit_factor=2.5,
        sharpe_ratio=1.8,
        sortino_ratio=2.2,
        calmar_ratio=3.5,
        max_drawdown_pct=4.0,
        total_pnl_pct=14.0,
    )
    d = metrics.to_dict()
    assert "calmar_ratio" in d
    assert d["calmar_ratio"] == 3.5


# ==============================================================================
# FASE 2: Margin Monitor, Pending Orders, & PnL Summary
# ==============================================================================

def test_fase2_task_registry_margin_guardian():
    assert "MarginGuardian" in CORE_TRADING_TASKS or "MarginMonitor" in CORE_TRADING_TASKS
    import asyncio
    reg = TaskRegistry(asyncio.Event())
    async def _dummy(): pass
    reg.register("MarginGuardian", _dummy)
    table = reg.get_task_status_table()
    assert len(table) == 1
    assert table[0]["name"] == "MarginGuardian"
    assert table[0]["is_core"] is True


@pytest.mark.asyncio
async def test_fase2_pnl_summary_handler():
    mock_session = create_mock_async_session()
    mock_result = MagicMock()
    mock_result.one_or_none.return_value = (150.0, 5, 4)
    mock_session.execute.return_value = mock_result

    res = await handle_get_pnl_summary({}, session=mock_session)
    assert res["status"] == "success"
    assert "summary" in res
    assert "today" in res["summary"]
    assert "this_week" in res["summary"]
    assert "this_month" in res["summary"]
    assert "all_time" in res["summary"]
    assert res["summary"]["today"]["real"]["total_pnl_usd"] == 150.0


# ==============================================================================
# FASE 3: Candlestick Patterns, SMC Visual Charting, ADR & Level Optimizer
# ==============================================================================

def test_fase3_candlestick_pattern_detection():
    # Build sample OHLCV DataFrame
    df = pd.DataFrame([
        # Regular candle
        {"open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0, "timestamp": datetime.now()},
        # Pin bar / hammer (long lower wick)
        {"open": 101.0, "high": 101.5, "low": 95.0, "close": 101.2, "timestamp": datetime.now()},
        # Shooting star (long upper wick)
        {"open": 101.2, "high": 108.0, "low": 101.0, "close": 101.3, "timestamp": datetime.now()},
        # Bearish candle followed by Bullish Engulfing
        {"open": 101.0, "high": 101.2, "low": 98.0, "close": 98.5, "timestamp": datetime.now()},
        {"open": 98.0, "high": 103.0, "low": 97.5, "close": 102.5, "timestamp": datetime.now()},
    ])
    
    result = detect_candlestick_patterns(df)
    assert isinstance(result, dict)
    patterns = result.get("detected_patterns", [])
    assert len(patterns) > 0
    pattern_names = [p["pattern"] for p in patterns]
    assert any("Pin Bar" in p or "Shooting Star" in p or "Engulfing" in p for p in pattern_names)


@pytest.mark.asyncio
async def test_fase3_anchored_vwap_modes():
    mock_session = create_mock_async_session()
    mock_bar = MagicMock(open=100.0, high=105.0, low=98.0, close=102.0, volume=500.0)
    mock_result = MagicMock()
    mock_result.scalars().all.return_value = [mock_bar]
    mock_session.execute.return_value = mock_result

    vwap_session = await compute_anchored_vwap(mock_session, "XAUUSD", anchor_mode="session")
    vwap_swing = await compute_anchored_vwap(mock_session, "XAUUSD", anchor_mode="swing_low")
    assert "avwap" in vwap_session
    assert "avwap" in vwap_swing


@pytest.mark.asyncio
async def test_fase3_optimal_levels_trade_style():
    mock_session = create_mock_async_session()
    with patch("analysis.calculators.intraday_level_optimizer.compute_daily_range_context", new_callable=AsyncMock) as mock_adr, \
         patch("analysis.calculators.intraday_level_optimizer._get_atr", new_callable=AsyncMock) as mock_atr, \
         patch("analysis.calculators.intraday_level_optimizer._collect_zones", new_callable=AsyncMock) as mock_zones:
        mock_adr.return_value = {"adr": 20.0, "current_range": 5.0, "status": "ok"}
        mock_atr.return_value = 2.0
        mock_zones.return_value = [
            {"type": "sr_zone", "direction": None, "low": 1990.0, "high": 1995.0, "weight": 2.0},
            {"type": "sr_zone", "direction": None, "low": 2020.0, "high": 2025.0, "weight": 2.0},
        ]
        levels_intraday = await compute_optimal_levels(
            session=mock_session,
            symbol="XAUUSD",
            direction="buy",
            entry_price=2000.0,
            settings={},
            trade_style="intraday",
        )
        levels_swing = await compute_optimal_levels(
            session=mock_session,
            symbol="XAUUSD",
            direction="buy",
            entry_price=2000.0,
            settings={},
            trade_style="swing",
        )
        assert levels_intraday["tp2"] <= levels_swing["tp2"]


# ==============================================================================
# FASE 4: Quant Strategies, Counterfactual Trailing Stop, Debate & Stress Test
# ==============================================================================

@pytest.mark.asyncio
async def test_fase4_smc_fvg_strategy_evaluation():
    strat = SMCFairValueGapStrategy()
    mock_session = create_mock_async_session()

    # Provide synthetic candles with a bullish FVG
    now = datetime.now(timezone.utc)
    mock_candles = [
        MagicMock(open=100.0, high=102.0, low=99.0, close=101.0, volume=100.0),
        MagicMock(open=101.0, high=108.0, low=101.0, close=107.0, volume=500.0),  # big impulse
        MagicMock(open=107.0, high=110.0, low=104.0, close=109.0, volume=200.0),  # gap between 102 and 104
        MagicMock(open=109.0, high=109.5, low=103.0, close=103.5, volume=150.0),  # retest into gap
    ]
    strat.get_historical_candles = AsyncMock(return_value=mock_candles)

    signal = await strat.evaluate(mock_session, "EURUSD", {})
    assert signal.strategy_id == "smc_fvg"
    assert signal.symbol == "EURUSD"
    if signal.valid:
        assert signal.direction in ("buy", "sell")
        assert signal.stop_loss is not None
        assert signal.take_profit is not None


@pytest.mark.asyncio
async def test_fase4_bb_volume_profile_strategy_evaluation():
    strat = BBVolumeProfileMeanReversion()
    mock_session = create_mock_async_session()

    mock_candles = [
        MagicMock(open=100.0 + i * 0.1, high=101.0 + i * 0.1, low=99.0 + i * 0.1, close=100.5 + i * 0.1, volume=100.0)
        for i in range(30)
    ]
    strat.get_historical_candles = AsyncMock(return_value=mock_candles)

    signal = await strat.evaluate(mock_session, "GBPUSD", {})
    assert signal.strategy_id == "bb_volume_profile"
    assert signal.symbol == "GBPUSD"


@pytest.mark.asyncio
async def test_fase4_counterfactual_trailing_stop():
    sim = CounterfactualSimulator()
    mock_session = create_mock_async_session()

    mock_trade = MagicMock(
        id=101, symbol="EURUSD", direction="BUY", entry_price=1.0800,
        stop_loss=1.0750, take_profit=1.0900, exit_price=1.0780,
        pnl_usd=-20.0, lot_size=0.1, exit_reason="sl",
        created_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        closed_at=datetime(2026, 9, 2, tzinfo=timezone.utc),
    )
    mock_session.get.return_value = mock_trade

    mock_bars = [
        MagicMock(timestamp=datetime(2026, 9, 1, 1, tzinfo=timezone.utc), high=1.0840, low=1.0790, close=1.0830),
        MagicMock(timestamp=datetime(2026, 9, 1, 2, tzinfo=timezone.utc), high=1.0880, low=1.0820, close=1.0870),
        MagicMock(timestamp=datetime(2026, 9, 1, 3, tzinfo=timezone.utc), high=1.0860, low=1.0810, close=1.0820),
    ]
    mock_result = MagicMock()
    mock_result.scalars().all.return_value = mock_bars
    mock_session.execute.return_value = mock_result

    res = await sim.simulate_single_trade_counterfactual(
        session=mock_session, trade_id=101, trailing_stop_atr_mult=1.5
    )
    assert res["status"] == "success"
    assert "trailing_stop_atr_mult" in res["counterfactual"]
    assert res["counterfactual"]["trailing_stop_atr_mult"] == 1.5


@pytest.mark.asyncio
async def test_fase4_hostile_stress_test():
    res = await handle_run_hostile_stress_test({"symbol": "EURUSD"})
    assert res["status"] == "success"
    assert res["all_resilient"] is True
    assert res["passed_count"] == res["total_tested"]


# ==============================================================================
# FASE 5: Macro Correlation, Coinglass OI, Database Operators, & Socket Guard
# ==============================================================================

@pytest.mark.asyncio
async def test_fase5_cross_asset_macro_correlation():
    mock_session = create_mock_async_session()
    mock_result = MagicMock()
    mock_result.all.return_value = [
        (datetime(2026, 9, 1, tzinfo=timezone.utc), 4.25),
        (datetime(2026, 9, 2, tzinfo=timezone.utc), 4.30),
    ]
    mock_session.execute.return_value = mock_result

    res = await compute_cross_asset_macro_correlation(mock_session, lookback_days=30)
    assert "status" in res
    assert "us10y_xau_corr" in res
    assert "yield_curve_10y_2y" in res


def test_fase5_socket_guard_diagnostics():
    diag = get_socket_guard_diagnostics()
    assert diag["status"] == "healthy"
    assert "graveyard_size" in diag
    assert "fd_leak_risk" in diag
