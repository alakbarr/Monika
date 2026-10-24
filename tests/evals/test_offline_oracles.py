"""
Mechanical Oracles in CI (Phase 5.5).
Executes all golden scenario fixtures through OfflineEvalRunner with deterministic validation,
verifying 100% compliance across SMC geometry, risk constraints, and trade discipline without LLM calls.
"""

import pytest
from monika.application.evals.runner import OfflineEvalRunner


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


def test_smc_geometry_rejects_nan_and_nonpositive():
    """Verify smc geometry oracle fails closed on NaN, Inf, and non-positive coordinates."""
    from monika.application.evals.oracles.smc_geometry_oracle import evaluate_smc_geometry

    fixture = {
        "expected_outcome": {"valid_decisions": ["BUY"], "min_rr": 1.3},
        "technical_context": {"atr_14": 0.0010},
    }

    # NaN in SL
    res_nan = evaluate_smc_geometry(
        fixture, {"decision": "BUY", "entry_price": 1.10, "stop_loss": float("nan"), "take_profit": 1.15}
    )
    assert not res_nan["passed"]
    assert any("finite and strictly positive" in v for v in res_nan["violations"])

    # Negative entry
    res_neg = evaluate_smc_geometry(
        fixture, {"decision": "BUY", "entry_price": -1.10, "stop_loss": 1.05, "take_profit": 1.15}
    )
    assert not res_neg["passed"]
    assert any("finite and strictly positive" in v for v in res_neg["violations"])


def test_macro_regime_rejects_missing_cb_stance():
    """Verify macro regime oracle fails closed when expected stance is missing in decision."""
    from monika.application.evals.oracles.macro_regime_oracle import evaluate_macro_regime

    fixture = {
        "macro_context": {"vix": 18.0},
        "expected_outcome": {"expected_cb_stance": "hawkish"},
    }

    # Missing stance
    res_missing = evaluate_macro_regime(fixture, {"decision": "BUY", "risk_regime": "RISK_ON"})
    assert not res_missing["passed"]
    assert any("Missing required central bank stance" in v for v in res_missing["violations"])


def test_trade_discipline_rejects_missing_symbol_and_negative_price():
    """Verify trade discipline oracle fails closed when symbol is missing or price is negative."""
    from monika.application.evals.oracles.trade_discipline_oracle import evaluate_trade_discipline

    fixture = {"symbol": "EURUSD", "current_price": 1.0850}

    # Missing symbol
    res_no_sym = evaluate_trade_discipline(fixture, {"decision": "BUY", "entry_price": 1.0850})
    assert not res_no_sym["passed"]
    assert any("Missing symbol" in v for v in res_no_sym["violations"])

    # Negative price
    res_neg = evaluate_trade_discipline(fixture, {"symbol": "EURUSD", "decision": "BUY", "entry_price": -1.0850})
    assert not res_neg["passed"]
    assert any("Non-positive price level" in v for v in res_neg["violations"])


def test_risk_compliance_rejects_missing_stop_loss():
    """Verify risk compliance oracle rejects directional decisions without strictly positive SL."""
    from monika.application.evals.oracles.risk_compliance_oracle import evaluate_risk_compliance

    fixture = {"expected_outcome": {"requires_risk_veto": False}}

    # BUY with missing SL
    res_no_sl = evaluate_risk_compliance(fixture, {"decision": "BUY", "symbol": "EURUSD", "entry_price": 1.0850})
    assert not res_no_sl["passed"]
    assert any("missing strictly positive Stop Loss" in v for v in res_no_sl["violations"])

    # BUY with 0.0 SL
    res_zero_sl = evaluate_risk_compliance(
        fixture, {"decision": "BUY", "symbol": "EURUSD", "entry_price": 1.0850, "stop_loss": 0.0}
    )
    assert not res_zero_sl["passed"]
    assert any("missing strictly positive Stop Loss" in v for v in res_zero_sl["violations"])


def test_tool_safety_oracle_fails_closed_when_fixture_missing():
    """Verify tool safety oracle fails closed when fixture does not exist."""
    from monika.application.evals.oracles.tool_safety_oracle import ToolSafetyOracle

    oracle = ToolSafetyOracle(fixture_path="non_existent_fixture.json")
    results = oracle.evaluate_traps_suite()
    assert len(results) == 1
    assert not results[0].passed
    assert "fixture missing or empty" in results[0].reason
