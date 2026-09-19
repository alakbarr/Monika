# ==============================================================================
# File: evals/runner.py
# Description: Automated Offline Evaluation Runner & Mechanical Scoring Engine
# ==============================================================================

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

from evals.oracles.smc_geometry_oracle import evaluate_smc_geometry
from evals.oracles.risk_compliance_oracle import evaluate_risk_compliance
from evals.oracles.trade_discipline_oracle import evaluate_trade_discipline

logger = logging.getLogger("TradingAgent.Evals.Runner")

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class OfflineEvalRunner:
    """
    Zero-LLM cost mechanical evaluation engine.
    Validates trading decisions and harness proposals against frozen market ground truth.
    """

    def __init__(self, fixtures_path: Optional[Path] = None):
        self.fixtures_path = fixtures_path or FIXTURES_DIR

    def load_all_fixtures(self) -> List[Dict[str, Any]]:
        """Loads all golden scenario fixtures from disk."""
        fixtures = []
        if not self.fixtures_path.exists():
            return fixtures
        for json_file in sorted(self.fixtures_path.glob("*.json")):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                fixtures.append(data)
            except Exception as e:
                logger.error(f"Failed to load fixture {json_file.name}: {e}")
        return fixtures

    def evaluate_decision(self, fixture: Dict[str, Any], decision_data: Dict[str, Any]) -> Dict[str, Any]:
        """Runs all deterministic oracles against a single decision for a given fixture."""
        geo_result = evaluate_smc_geometry(fixture, decision_data)
        risk_result = evaluate_risk_compliance(fixture, decision_data)
        disc_result = evaluate_trade_discipline(fixture, decision_data)

        all_violations = geo_result["violations"] + risk_result["violations"] + disc_result["violations"]
        all_passed_checks = geo_result["checks_passed"] + risk_result["checks_passed"] + disc_result["checks_passed"]

        is_passed = (len(all_violations) == 0)

        return {
            "scenario_id": fixture.get("scenario_id", "unknown"),
            "scenario_name": fixture.get("name", "unnamed"),
            "symbol": fixture.get("symbol"),
            "passed": is_passed,
            "violations": all_violations,
            "passed_checks": all_passed_checks,
            "details": {
                "smc_geometry": geo_result,
                "risk_compliance": risk_result,
                "trade_discipline": disc_result,
            }
        }

    def run_suite(self, candidate_decisions: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Runs full test suite against provided dictionary of {scenario_id: decision_data}.
        Returns aggregate evaluation scorecard.
        """
        fixtures = self.load_all_fixtures()
        results = []
        passed_count = 0

        for fix in fixtures:
            scen_id = fix.get("scenario_id")
            dec_data = candidate_decisions.get(scen_id)
            if not dec_data:
                # If no explicit candidate provided, test against fixture baseline
                results.append({
                    "scenario_id": scen_id,
                    "scenario_name": fix.get("name"),
                    "passed": False,
                    "violations": [f"No candidate decision provided for scenario {scen_id}"],
                    "passed_checks": [],
                })
                continue

            eval_res = self.evaluate_decision(fix, dec_data)
            if eval_res["passed"]:
                passed_count += 1
            results.append(eval_res)

        total = len(fixtures)
        pass_rate = round((passed_count / total) * 100, 1) if total > 0 else 0.0

        return {
            "total_scenarios": total,
            "passed_count": passed_count,
            "failed_count": total - passed_count,
            "pass_rate_pct": pass_rate,
            "all_passed": (passed_count == total and total > 0),
            "results": results,
        }


def get_default_golden_candidates() -> Dict[str, Dict[str, Any]]:
    """Golden candidate decisions that satisfy all scenario constraints 100%."""
    return {
        "smc_bull_displacement_01": {
            "symbol": "EURUSD",
            "decision": "BUY",
            "entry_price": 1.08500,
            "stop_loss": 1.08200,      # sl_dist = 0.00300 (>= 0.8 * atr 0.00350 = 0.00280)
            "take_profit": 1.08950,     # tp_dist = 0.00450 (R:R = 1.5 >= 1.3)
            "reason": "Bullish BOS displacement into unmitigated FVG discount",
        },
        "smc_bear_sweep_01": {
            "symbol": "XAUUSD",
            "decision": "SELL",
            "entry_price": 2345.00,
            "stop_loss": 2353.00,      # sl_dist = 8.00 (>= 0.8 * atr 5.80 = 4.64)
            "take_profit": 2329.00,     # tp_dist = 16.00 (R:R = 2.0 >= 1.3)
            "reason": "Asian high sweep rejection and CHoCH structural breakdown",
        },
        "smc_choppy_trap_01": {
            "symbol": "GBPUSD",
            "decision": "WAIT",
            "reason": "Midday choppy compression with no clear displacement. Awaiting range breakout.",
        },
        "risk_trap_spread_spike_01": {
            "symbol": "USDJPY",
            "decision": "WAIT",
            "reason": "Execution vetoed: spread_exceeded (8.5 pips > 3.0 pips limit).",
        },
        "risk_trap_daily_dd_01": {
            "symbol": "EURUSD",
            "decision": "WAIT",
            "reason": "Execution vetoed: daily_drawdown_limit_breached (-3.20% <= -2.50%).",
        },
    }


if __name__ == "__main__":
    runner = OfflineEvalRunner()
    fixtures = runner.load_all_fixtures()
    print(f"Loaded {len(fixtures)} fixtures from {FIXTURES_DIR}")
    golden = get_default_golden_candidates()
    report = runner.run_suite(golden)
    print(f"Eval Suite Scorecard: {report['passed_count']}/{report['total_scenarios']} passed ({report['pass_rate_pct']}%)")
    for r in report["results"]:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"[{status}] {r['scenario_id']}: {r['scenario_name']}")
        if not r["passed"]:
            for v in r["violations"]:
                print(f"  - VIOLATION: {v}")
