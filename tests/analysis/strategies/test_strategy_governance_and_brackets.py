"""
Unit tests for Strategy Governance, StrategyTier, and EdgeSignal bracket integrity.
Verifies Phase 3 requirements of the Monika Profitability Remediation Plan.
"""

import pytest

from monika.application.analysis.strategies.base_strategy import (
    EdgeSignal,
    EdgeStrategy,
    StrategyTier,
    QUARANTINED_STRATEGY_IDS,
    PROMOTED_EMPIRICAL_STRATEGIES,
)
from monika.application.analysis.strategies.registry import StrategyRegistry
from monika.application.backtest.isolated_strategy_harness import IsolatedStrategyBacktestHarness


class DummyStrategy(EdgeStrategy):
    strategy_id = "dummy_test_strategy"


def test_edge_signal_is_executable_valid_buy():
    sig = EdgeSignal(
        strategy_id="test_strat",
        symbol="EURUSD",
        direction="buy",
        valid=True,
        confidence=0.85,
        entry_price=1.1000,
        stop_loss=1.0950,  # 50 pips risk
        take_profit=1.1100,  # 100 pips reward (R:R = 2.0)
    )
    assert sig.is_executable(min_rr=1.0) is True
    assert sig.is_executable(min_rr=1.5) is True
    assert sig.is_executable(min_rr=2.5) is False


def test_edge_signal_is_executable_valid_sell():
    sig = EdgeSignal(
        strategy_id="test_strat",
        symbol="EURUSD",
        direction="sell",
        valid=True,
        confidence=0.85,
        entry_price=1.1000,
        stop_loss=1.1050,  # 50 pips risk
        take_profit=1.0900,  # 100 pips reward (R:R = 2.0)
    )
    assert sig.is_executable(min_rr=1.0) is True
    assert sig.is_executable(min_rr=1.8) is True
    assert sig.is_executable(min_rr=2.5) is False


def test_edge_signal_is_executable_rejects_inverted_brackets():
    # Buy with SL above Entry
    bad_buy = EdgeSignal(
        strategy_id="test_strat",
        symbol="EURUSD",
        direction="buy",
        valid=True,
        confidence=0.85,
        entry_price=1.1000,
        stop_loss=1.1050,
        take_profit=1.1150,
    )
    assert bad_buy.is_executable() is False

    # Sell with SL below Entry
    bad_sell = EdgeSignal(
        strategy_id="test_strat",
        symbol="EURUSD",
        direction="sell",
        valid=True,
        confidence=0.85,
        entry_price=1.1000,
        stop_loss=1.0950,
        take_profit=1.0900,
    )
    assert bad_sell.is_executable() is False


def test_edge_signal_is_executable_rejects_missing_or_invalid_fields():
    # Invalid flag
    sig = EdgeSignal(
        strategy_id="test_strat",
        symbol="EURUSD",
        direction="buy",
        valid=False,
        confidence=0.85,
        entry_price=1.1000,
        stop_loss=1.0950,
        take_profit=1.1100,
    )
    assert sig.is_executable() is False

    # None direction
    sig.valid = True
    sig.direction = None
    assert sig.is_executable() is False

    # Missing stop loss
    sig.direction = "buy"
    sig.stop_loss = None
    assert sig.is_executable() is False

    # Zero entry price
    sig.stop_loss = 1.0950
    sig.entry_price = 0.0
    assert sig.is_executable() is False


def test_edge_strategy_build_bracket():
    # Buy bracket
    sl_buy, tp_buy = EdgeStrategy.build_bracket(
        entry_price=100.0,
        direction="buy",
        atr=2.0,
        atr_multiplier_sl=1.5,
        risk_reward_ratio=2.0,
    )
    # SL = 100 - (2 * 1.5) = 97.0
    # TP = 100 + (3 * 2.0) = 106.0
    assert sl_buy == 97.0
    assert tp_buy == 106.0

    # Sell bracket
    sl_sell, tp_sell = EdgeStrategy.build_bracket(
        entry_price=100.0,
        direction="sell",
        atr=2.0,
        atr_multiplier_sl=1.5,
        risk_reward_ratio=2.0,
    )
    # SL = 100 + 3.0 = 103.0
    # TP = 100 - 6.0 = 94.0
    assert sl_sell == 103.0
    assert tp_sell == 94.0

    # Invalid ATR or entry
    with pytest.raises(ValueError):
        EdgeStrategy.build_bracket(entry_price=0.0, direction="buy", atr=1.0)

    with pytest.raises(ValueError):
        EdgeStrategy.build_bracket(entry_price=100.0, direction="invalid", atr=1.0)


def test_strategy_tiers_and_registry_classification():
    # Quarantined strategy
    for q_id in ("smc_fvg", "btc_donchian_breakout", "bollinger_reversion", "gbpusd_trend_breakout"):
        assert StrategyRegistry.get_tier(q_id) == StrategyTier.QUARANTINED
        assert q_id in QUARANTINED_STRATEGY_IDS

    # Validated strategy
    for v_id in ("smt_divergence", "bb_volume_profile", "tokyo_open_sweep", "vwap_mean_reversion"):
        assert StrategyRegistry.get_tier(v_id) == StrategyTier.VALIDATED
        assert v_id in PROMOTED_EMPIRICAL_STRATEGIES

    # Experimental strategy
    assert StrategyRegistry.get_tier("unpromoted_novel_strategy") == StrategyTier.EXPERIMENTAL


def test_isolated_harness_rejects_synthetic_bracket_fabrication():
    harness_no_params = IsolatedStrategyBacktestHarness(
        strategy=DummyStrategy,
        symbol="EURUSD",
        strategy_params={},
    )
    sig_no_sl = EdgeSignal(
        strategy_id="dummy",
        symbol="EURUSD",
        direction="buy",
        valid=True,
        confidence=0.8,
    )
    # Harness must not fabricate synthetic default 1.2 / 2.0 brackets
    sl, tp = harness_no_params._resolve_sl_tp(sig_no_sl, entry_price=1.1000, atr=0.0050)
    assert sl is None
    assert tp is None

    # Self-contained signal preserves its own levels
    sig_with_sl = EdgeSignal(
        strategy_id="dummy",
        symbol="EURUSD",
        direction="buy",
        valid=True,
        confidence=0.8,
        entry_price=1.1000,
        stop_loss=1.0950,
        take_profit=1.1100,
    )
    sl_self, tp_self = harness_no_params._resolve_sl_tp(sig_with_sl, entry_price=1.1000, atr=0.0050)
    assert sl_self == 1.0950
    assert tp_self == 1.1100
