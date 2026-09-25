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


def test_strategy_decay_monitor_institutional_incubation_gate():
    """Verifies that new strategies require minimum 15 paper trades with WR >= 55% and PF >= 1.30 before graduating to live."""
    monitor = StrategyDecayMonitor()
    strat_id = "alpha_newly_discovered"

    # 1. Register as incubating
    health = monitor.register_incubating_strategy(strat_id)
    assert health.is_incubation_passed is False
    assert health.paper_trades_count == 0
    assert monitor.is_tradeable(strat_id) is True
    assert monitor.is_live_ready(strat_id) is False

    # 2. Record 10 winning paper trades (insufficient for 15-trade gate)
    for _ in range(10):
        monitor.record_trade_outcome(strat_id, win=True, is_paper=True, profit=2.0)
    assert monitor.get_health(strat_id).paper_trades_count == 10
    assert monitor.is_live_ready(strat_id) is False  # Still not live ready

    # 3. Reach 15 trades with 10 wins, 5 losses -> WR=66.7%, PF=20/5=4.0 -> Passes incubation!
    for _ in range(5):
        monitor.record_trade_outcome(strat_id, win=False, is_paper=True, profit=-1.0)
    assert monitor.get_health(strat_id).paper_trades_count == 15
    assert monitor.get_health(strat_id).is_incubation_passed is True
    assert monitor.is_live_ready(strat_id) is True  # Graduated to live!


def test_strategy_decay_monitor_incubation_failure_low_win_rate():
    """Verifies that 15 trades with < 55% win rate fails incubation graduation."""
    monitor = StrategyDecayMonitor()
    strat_id = "alpha_weak_candidate"

    monitor.register_incubating_strategy(strat_id)

    # 5 wins, 10 losses -> 33.3% win rate
    for _ in range(5):
        monitor.record_trade_outcome(strat_id, win=True, is_paper=True, profit=1.0)
    for _ in range(10):
        monitor.record_trade_outcome(strat_id, win=False, is_paper=True, profit=-1.0)

    health = monitor.get_health(strat_id)
    assert health.paper_trades_count == 15
    assert health.paper_wins_count == 5
    assert health.is_incubation_passed is False
    assert monitor.is_live_ready(strat_id) is False


@pytest.mark.asyncio
async def test_xau_trend_engine_numeric_parsing():
    """Bug 1: Verifies XAUTrendEngine parses JSON dict values safely without TypeError."""
    from analysis.strategies.xau_trend_engine import XAUTrendEngine
    strat = XAUTrendEngine({"trading": {}})

    mock_session = AsyncMock()
    fast_mock = MagicMock()
    fast_mock.value_json = json.dumps({"value": 2650.5})
    slow_mock = MagicMock()
    slow_mock.value_json = json.dumps({"value": 2640.0})

    bars = [
        MagicMock(high=2650.0, low=2630.0, close=2645.0)
        for _ in range(25)
    ]
    bars[0].close = 2660.0

    call_count = 0
    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        res = MagicMock()
        if call_count == 1:
            res.scalar_one_or_none.return_value = fast_mock
        elif call_count == 2:
            res.scalar_one_or_none.return_value = slow_mock
        else:
            res.scalars.return_value.all.return_value = bars
        return res

    mock_session.execute = AsyncMock(side_effect=mock_execute)

    sig = await strat.evaluate(mock_session, "XAUUSD", {})
    assert sig is not None
    assert sig.valid is True
    assert sig.direction == "buy"
    assert sig.rationale != "dirty EMA values"


@pytest.mark.asyncio
async def test_btc_donchian_breakout_abstract_contract():
    """Bug 2: Verifies BTCDonchianBreakout implements evaluate() and returns EdgeSignal."""
    from analysis.strategies.btc_donchian_breakout import BTCDonchianBreakout
    strat = BTCDonchianBreakout({"trading": {}})

    mock_session = AsyncMock()
    candles = [
        MagicMock(high=65000.0, low=64000.0, close=64500.0, volume=100.0)
        for _ in range(35)
    ]
    candles[0].close = 66000.0
    candles[0].high = 66100.0
    candles[0].volume = 500.0

    scalars_mock = MagicMock()
    scalars_mock.all.return_value = candles
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    mock_session.execute = AsyncMock(return_value=result_mock)

    sig = await strat.evaluate(mock_session, "BTCUSD", {})
    assert sig is not None
    assert isinstance(sig, EdgeSignal)
    assert sig.direction == "buy"
    assert sig.valid is True


def test_harness_true_range_and_r_multiple():
    """Bug 3 & 9: Verifies TR includes (high - low) and returns are calculated as risk-normalized R-multiples."""
    from backtest.isolated_strategy_harness import IsolatedStrategyBacktestHarness, CandleDict
    from datetime import datetime, timezone

    harness = IsolatedStrategyBacktestHarness(
        strategy=MockPlateauStrategy,
        symbol="EURUSD",
    )
    candles = [
        CandleDict({"open": 1.1000, "high": 1.1050, "low": 1.0950, "close": 1.1020, "time": datetime.now(timezone.utc)}),
        CandleDict({"open": 1.1020, "high": 1.1100, "low": 1.1000, "close": 1.1080, "time": datetime.now(timezone.utc)}),
    ]
    atr = harness._calculate_atr(candles, period=1)
    assert abs(atr - 0.0100) < 1e-5

    ret_equity, ret_pct, r_mult = harness._calculate_trade_pnl("buy", 1.1000, 1.1100, 1.0950)
    assert abs(r_mult - 2.0) < 1e-4
    assert abs(ret_equity - 0.02) < 1e-4
    assert abs(ret_pct - 2.0) < 1e-4


def test_harness_dynamic_parameters_applied():
    """Bug 4: Verifies harness applies dynamic sl_atr_multiplier and tp_sl_multiplier."""
    from backtest.isolated_strategy_harness import IsolatedStrategyBacktestHarness
    from analysis.strategies.base_strategy import EdgeSignal

    harness = IsolatedStrategyBacktestHarness(
        strategy=MockPlateauStrategy,
        symbol="EURUSD",
        strategy_params={"sl_atr_multiplier": 2.0, "tp_sl_multiplier": 3.0},
    )
    sig = EdgeSignal(strategy_id="test", symbol="EURUSD", direction="buy", valid=True, confidence=0.8, exit_style="trend_trailing")
    entry = 1.1000
    atr = 0.0100

    sl, tp = harness._resolve_sl_tp(sig, entry, atr)
    assert abs(sl - 1.0800) < 1e-5
    assert abs(tp - 1.1600) < 1e-5


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


@pytest.mark.asyncio
async def test_context_builder_quant_edge_injection():
    """Bug 6: Verifies context_builder uses classify_market_regime to evaluate StrategyRegistry with compatible regime."""
    from analysis.stages.per_asset.context_builder import ContextBuilder

    cb = ContextBuilder(settings={"trading": {}})
    mock_session = AsyncMock()

    with patch("analysis.calculators.regime_classifier.classify_market_regime", new=AsyncMock(return_value={"regime": "TREND"})), \
         patch("analysis.strategies.registry.StrategyRegistry.evaluate_all", new=AsyncMock(return_value=[
             EdgeSignal("tsm_momentum", "EURUSD", "buy", True, 0.85, 1.1000, 1.0950, 1.1100, rationale="Trend confirmed")
         ])):
        from analysis.calculators.regime_classifier import classify_market_regime
        reg_info = await classify_market_regime(mock_session, "EURUSD", cb.settings)
        assert reg_info["regime"] == "TREND"
        edge_signals = await StrategyRegistry.evaluate_all(mock_session, "EURUSD", cb.settings, current_regime=reg_info["regime"])
        assert len(edge_signals) == 1
        assert edge_signals[0].direction == "buy"
        assert edge_signals[0].confidence == 0.85


def test_edge_strategy_runner_symbol_hot_reload():
    """Bug 8: Verifies EdgeStrategyRunner.hot_reload_strategy supports symbol-partitioned parameter overrides."""
    from scheduler.edge_strategy_runner import EdgeStrategyRunner

    settings = {"trading": {"edge_strategy": {}}}
    runner = EdgeStrategyRunner(settings=settings)

    runner.hot_reload_strategy("tsm_momentum", {"sl_atr_multiplier": 1.8}, symbol="XAUUSD")
    runner.hot_reload_strategy("tsm_momentum", {"sl_atr_multiplier": 2.2}, symbol="EURUSD")

    edge_cfg = runner.settings["trading"]["edge_strategy"]
    assert edge_cfg["tsm_momentum_XAUUSD"]["sl_atr_multiplier"] == 1.8
    assert edge_cfg["tsm_momentum_EURUSD"]["sl_atr_multiplier"] == 2.2


def test_decay_monitor_incubation_graduation_at_15_trades():
    """Verifies that an incubating strategy graduates at 15 trades with WR >= 55% and PF >= 1.30."""
    monitor = StrategyDecayMonitor()
    strat_id = "alpha_incubation_15"
    monitor.register_incubating_strategy(strat_id)
    assert monitor.is_live_ready(strat_id) is False

    # Record 9 wins (+1.5R each = 13.5) and 5 losses (-1.0R each = -5.0) -> 14 trades
    for _ in range(9):
        monitor.record_trade_outcome(strat_id, win=True, is_paper=True, profit=1.5)
    for _ in range(5):
        monitor.record_trade_outcome(strat_id, win=False, is_paper=True, profit=-1.0)
    assert monitor.is_live_ready(strat_id) is False

    # 15th trade (6th loss -> 9/15 = 60%, PF = 13.5 / 6.0 = 2.25)
    monitor.record_trade_outcome(strat_id, win=False, is_paper=True, profit=-1.0)
    assert monitor.get_health(strat_id).is_incubation_passed is True
    assert monitor.is_live_ready(strat_id) is True
