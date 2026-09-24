"""
Comprehensive Unit Tests for Overhauled Alpha Strategy Discovery & Paper Incubation Pipeline.
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from analysis.strategies.decay_monitor import StrategyDecayMonitor, StrategyHealth, DecayState
from analysis.strategies.base_strategy import EdgeSignal, EdgeStrategy
from analysis.strategies.registry import StrategyRegistry
from analysis.calculators.quant_plateau_optimizer import (
    QuantPlateauOptimizer,
    ParameterSpec,
    PlateauOptimizationResult,
)
from scheduler.alpha_discovery_scheduler import (
    AlphaDiscoveryScheduler,
    AlphaHypothesis,
    CandidateAlphaProposal,
    STRATEGY_PARAM_SPACES,
)
from analysis.arbitration.signal_arbitrator import SignalArbitrator, ArbitrationResult


class MockPlateauStrategy(EdgeStrategy):
    strategy_id = "mock_plateau_alpha"
    applicable_symbols = {"EURUSD"}

    async def evaluate(self, session, symbol, settings):
        return EdgeSignal(
            strategy_id=self.strategy_id,
            symbol=symbol,
            direction="buy",
            valid=True,
            confidence=0.82,
            entry_price=1.1000,
            stop_loss=1.0950,
            take_profit=1.1100,
        )


@pytest.fixture(autouse=True)
def clean_registry():
    orig_registry = dict(StrategyRegistry._registry)
    orig_dyn = dict(StrategyRegistry._dynamic_params)
    StrategyRegistry._registry = {"mock_plateau_alpha": MockPlateauStrategy}
    yield
    StrategyRegistry._registry = orig_registry
    StrategyRegistry._dynamic_params = orig_dyn


def test_strategy_decay_monitor_4_trade_incubation_gate():
    """Verifies that new strategies require strictly 4 paper trades before graduating to live."""
    monitor = StrategyDecayMonitor()
    strat_id = "alpha_newly_discovered"

    # 1. Register as incubating
    health = monitor.register_incubating_strategy(strat_id)
    assert health.is_incubation_passed is False
    assert health.paper_trades_count == 0
    assert monitor.is_tradeable(strat_id) is True
    assert monitor.is_live_ready(strat_id) is False

    # 2. Record 3 winning paper trades (insufficient for 4-trade gate)
    for _ in range(3):
        monitor.record_trade_outcome(strat_id, win=True, is_paper=True)
    assert monitor.get_health(strat_id).paper_trades_count == 3
    assert monitor.is_live_ready(strat_id) is False  # Still not live ready

    # 3. 4th winning paper trade -> passes incubation!
    monitor.record_trade_outcome(strat_id, win=True, is_paper=True)
    assert monitor.get_health(strat_id).paper_trades_count == 4
    assert monitor.get_health(strat_id).is_incubation_passed is True
    assert monitor.is_live_ready(strat_id) is True  # Graduated to live!


def test_strategy_decay_monitor_incubation_failure_low_win_rate():
    """Verifies that 4 trades with < 50% win rate fails incubation graduation."""
    monitor = StrategyDecayMonitor()
    strat_id = "alpha_weak_candidate"

    monitor.register_incubating_strategy(strat_id)

    # 1 win, 3 losses
    monitor.record_trade_outcome(strat_id, win=True, is_paper=True)
    monitor.record_trade_outcome(strat_id, win=False, is_paper=True)
    monitor.record_trade_outcome(strat_id, win=False, is_paper=True)
    monitor.record_trade_outcome(strat_id, win=False, is_paper=True)

    health = monitor.get_health(strat_id)
    assert health.paper_trades_count == 4
    assert health.paper_wins_count == 1
    assert health.is_incubation_passed is False
    assert monitor.is_live_ready(strat_id) is False


def test_strategy_decay_monitor_serialization_roundtrip():
    """Verifies that paper incubation attributes serialize and deserialize cleanly."""
    monitor = StrategyDecayMonitor()
    health = monitor.register_incubating_strategy("alpha_test_persist")
    health.paper_trades_count = 2
    health.paper_wins_count = 2

    d = monitor.to_dict()
    assert "alpha_test_persist" in d
    assert d["alpha_test_persist"]["paper_trades_count"] == 2
    assert d["alpha_test_persist"]["is_incubation_passed"] is False

    new_monitor = StrategyDecayMonitor()
    new_monitor.from_dict(d)
    restored = new_monitor.get_health("alpha_test_persist")
    assert restored.paper_trades_count == 2
    assert restored.paper_wins_count == 2
    assert restored.is_incubation_passed is False


@pytest.mark.asyncio
async def test_quant_signal_arbitrator_concordance():
    """Verifies SignalArbitrator awards concordant boost when Quant and LLM agree."""
    arbitrator = SignalArbitrator(settings={
        "trading": {
            "signal_arbitration": {
                "concordant_boost_confidence": 0.05,
                "quant_weight": 0.50,
                "llm_weight": 0.50,
                "empirical_joint_pooling": False,
            }
        }
    })

    quant_sig = EdgeSignal(
        strategy_id="mock_plateau_alpha",
        symbol="EURUSD",
        direction="buy",
        valid=True,
        confidence=0.80,
        entry_price=1.1000,
        stop_loss=1.0950,
        take_profit=1.1100,
    )

    llm_dec = {
        "decision": "buy",
        "confidence": 0.75,
        "risk_multiplier": 1.0,
        "entry_price": 1.1000,
        "stop_loss": 1.0950,
        "take_profit": 1.1100,
        "rationale": "Bullish divergence and macro tailwinds",
    }

    res = await arbitrator.arbitrate(
        session=None,
        symbol="EURUSD",
        quant_signal=quant_sig,
        llm_decision=llm_dec,
        vix_level=16.0,
        regime_info={"regime": "trending"},
    )

    assert res.decision == "buy"
    assert res.selected_source == "concordant"
    # raw mean = (0.80 + 0.75) / 2 = 0.775, + 0.05 boost = 0.825 -> 0.82 or 0.83
    assert res.confidence >= 0.80
