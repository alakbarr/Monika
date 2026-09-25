"""
Unit & Integration Tests for Remediation Phase 2 (Architectural & Advanced Enhancements).
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from utils import clock
from utils.clock import frozen_time
from backtest.outcome_evaluator import OutcomeEvaluator
from database.models import BacktestTrade
from analysis.arbitration.signal_arbitrator import SignalArbitrator, ArbitrationResult
from analysis.strategies.base_strategy import EdgeSignal
from database.db import transactional_advisory_lock


def test_clock_frozen_time_context_manager():
    """Verify that frozen_time deterministically fixes the clock and resets on exit."""
    sim_dt = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    
    assert clock.now() != sim_dt
    with frozen_time(sim_dt):
        assert clock.now() == sim_dt
        assert clock.now().year == 2025
        assert clock.now().month == 6
    
    # After exiting context, clock resets to real time
    assert clock.now() != sim_dt


@pytest.mark.asyncio
async def test_outcome_evaluator_cost_friction():
    """Verify OutcomeEvaluator properly calculates spread, slippage, and swap costs."""
    evaluator = OutcomeEvaluator(max_holding_hours=48)
    
    entry_time = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)
    exit_time = datetime(2026, 8, 21, 14, 0, tzinfo=timezone.utc)  # 28 hours (1 night swap)
    
    trade = BacktestTrade(
        symbol="EURUSD",
        direction="buy",
        entry_price=1.1000,
        stop_loss=1.0900,
        take_profit=1.1100,
        entry_time=entry_time
    )

    # 1. Gross calculation (apply_costs=False)
    gross_outcome = evaluator._calculate_outcome(trade, exit_time, 1.1050, "tp_hit", apply_costs=False)
    assert gross_outcome["pnl_pips"] == 50.0
    assert gross_outcome["friction_pips"] == 0.0

    # 2. Net calculation with friction (apply_costs=True)
    net_outcome = evaluator._calculate_outcome(trade, exit_time, 1.1050, "tp_hit", apply_costs=True)
    assert net_outcome["friction_pips"] > 0.0
    assert net_outcome["pnl_pips"] < gross_outcome["pnl_pips"]
    assert net_outcome["pnl_pct"] < gross_outcome["pnl_pct"]


@pytest.mark.asyncio
async def test_signal_arbitrator_concordant_boost():
    """Verify SignalArbitrator boosts conviction when Quant and LLM agree."""
    arbitrator = SignalArbitrator(settings={})
    mock_session = AsyncMock()

    quant_sig = EdgeSignal(
        strategy_id="btc_donchian",
        symbol="BTCUSD",
        direction="buy",
        valid=True,
        confidence=0.80,
        entry_price=60000.0,
        stop_loss=58000.0,
        take_profit=65000.0,
        rationale="Donchian 20D channel breakout"
    )

    llm_dec = {
        "decision": "buy",
        "confidence": 0.75,
        "risk_multiplier": 1.0,
        "stop_loss": 58500.0,
        "take_profit": 65000.0,
        "rationale": "Bullish macro cycle",
        "decision_source": "llm_debate"
    }

    with patch("utils.calibration.confidence_calibrator.get_calibrated_confidence", AsyncMock(return_value=0.75)):
        result = await arbitrator.arbitrate(
            session=mock_session,
            symbol="BTCUSD",
            quant_signal=quant_sig,
            llm_decision=llm_dec,
            vix_level=16.0
        )

        assert result.decision == "buy"
        assert result.selected_source == "concordant"
        assert result.confidence >= 0.80
        assert result.risk_multiplier > 1.0  # Boosted risk multiplier
        assert "Concordant agreement" in result.arbitration_reason


@pytest.mark.asyncio
async def test_signal_arbitrator_conflict_regime_and_vix():
    """Verify SignalArbitrator resolves conflicts based on VIX uncertainty and trend regime."""
    arbitrator = SignalArbitrator(settings={})
    mock_session = AsyncMock()

    quant_sig = EdgeSignal(
        strategy_id="xau_trend",
        symbol="XAUUSD",
        direction="buy",
        valid=True,
        confidence=0.85,
        entry_price=2000.0,
        stop_loss=1980.0,
        take_profit=2050.0,
        rationale="Gold breakout above resistance"
    )

    llm_dec = {
        "decision": "sell",
        "confidence": 0.70,
        "risk_multiplier": 1.0,
        "stop_loss": 2020.0,
        "take_profit": 1950.0,
        "rationale": "Hawkish Fed commentary",
        "decision_source": "llm_debate"
    }

    # Case 1: Extreme VIX uncertainty (VIX=36.0) -> Defensive Override (Avoid)
    res_high_vix = await arbitrator.arbitrate(
        session=mock_session,
        symbol="XAUUSD",
        quant_signal=quant_sig,
        llm_decision=llm_dec,
        vix_level=36.0,
        regime_info={"regime": "ranging"}
    )
    assert res_high_vix.decision == "avoid"
    assert res_high_vix.selected_source == "defensive_override"

    # Case 2: Verified Strong Trend regime -> Quant Trend strategy prioritized with caution scaling
    res_trend = await arbitrator.arbitrate(
        session=mock_session,
        symbol="XAUUSD",
        quant_signal=quant_sig,
        llm_decision=llm_dec,
        vix_level=18.0,
        regime_info={"regime": "strong_trend"}
    )
    assert res_trend.decision == "buy"
    assert res_trend.selected_source == "quant"
    assert res_trend.risk_multiplier <= 0.75  # Scaled down caution sizing

    # Case 3: Ranging market conflict -> Mutual Suppression (equal conviction)
    res_ranging = await arbitrator.arbitrate(
        session=mock_session,
        symbol="XAUUSD",
        quant_signal=quant_sig,
        llm_decision={**llm_dec, "confidence": 0.85},
        vix_level=18.0,
        regime_info={"regime": "ranging"}
    )
    assert res_ranging.decision == "avoid"
    assert res_ranging.selected_source == "conflict_suppression"


@pytest.mark.asyncio
async def test_transactional_advisory_lock_fallback():
    """Verify transactional_advisory_lock functions properly as an async context manager."""
    mock_session = AsyncMock()
    mock_session.get_bind.return_value = MagicMock(dialect=MagicMock(name="sqlite"))

    async with transactional_advisory_lock(mock_session, lock_key=12345) as is_locked:
        assert is_locked is True


@pytest.mark.asyncio
async def test_benchmark_judge_ensemble():
    """Verify judge_output_ensemble aggregates scores across multiple judge models."""
    from benchmark.judge import judge_output_ensemble
    
    mock_result_1 = ({"grounding_score": 8, "accuracy_score": 9, "actionability_score": 8, "consistency_score": 9, "hallucination_risk": "none", "notes": "Good"}, 8.5, 500, 100)
    mock_result_2 = ({"grounding_score": 8, "accuracy_score": 8, "actionability_score": 8, "consistency_score": 8, "hallucination_risk": "low", "notes": "Solid"}, 7.5, 450, 90)

    with patch("benchmark.judge.judge_output", side_effect=[mock_result_1, mock_result_2]):
        verdict, score, total_in, total_out = await judge_output_ensemble(
            judge_models=["model_a", "model_b"],
            settings={},
            category="trade_decision",
            context_summary="Fact sheet test context",
            candidate_output="Buy EURUSD at 1.1000"
        )
        assert score == 8.0  # Average of 8.5 and 7.5
        assert total_in == 950
        assert total_out == 190
        assert "ensemble_scores" in verdict
        assert verdict["ensemble_consensus_score"] == 8.0
