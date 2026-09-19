import pytest
from evals.runner import OfflineEvalRunner, get_default_golden_candidates
from evals.oracles.smc_geometry_oracle import evaluate_smc_geometry
from evals.oracles.risk_compliance_oracle import evaluate_risk_compliance
from evals.oracles.trade_discipline_oracle import evaluate_trade_discipline


def test_offline_eval_runner_full_suite():
    runner = OfflineEvalRunner()
    fixtures = runner.load_all_fixtures()
    assert len(fixtures) >= 5

    candidates = get_default_golden_candidates()
    report = runner.run_suite(candidates)

    assert report["total_scenarios"] >= 5
    assert report["passed_count"] == report["total_scenarios"]
    assert report["pass_rate_pct"] == 100.0
    assert report["all_passed"] is True


def test_smc_geometry_oracle_detects_bad_rr():
    mock_fixture = {
        "scenario_id": "test_bad_rr",
        "symbol": "EURUSD",
        "current_price": 1.0850,
        "technical_context": {"atr_14": 0.0020},
        "expected_outcome": {"valid_decisions": ["BUY"], "min_rr": 1.3}
    }
    
    # R:R is 0.0010 / 0.0020 = 0.5 (< 1.3)
    bad_decision = {
        "decision": "BUY",
        "entry_price": 1.0850,
        "stop_loss": 1.0830,
        "take_profit": 1.0860,
    }

    res = evaluate_smc_geometry(mock_fixture, bad_decision)
    assert res["passed"] is False
    assert any("violates minimum requirement" in v for v in res["violations"])


def test_risk_compliance_oracle_catches_breach():
    mock_fixture = {
        "scenario_id": "test_dd_breach",
        "expected_outcome": {
            "requires_risk_veto": True,
            "veto_reason": "daily_drawdown_limit_breached"
        }
    }

    # Agent improperly tries to BUY anyway
    violating_decision = {
        "decision": "BUY",
        "entry_price": 1.0850,
        "reason": "Great momentum, ignoring drawdown",
    }

    res = evaluate_risk_compliance(mock_fixture, violating_decision)
    assert res["passed"] is False
    assert any("requires binary VETO" in v for v in res["violations"])


def test_trade_discipline_oracle_flags_lazy_wait():
    mock_fixture = {
        "scenario_id": "test_trend",
        "symbol": "EURUSD",
        "expected_outcome": {
            "valid_decisions": ["BUY"],
        }
    }

    lazy_decision = {
        "symbol": "EURUSD",
        "decision": "WAIT",
        "reason": "I do not feel like trading today",
    }

    res = evaluate_trade_discipline(mock_fixture, lazy_decision)
    assert res["passed"] is False
    assert any("Lazy Unjustified WAIT" in v for v in res["violations"])
