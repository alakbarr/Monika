# ==============================================================================
# File: tests/evals/test_simulation_and_oracles.py
# Description: Unit Tests for SimulationClock, MarketStepSimulator, Macro Oracle & Drift Tracker
# ==============================================================================

import pytest
from datetime import datetime, timezone, timedelta

from evals.simulation_clock import SimulationClock, MarketStep, MarketStepSimulator
from evals.oracles.macro_regime_oracle import evaluate_macro_regime
from benchmark.token_drift_tracker import TokenDriftTracker, PromptSnapshot


def test_simulation_clock_advance_and_freeze():
    start = datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
    clock = SimulationClock(start)

    assert clock.now() == start
    assert clock.is_frozen() is True

    # Advance 60 seconds
    clock.advance(60.0)
    assert clock.now() == start + timedelta(seconds=60)

    # Advance to target
    target = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    clock.advance_to(target)
    assert clock.now() == target

    # Cannot advance backwards
    with pytest.raises(ValueError):
        clock.advance_to(start)


@pytest.mark.asyncio
async def test_simulation_clock_virtual_sleep():
    start = datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
    clock = SimulationClock(start)

    # Virtual sleep should advance clock instantaneously without blocking
    await clock.sleep(300.0)
    assert clock.now() == start + timedelta(seconds=300)


def test_market_step_simulator_fills():
    t1 = datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 6, 1, 10, 5, 0, tzinfo=timezone.utc)

    step1 = MarketStep(
        timestamp=t1,
        symbol="EURUSD",
        bid=1.08500,
        ask=1.08515,
        bar_open=1.08480,
        bar_high=1.08530,
        bar_low=1.08470,
        bar_close=1.08510,
    )
    step2 = MarketStep(
        timestamp=t2,
        symbol="EURUSD",
        bid=1.08540,
        ask=1.08555,
        bar_open=1.08510,
        bar_high=1.08560,
        bar_low=1.08500,
        bar_close=1.08550,
    )

    clock = SimulationClock(t1)
    sim = MarketStepSimulator(clock)
    sim.load_steps([step1, step2])

    # Step 1
    s = sim.step()
    assert s is not None
    assert s.bid == 1.08500
    assert s.spread_pips == 1.5  # (1.08515 - 1.08500) / 0.0001
    assert clock.now() == t1

    # Simulate BUY fill with 0.5 pip slippage
    fill = sim.simulate_order_fill("EURUSD", "BUY", lots=0.5, slippage_pips=0.5)
    # ask 1.08515 + 0.5 * 0.0001 = 1.08520
    assert fill["fill_price"] == 1.08520
    assert fill["lots"] == 0.5

    # Step 2
    s2 = sim.step()
    assert s2 is not None
    assert clock.now() == t2

    # Simulate SELL fill
    fill2 = sim.simulate_order_fill("EURUSD", "SELL", lots=1.0, slippage_pips=0.0)
    assert fill2["fill_price"] == 1.08540


def test_macro_regime_oracle_evaluation():
    fixture = {
        "macro_context": {
            "vix": 18.5,
            "dxy": 104.2,
        },
        "expected_outcome": {
            "valid_regimes": ["RISK_ON", "NEUTRAL"],
            "expected_cb_stance": "hawkish",
        }
    }

    # Case 1: Valid regime & policy stance
    decision_valid = {
        "risk_regime": "RISK_ON",
        "central_bank_stance": "hawkish pause",
        "risk_pct": 1.0,
    }
    res = evaluate_macro_regime(fixture, decision_valid)
    assert res["passed"] is True
    assert len(res["violations"]) == 0

    # Case 2: Contradictory regime
    decision_invalid_regime = {
        "risk_regime": "DEEP_RECESSION",
        "central_bank_stance": "hawkish",
        "risk_pct": 0.5,
    }
    res_inv = evaluate_macro_regime(fixture, decision_invalid_regime)
    assert res_inv["passed"] is False
    assert any("contradicts" in v for v in res_inv["violations"])

    # Case 3: High VIX risk violation
    fixture_high_vix = dict(fixture)
    fixture_high_vix["macro_context"] = {"vix": 35.0}
    decision_excess_risk = {
        "risk_regime": "RISK_ON",
        "central_bank_stance": "hawkish",
        "risk_pct": 2.5,  # Exceeds 1.0% limit during VIX >= 30
    }
    res_vix = evaluate_macro_regime(fixture_high_vix, decision_excess_risk)
    assert res_vix["passed"] is False
    assert any("High volatility" in v for v in res_vix["violations"])


def test_token_drift_tracker_bloat_and_invalidation():
    tracker = TokenDriftTracker(max_drift_pct=15.0)

    base_snapshot = PromptSnapshot.from_prompts(
        stage_name="stage1_macro",
        system_prompt="Invariant Base System Prompt",
        user_prompt="Analyze macroeconomic indicators",
    )
    tracker.set_baseline(base_snapshot)

    # 1. Normal run within 15% growth
    run_normal = PromptSnapshot.from_prompts(
        stage_name="stage1_macro",
        system_prompt="Invariant Base System Prompt",
        user_prompt="Analyze macroeconomic indicators for today",
    )
    rep1 = tracker.record_run(run_normal)
    assert rep1.is_drift_detected is False
    assert rep1.is_cache_invalidated is False

    # 2. Bloated prompt (> 15% growth)
    run_bloated = PromptSnapshot.from_prompts(
        stage_name="stage1_macro",
        system_prompt="Invariant Base System Prompt",
        user_prompt="Analyze macroeconomic indicators " + "extra redundant instructions " * 20,
    )
    rep2 = tracker.record_run(run_bloated)
    assert rep2.is_drift_detected is True
    assert any("bloat detected" in v for v in rep2.violations)

    # 3. Cache key break (system prompt modified at Surface Node 0)
    run_broken_cache = PromptSnapshot.from_prompts(
        stage_name="stage1_macro",
        system_prompt="Modified System Prompt Different Hash",
        user_prompt="Analyze macroeconomic indicators",
    )
    rep3 = tracker.record_run(run_broken_cache)
    assert rep3.is_cache_invalidated is True
    assert any("invalidation" in v for v in rep3.violations)

    summary = tracker.get_summary()
    assert "stage1_macro" in summary
    assert summary["stage1_macro"]["total_runs"] == 4
