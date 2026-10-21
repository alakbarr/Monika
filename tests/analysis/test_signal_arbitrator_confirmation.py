"""Phase 1: a quantitative signal may only override an LLM WAIT on TimesFM confirmation.

Removed in Phase 1:
  * the hardcoded "promoted strategy" override (neutral / non-opposing skew),
  * the "decisive conviction" override (no TimesFM confirmation required).
"""

import pytest

import monika.core.primitives.clock as clock
from monika.application.analysis.arbitration.signal_arbitrator import SignalArbitrator
from monika.application.analysis.strategies.base_strategy import EdgeSignal
from monika.application.analysis.strategies.decay_monitor import (
    StrategyDecayMonitor,
    get_strategy_decay_monitor,
)
from monika.infrastructure.ml.timesfm_engine import TimesFMEngine

STRATEGY_ID = "phase1_confirm_alpha"
LEGACY_PROMOTED_ID = "tokyo_open_sweep"


@pytest.fixture(autouse=True)
def _reset_decay_monitor():
    yield
    StrategyDecayMonitor.reset()


def _make_live_ready(strategy_id: str) -> None:
    """Promote a strategy the only legitimate way: real paper-trade results."""
    monitor = get_strategy_decay_monitor()
    monitor.register_incubating_strategy(strategy_id)
    for _ in range(StrategyDecayMonitor.MIN_INCUBATION_TRADES):
        monitor.record_trade_outcome(strategy_id, win=True, is_paper=True, profit=2.0)
    assert monitor.is_live_ready(strategy_id) is True


async def _save_forecast(session, symbol: str, skew: float) -> None:
    engine = TimesFMEngine()
    forecast = {
        "symbol": symbol,
        "timeframe": "H1",
        "generated_at": clock.now(),
        "horizon_steps": 24,
        "quantiles": {"q10": [1.08] * 24, "q50": [1.09] * 24, "q90": [1.095] * 24},
        "expected_range": 0.015,
        "quantile_skew": skew,
        "volatility_expansion_ratio": 1.1,
        "reachability_envelope": [],
    }
    await engine.save_forecast(session, forecast)
    await session.commit()


def _quant_signal(strategy_id: str = STRATEGY_ID) -> EdgeSignal:
    return EdgeSignal(
        strategy_id=strategy_id,
        symbol="EURUSD",
        direction="buy",
        valid=True,
        confidence=0.80,
        entry_price=1.0920,
        stop_loss=1.0880,
        take_profit=1.1000,
    )


@pytest.mark.asyncio
async def test_neutral_timesfm_does_not_override_llm_wait(db_session):
    """A neutral skew used to let a 'promoted' strategy override the LLM WAIT."""
    _make_live_ready(STRATEGY_ID)
    await _save_forecast(db_session, "EURUSD", skew=0.0)

    arbitrator = SignalArbitrator(settings={"trading": {"signal_arbitration": {}}})
    result = await arbitrator.arbitrate(
        db_session,
        symbol="EURUSD",
        quant_signal=_quant_signal(),
        llm_decision={"decision": "wait", "confidence": 0.5},
        vix_level=16.0,
    )

    assert result.decision == "wait"
    assert result.selected_source == "llm"
    assert "directional confirmation" in result.arbitration_reason


@pytest.mark.asyncio
async def test_confirming_timesfm_allows_quant_override(db_session):
    _make_live_ready(STRATEGY_ID)
    await _save_forecast(db_session, "EURUSD", skew=0.40)

    arbitrator = SignalArbitrator(settings={"trading": {"signal_arbitration": {}}})
    result = await arbitrator.arbitrate(
        db_session,
        symbol="EURUSD",
        quant_signal=_quant_signal(),
        llm_decision={"decision": "wait", "confidence": 0.5},
        vix_level=16.0,
    )

    assert result.decision == "buy"
    assert result.selected_source == "quant"
    assert "confirmation" in result.arbitration_reason


@pytest.mark.asyncio
async def test_opposing_timesfm_keeps_llm_wait(db_session):
    _make_live_ready(STRATEGY_ID)
    await _save_forecast(db_session, "EURUSD", skew=-0.40)

    arbitrator = SignalArbitrator(settings={"trading": {"signal_arbitration": {}}})
    result = await arbitrator.arbitrate(
        db_session,
        symbol="EURUSD",
        quant_signal=_quant_signal(),
        llm_decision={"decision": "wait", "confidence": 0.5},
        vix_level=16.0,
    )

    assert result.decision in ("wait", "avoid")
    assert result.risk_multiplier == 0.0


@pytest.mark.asyncio
async def test_legacy_promoted_strategy_has_no_special_override(db_session):
    """The old hardcoded promotion list must not grant any override power."""
    _make_live_ready(LEGACY_PROMOTED_ID)
    await _save_forecast(db_session, "EURUSD", skew=0.0)

    arbitrator = SignalArbitrator(settings={"trading": {"signal_arbitration": {}}})
    result = await arbitrator.arbitrate(
        db_session,
        symbol="EURUSD",
        quant_signal=_quant_signal(LEGACY_PROMOTED_ID),
        llm_decision={"decision": "wait", "confidence": 0.5},
        vix_level=16.0,
    )

    assert result.decision == "wait"
    assert result.selected_source == "llm"


@pytest.mark.asyncio
async def test_direct_conflict_without_timesfm_confirmation_is_avoided(db_session):
    """A quant signal may not win a direct LLM conflict without market confirmation."""
    _make_live_ready(STRATEGY_ID)
    await _save_forecast(db_session, "EURUSD", skew=0.0)

    arbitrator = SignalArbitrator(settings={"trading": {"signal_arbitration": {}}})
    result = await arbitrator.arbitrate(
        db_session,
        symbol="EURUSD",
        quant_signal=_quant_signal(),
        llm_decision={"decision": "sell", "confidence": 0.50},
        vix_level=16.0,
    )

    assert result.decision == "avoid"
    assert result.selected_source == "conflict_suppression"
    assert result.risk_multiplier == 0.0


@pytest.mark.asyncio
async def test_direct_conflict_with_timesfm_confirmation_resolves_to_quant(db_session):
    """With directional confirmation the conflict is resolved in favour of the quant side."""
    _make_live_ready(STRATEGY_ID)
    await _save_forecast(db_session, "EURUSD", skew=0.30)

    arbitrator = SignalArbitrator(settings={"trading": {"signal_arbitration": {}}})
    result = await arbitrator.arbitrate(
        db_session,
        symbol="EURUSD",
        quant_signal=_quant_signal(),
        llm_decision={"decision": "sell", "confidence": 0.50},
        vix_level=16.0,
    )

    assert result.decision == "buy"
    assert result.selected_source in ("timesfm_tie_break_quant", "quant_conviction_precedence")
    assert result.risk_multiplier > 0.0


@pytest.mark.asyncio
async def test_llm_conviction_precedence_still_wins_without_confirmation(db_session):
    """The LLM side of a conflict keeps precedence on conviction, no confirmation needed."""
    _make_live_ready(STRATEGY_ID)
    await _save_forecast(db_session, "EURUSD", skew=0.0)

    arbitrator = SignalArbitrator(settings={"trading": {"signal_arbitration": {}}})
    result = await arbitrator.arbitrate(
        db_session,
        symbol="EURUSD",
        quant_signal=_quant_signal(),
        llm_decision={"decision": "sell", "confidence": 0.90},
        vix_level=16.0,
    )

    assert result.decision == "sell"
    assert result.selected_source == "llm_conviction_precedence"
    assert result.risk_multiplier == 0.75


@pytest.mark.asyncio
async def test_decisive_conviction_without_confirmation_does_not_override(db_session):
    """Confidence delta alone is no longer sufficient to override the LLM WAIT."""
    _make_live_ready(STRATEGY_ID)
    await _save_forecast(db_session, "EURUSD", skew=0.0)

    arbitrator = SignalArbitrator(settings={"trading": {"signal_arbitration": {}}})
    result = await arbitrator.arbitrate(
        db_session,
        symbol="EURUSD",
        quant_signal=_quant_signal(),
        llm_decision={"decision": "wait", "confidence": 0.30},
        vix_level=16.0,
    )

    assert result.decision == "wait"
    assert result.selected_source == "llm"
