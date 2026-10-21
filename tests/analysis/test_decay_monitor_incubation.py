"""Phase 1: incubation must be earned with real paper results only.

The former ``CORE_STRATEGY_IDS`` list auto-passed incubation for a hardcoded set of
strategy ids, and a persisted "passed" flag was trusted even without paper trades.
Both loopholes are closed.
"""

import pytest

from monika.application.analysis.strategies.decay_monitor import (
    DecayState,
    StrategyDecayMonitor,
)


def test_no_strategy_is_auto_passed_without_paper_results():
    monitor = StrategyDecayMonitor()

    for strategy_id in (
        "smt_divergence",
        "bb_volume_profile",
        "tokyo_open_sweep",
        "vwap_mean_reversion",
        "tsm_momentum",
        "liquidity_sweep",
        "some_unknown_alpha",
    ):
        health = monitor.get_health(strategy_id)
        assert health.is_incubation_passed is False, strategy_id
        assert monitor.is_live_ready(strategy_id) is False, strategy_id
        assert "Incubating" in health.reason


def test_incubation_is_granted_by_real_paper_results():
    monitor = StrategyDecayMonitor()
    strategy_id = "paper_proven_alpha"

    monitor.register_incubating_strategy(strategy_id)
    assert monitor.get_health(strategy_id).is_incubation_passed is False

    for _ in range(StrategyDecayMonitor.MIN_INCUBATION_TRADES - 1):
        monitor.record_trade_outcome(strategy_id, win=True, is_paper=True, profit=2.0)
    assert monitor.get_health(strategy_id).is_incubation_passed is False
    assert monitor.is_live_ready(strategy_id) is False

    monitor.record_trade_outcome(strategy_id, win=True, is_paper=True, profit=2.0)
    health = monitor.get_health(strategy_id)
    assert health.is_incubation_passed is True
    assert health.paper_trades_count == StrategyDecayMonitor.MIN_INCUBATION_TRADES
    assert monitor.is_live_ready(strategy_id) is True


def test_live_outcomes_do_not_count_as_incubation_evidence():
    monitor = StrategyDecayMonitor()
    strategy_id = "live_only_alpha"

    for _ in range(StrategyDecayMonitor.MIN_INCUBATION_TRADES):
        monitor.record_trade_outcome(strategy_id, win=True, is_paper=False, profit=2.0)

    health = monitor.get_health(strategy_id)
    assert health.paper_trades_count == 0
    assert health.is_incubation_passed is False
    assert monitor.is_live_ready(strategy_id) is False


def test_stale_passed_flag_without_paper_trades_is_sanitized():
    monitor = StrategyDecayMonitor()
    monitor.from_dict(
        {
            "legacy_core_alpha": {
                "strategy_id": "legacy_core_alpha",
                "state": "active",
                "is_incubation_passed": True,
                "paper_trades_count": 0,
                "paper_wins_count": 0,
            }
        }
    )

    health = monitor.get_health("legacy_core_alpha")
    assert health.is_incubation_passed is False
    assert monitor.is_live_ready("legacy_core_alpha") is False


def test_quarantine_wins_over_incubation_state():
    monitor = StrategyDecayMonitor()
    quarantined = "smc_fvg"

    for _ in range(StrategyDecayMonitor.MIN_INCUBATION_TRADES):
        monitor.record_trade_outcome(quarantined, win=True, is_paper=True, profit=2.0)

    health = monitor.get_health(quarantined)
    assert health.state == DecayState.DISABLED
    assert health.is_incubation_passed is False
    assert monitor.is_tradeable(quarantined) is False
    assert monitor.is_live_ready(quarantined) is False
