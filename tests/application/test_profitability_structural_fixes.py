"""
Tests for Monika Profitability Structural Fixes.
Verifies de-gridlocked mechanical gates, strategy governance, self-contained brackets,
and configuration parity.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from monika.application.analysis.strategies.base_strategy import (
    EdgeSignal,
    PROMOTED_EMPIRICAL_STRATEGIES,
    QUARANTINED_STRATEGY_IDS,
)
from monika.application.analysis.strategies.registry import StrategyRegistry
from monika.application.analysis.strategies.tokyo_sweep import TokyoSweepStrategy
from monika.application.analysis.strategies.liquidity_sweep_edge import LiquiditySweepStructuralShift
from monika.application.analysis.tools.mixins.analysis_validation import AssetAnalysisValidationMixin


def test_strategy_governance_parity():
    """Verify xti_pairs_readiness is quarantined and tokyo_open_sweep & liquidity_sweep are promoted."""
    assert "xti_pairs_readiness" in QUARANTINED_STRATEGY_IDS
    assert "xti_pairs_readiness" not in PROMOTED_EMPIRICAL_STRATEGIES

    assert "tokyo_open_sweep" in PROMOTED_EMPIRICAL_STRATEGIES
    assert "tokyo_open_sweep" not in QUARANTINED_STRATEGY_IDS
    assert TokyoSweepStrategy.applicable_symbols == {"USDJPY"}

    assert "liquidity_sweep" in PROMOTED_EMPIRICAL_STRATEGIES
    assert "liquidity_sweep" not in QUARANTINED_STRATEGY_IDS


def test_volatility_regime_error_classification():
    """Verify that volatility squeeze and volatility regime errors are classified as GATE_FIXABLE."""
    mixin = AssetAnalysisValidationMixin()

    # Volatility regime gate is fixable (allows agent to switch to structural limit/breakout)
    err_class = mixin._classify_validation_errors(
        ["VOLATILITY REGIME GATE: BB width in squeeze — market order in squeeze is prone to chop."]
    )
    assert err_class == "GATE_FIXABLE"

    err_squeeze = mixin._classify_validation_errors(["volatility squeeze detected on H4"])
    assert err_squeeze == "GATE_FIXABLE"

    # Truly fatal gate stays fatal (returns "GATE")
    err_macro = mixin._classify_validation_errors(["macro bias gate: strong conflict with D1 direction"])
    assert err_macro == "GATE"


@pytest.mark.asyncio
async def test_liquidity_sweep_produces_executable_bracket():
    """Verify LiquiditySweepStructuralShift produces complete, executable EdgeSignal brackets."""
    strat = LiquiditySweepStructuralShift()
    session = AsyncMock()

    # Mock candle return
    from monika.application.analysis.strategies.base_strategy import CandleDict

    c1 = CandleDict(
        {
            "timestamp": "2026-10-20T10:00:00Z",
            "open": 150.0,
            "high": 150.5,
            "low": 149.8,
            "close": 150.2,
            "volume": 100.0,
        }
    )
    c2 = CandleDict(
        {
            "timestamp": "2026-10-20T11:00:00Z",
            "open": 150.2,
            "high": 150.8,
            "low": 150.1,
            "close": 150.5,
            "volume": 120.0,
        }
    )

    strat.get_historical_candles = AsyncMock(return_value=[c1, c2])

    from unittest.mock import patch

    with (
        patch(
            "monika.application.analysis.strategies.liquidity_sweep_edge.detect_liquidity_sweep", new_callable=AsyncMock
        ) as mock_detect,
        patch(
            "monika.application.analysis.calculators.intraday_level_optimizer._get_atr", new_callable=AsyncMock
        ) as mock_atr,
    ):
        mock_detect.return_value = {
            "structure_confirmed": True,
            "volume_confirmed": True,
            "valid_for_direction": "buy",
            "sweep_price": 149.50,
            "reasons": ["sell_side sweep confirmed by ChoCH/BOS"],
        }
        mock_atr.return_value = 0.50

        sig = await strat.evaluate(session=session, symbol="USDJPY", settings={})

        assert sig.valid is True
        assert sig.direction == "buy"
        assert sig.entry_price == 150.5
        assert sig.stop_loss is not None
        assert sig.take_profit is not None
        assert sig.stop_loss < sig.entry_price < sig.take_profit
        assert sig.is_executable(min_rr=1.5) is True


def test_edge_signal_physical_geometry_guard():
    """Verify that inverted stops or insufficient R:R fail is_executable validation."""
    # Inverted BUY SL (SL > Entry)
    inverted_buy = EdgeSignal(
        strategy_id="test",
        symbol="USDJPY",
        direction="buy",
        valid=True,
        confidence=0.8,
        entry_price=150.0,
        stop_loss=150.5,  # Inverted!
        take_profit=152.0,
    )
    assert inverted_buy.is_executable() is False

    # Inverted SELL SL (SL < Entry)
    inverted_sell = EdgeSignal(
        strategy_id="test",
        symbol="USDJPY",
        direction="sell",
        valid=True,
        confidence=0.8,
        entry_price=150.0,
        stop_loss=149.5,  # Inverted!
        take_profit=148.0,
    )
    assert inverted_sell.is_executable() is False

    # Valid BUY
    valid_buy = EdgeSignal(
        strategy_id="test",
        symbol="USDJPY",
        direction="buy",
        valid=True,
        confidence=0.8,
        entry_price=150.0,
        stop_loss=149.0,
        take_profit=152.0,
    )
    assert valid_buy.is_executable(min_rr=1.5) is True


def test_regime_compatibility_alias_resolution():
    """Verify that RANGE/RANGING, CHOP/CHOPPY, and TREND/STRONG_TREND aliases resolve correctly."""
    from monika.application.analysis.strategies.base_strategy import EdgeStrategy

    class RangingStrategy(EdgeStrategy):
        strategy_id = "test_ranging"
        compatible_regimes = {"RANGING", "MEAN_REVERTING"}

        async def evaluate(self, session, symbol, settings, as_of=None):
            return EdgeSignal(self.strategy_id, symbol, None, False, 0.0)

    strat = RangingStrategy()
    assert strat.is_regime_compatible("RANGE") is True
    assert strat.is_regime_compatible("RANGING") is True
    assert strat.is_regime_compatible("MEAN_REVERTING") is True
    assert strat.is_regime_compatible("TREND") is False

    class TrendingStrategy(EdgeStrategy):
        strategy_id = "test_trending"
        compatible_regimes = {"TREND", "STRONG_TREND"}

        async def evaluate(self, session, symbol, settings, as_of=None):
            return EdgeSignal(self.strategy_id, symbol, None, False, 0.0)

    t_strat = TrendingStrategy()
    assert t_strat.is_regime_compatible("TREND") is True
    assert t_strat.is_regime_compatible("STRONG_TREND") is True
    assert t_strat.is_regime_compatible("TRENDING") is True
    assert t_strat.is_regime_compatible("RANGE") is False


@pytest.mark.asyncio
async def test_tp_structural_mapping_adr_expansion_acceptance():
    """Verify that TP falling inside verified ADR expansion band is accepted."""
    mixin = AssetAnalysisValidationMixin()
    mixin.settings = {"trading": {"risk": {"structural_snap_tolerance_atr_mult": 0.4}}}
    mixin.session = AsyncMock()

    # Empty DB structure returns
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mixin.session.execute.return_value = mock_result

    adr_ctx = {
        "target_tp_min_distance": 0.30,
        "target_tp_max_distance": 0.60,
        "band_tolerance_pct": 0.15,
    }

    # TP distance within ADR target band
    errors = await mixin._validate_tp_structural_target(
        symbol="USDJPY",
        direction="buy",
        tp_price=150.45,  # within ADR band of 150.00
        atr=0.25,
        adr_ctx=adr_ctx,
    )
    assert len(errors) == 0
