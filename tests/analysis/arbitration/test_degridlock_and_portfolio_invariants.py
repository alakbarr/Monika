import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from monika.application.analysis.arbitration.signal_arbitrator import SignalArbitrator
from monika.application.analysis.strategies.base_strategy import EdgeSignal, PROMOTED_EMPIRICAL_STRATEGIES
from monika.application.analysis.strategies.decay_monitor import (
    StrategyDecayMonitor,
    get_strategy_decay_monitor,
)
from monika.application.analysis.strategies.liquidity_sweep_edge import LiquiditySweepStructuralShift

STRATEGY_ID = "tokyo_open_sweep"


def _make_live_ready(strategy_id: str) -> None:
    """A strategy may only override the LLM after real paper-trade results."""
    monitor = get_strategy_decay_monitor()
    monitor.register_incubating_strategy(strategy_id)
    for _ in range(StrategyDecayMonitor.MIN_INCUBATION_TRADES):
        monitor.record_trade_outcome(strategy_id, win=True, is_paper=True, profit=2.0)
    assert monitor.is_live_ready(strategy_id) is True


@pytest.fixture(autouse=True)
def _reset_decay_monitor():
    yield
    StrategyDecayMonitor.reset()


def test_liquidity_sweep_pruned_symbols():
    """Verify GBPUSD and XAUUSD are pruned from liquidity_sweep to prevent empirical alpha decay."""
    strat = LiquiditySweepStructuralShift()
    assert "GBPUSD" not in strat.applicable_symbols
    assert "XAUUSD" not in strat.applicable_symbols
    assert strat.applicable_symbols == {"EURUSD", "USDJPY", "AUDUSD"}
    assert not strat.is_enabled("GBPUSD")
    assert not strat.is_enabled("XAUUSD")
    assert strat.is_enabled("USDJPY")
    assert strat.is_enabled("EURUSD")
    assert strat.is_enabled("AUDUSD")


def test_no_hardcoded_promotion_invariants():
    """Promotion is evidence-driven; no hardcoded whitelist may survive."""
    assert PROMOTED_EMPIRICAL_STRATEGIES == set()


@pytest.mark.asyncio
async def test_live_ready_strategy_degridlocking_on_llm_wait():
    """
    A quant strategy with real paper results may break the LLM 'wait' deadlock,
    but only with TimesFM directional confirmation.
    """
    _make_live_ready(STRATEGY_ID)
    arbitrator = SignalArbitrator(
        settings={"trading": {"signal_arbitration": {"quant_priority_risk_multiplier": 0.70}}}
    )

    quant_signal = EdgeSignal(
        strategy_id=STRATEGY_ID,
        symbol="USDJPY",
        direction="buy",
        valid=True,
        confidence=0.75,
        entry_price=150.0,
        stop_loss=149.5,
        take_profit=151.0,
        meta={"is_incubating": False},
    )

    llm_decision = {
        "decision": "wait",
        "confidence": 0.50,
        "rationale": "No catalyst present, waiting for London open.",
    }

    session_mock = AsyncMock()
    session_mock.add = MagicMock()
    nested_ctx = AsyncMock()
    nested_ctx.__aenter__.return_value = None
    nested_ctx.__aexit__.return_value = None
    session_mock.begin_nested = MagicMock(return_value=nested_ctx)

    with patch(
        "monika.infrastructure.ml.timesfm_engine.TimesFMEngine.get_latest_forecast", new_callable=AsyncMock
    ) as mock_tfm:
        mock_tfm.return_value = {"quantile_skew": 0.30}  # Confirms BUY

        res = await arbitrator.arbitrate(
            session=session_mock,
            symbol="USDJPY",
            quant_signal=quant_signal,
            llm_decision=llm_decision,
            regime_info={"regime": "ranging"},
        )

    assert res.decision == "buy"
    assert res.selected_source == "quant"
    assert res.risk_multiplier == 0.85
    assert "confirmation" in res.arbitration_reason


@pytest.mark.asyncio
async def test_live_ready_strategy_needs_timesfm_confirmation_on_llm_wait():
    """Without TimesFM confirmation the LLM wait stance must be preserved."""
    _make_live_ready(STRATEGY_ID)
    arbitrator = SignalArbitrator(
        settings={"trading": {"signal_arbitration": {"quant_priority_risk_multiplier": 0.70}}}
    )

    quant_signal = EdgeSignal(
        strategy_id=STRATEGY_ID,
        symbol="USDJPY",
        direction="buy",
        valid=True,
        confidence=0.75,
        entry_price=150.0,
        stop_loss=149.5,
        take_profit=151.0,
        meta={"is_incubating": False},
    )

    llm_decision = {
        "decision": "wait",
        "confidence": 0.50,
        "rationale": "No catalyst present, waiting for London open.",
    }

    session_mock = AsyncMock()
    session_mock.add = MagicMock()
    nested_ctx = AsyncMock()
    nested_ctx.__aenter__.return_value = None
    nested_ctx.__aexit__.return_value = None
    session_mock.begin_nested = MagicMock(return_value=nested_ctx)

    with patch(
        "monika.infrastructure.ml.timesfm_engine.TimesFMEngine.get_latest_forecast", new_callable=AsyncMock
    ) as mock_tfm:
        mock_tfm.return_value = {"quantile_skew": 0.0}  # Neutral

        res = await arbitrator.arbitrate(
            session=session_mock,
            symbol="USDJPY",
            quant_signal=quant_signal,
            llm_decision=llm_decision,
            regime_info={"regime": "ranging"},
        )

    assert res.decision == "wait"
    assert res.risk_multiplier == 0.0
    assert "directional confirmation" in res.arbitration_reason


@pytest.mark.asyncio
async def test_incubating_strategy_cannot_override_llm_wait():
    """Without real paper results the strategy stays incubating and cannot override."""
    arbitrator = SignalArbitrator(settings={"trading": {"signal_arbitration": {}}})

    quant_signal = EdgeSignal(
        strategy_id="brand_new_alpha",
        symbol="USDJPY",
        direction="buy",
        valid=True,
        confidence=0.75,
        entry_price=150.0,
        stop_loss=149.5,
        take_profit=151.0,
        meta={"is_incubating": True},
    )

    llm_decision = {
        "decision": "wait",
        "confidence": 0.50,
        "rationale": "Waiting for direction.",
    }

    session_mock = AsyncMock()
    session_mock.add = MagicMock()
    nested_ctx = AsyncMock()
    nested_ctx.__aenter__.return_value = None
    nested_ctx.__aexit__.return_value = None
    session_mock.begin_nested = MagicMock(return_value=nested_ctx)

    with patch(
        "monika.infrastructure.ml.timesfm_engine.TimesFMEngine.get_latest_forecast", new_callable=AsyncMock
    ) as mock_tfm:
        mock_tfm.return_value = {"quantile_skew": 0.30}

        res = await arbitrator.arbitrate(
            session=session_mock,
            symbol="USDJPY",
            quant_signal=quant_signal,
            llm_decision=llm_decision,
            regime_info={"regime": "ranging"},
        )

    assert res.decision == "wait"
    assert res.risk_multiplier == 0.0
    assert "incubating" in res.arbitration_reason


@pytest.mark.asyncio
async def test_live_ready_strategy_suppressed_when_timesfm_opposes():
    """Verify a live-ready quant signal is safely suppressed if TimesFM actively opposes direction."""
    _make_live_ready(STRATEGY_ID)
    arbitrator = SignalArbitrator(settings={"trading": {"signal_arbitration": {}}})

    quant_signal = EdgeSignal(
        strategy_id=STRATEGY_ID,
        symbol="USDJPY",
        direction="buy",
        valid=True,
        confidence=0.75,
        entry_price=150.0,
        stop_loss=149.5,
        take_profit=151.0,
        meta={"is_incubating": False},
    )

    llm_decision = {
        "decision": "wait",
        "confidence": 0.50,
        "rationale": "Waiting for direction.",
    }

    session_mock = AsyncMock()
    session_mock.add = MagicMock()
    nested_ctx = AsyncMock()
    nested_ctx.__aenter__.return_value = None
    nested_ctx.__aexit__.return_value = None
    session_mock.begin_nested = MagicMock(return_value=nested_ctx)

    with patch(
        "monika.infrastructure.ml.timesfm_engine.TimesFMEngine.get_latest_forecast", new_callable=AsyncMock
    ) as mock_tfm:
        mock_tfm.return_value = {"quantile_skew": -0.25}  # Opposes BUY

        res = await arbitrator.arbitrate(
            session=session_mock,
            symbol="USDJPY",
            quant_signal=quant_signal,
            llm_decision=llm_decision,
            regime_info={"regime": "ranging"},
        )

    assert res.decision == "wait"
    assert res.risk_multiplier == 0.0
    assert "contradicts TimesFM skew" in res.arbitration_reason
