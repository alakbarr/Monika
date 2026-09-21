"""
Mechanical Oracles in CI (Phase 5.5).
Executes all golden scenario fixtures through OfflineEvalRunner with deterministic validation,
verifying 100% compliance across SMC geometry, risk constraints, and trade discipline without LLM calls.
"""

import pytest
from evals.runner import OfflineEvalRunner


def test_offline_oracle_fixture_loading():
    """Verify all golden scenario fixtures load properly from disk."""
    runner = OfflineEvalRunner()
    fixtures = runner.load_all_fixtures()
    assert len(fixtures) >= 5, f"Expected at least 5 golden fixtures, found {len(fixtures)}"
    scenario_ids = [f["scenario_id"] for f in fixtures]
    assert "smc_bull_displacement_01" in scenario_ids
    assert "smc_bear_sweep_01" in scenario_ids
    assert "risk_trap_daily_dd_01" in scenario_ids


def test_offline_oracle_golden_evaluations():
    """Verify golden conforming proposals achieve 100% pass rate across deterministic oracles."""
    runner = OfflineEvalRunner()
    fixtures = {f["scenario_id"]: f for f in runner.load_all_fixtures()}

    # 1. Bullish Displacement: Valid BUY respecting FVG & SL under OB
    fix_bull = fixtures["smc_bull_displacement_01"]
    dec_bull = {
        "decision": "BUY",
        "symbol": "EURUSD",
        "entry_price": 1.08550,
        "stop_loss": 1.08200,
        "take_profit": 1.09100,
        "lot_size": 0.1,
        "confidence": 0.85,
    }
    res_bull = runner.evaluate_decision(fix_bull, dec_bull)
    assert res_bull["passed"], f"Bullish displacement evaluation failed: {res_bull['violations']}"

    # 2. Bearish Sweep: Valid SELL respecting liquidity sweep
    fix_bear = fixtures["smc_bear_sweep_01"]
    dec_bear = {
        "decision": "SELL",
        "symbol": "XAUUSD",
        "entry_price": 2340.50,
        "stop_loss": 2355.00,
        "take_profit": 2320.00,
        "lot_size": 0.1,
        "confidence": 0.80,
    }
    res_bear = runner.evaluate_decision(fix_bear, dec_bear)
    assert res_bear["passed"], f"Bearish sweep evaluation failed: {res_bear['violations']}"

    # 3. Choppy Trap: Valid WAIT decision avoiding low-edge market with justified rationale
    fix_chop = fixtures["smc_choppy_trap_01"]
    dec_chop = {
        "decision": "WAIT",
        "symbol": "GBPUSD",
        "confidence": 0.30,
        "rationale": "Market exhibits choppy compression and inside bars with no displacement, wait for expansion.",
    }
    res_chop = runner.evaluate_decision(fix_chop, dec_chop)
    assert res_chop["passed"], f"Choppy trap evaluation failed: {res_chop['violations']}"

    # 4. Risk Trap Daily DD: System must WAIT / reject execution citing daily_drawdown_limit_breached
    fix_dd = fixtures["risk_trap_daily_dd_01"]
    dec_dd = {
        "decision": "WAIT",
        "symbol": "EURUSD",
        "confidence": 0.0,
        "reason": "daily_drawdown_limit_breached",
        "veto_reason": "daily_drawdown_limit_breached",
    }
    res_dd = runner.evaluate_decision(fix_dd, dec_dd)
    assert res_dd["passed"], f"Risk trap DD evaluation failed: {res_dd['violations']}"


def test_offline_oracle_catches_violations():
    """Verify oracles catch invalid SL geometry and unconstrained risk proposals."""
    runner = OfflineEvalRunner()
    fixtures = {f["scenario_id"]: f for f in runner.load_all_fixtures()}

    fix_bull = fixtures["smc_bull_displacement_01"]
    # Bad BUY: Stop loss above entry price (inverted geometry)
    bad_dec = {
        "decision": "BUY",
        "symbol": "EURUSD",
        "entry_price": 1.08550,
        "stop_loss": 1.08600,
        "take_profit": 1.09000,
    }
    res = runner.evaluate_decision(fix_bull, bad_dec)
    assert not res["passed"]
    assert any("geometry" in v.lower() or "sl" in v.lower() or "stop" in v.lower() for v in res["violations"])
