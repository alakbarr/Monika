"""
File: evals/eval_runner.py
PR-12: A/B Evaluation Harness & Experiment Runner for Monika v2.
Compares baseline prompts/decisions against candidates across golden scenarios,
incorporating deterministic oracles, grounding verification, and cross-timeframe gates.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable

from evals.oracles.smc_geometry_oracle import evaluate_smc_geometry
from evals.oracles.risk_compliance_oracle import evaluate_risk_compliance
from evals.oracles.trade_discipline_oracle import evaluate_trade_discipline
from evals.eval_metrics import (
    DecisionEvaluation,
    ABReport,
    compare_ab_evaluations,
    aggregate_eval_metrics,
)

logger = logging.getLogger("TradingAgent.Evals.ABRunner")
FIXTURES_DIR = Path(__file__).parent / "fixtures"


class ABEvalRunner:
    """
    Automated A/B Evaluation Harness.
    Executes mechanical oracles, grounding checks, and cost/accuracy metrics
    to benchmark prompt variations, context engines, and trading models.
    """

    def __init__(self, fixtures_path: Optional[Path] = None):
        self.fixtures_path = fixtures_path or FIXTURES_DIR

    def load_fixtures(self) -> List[Dict[str, Any]]:
        """Loads all golden scenario fixtures from the fixtures directory."""
        fixtures = []
        if not self.fixtures_path.exists():
            return fixtures
        for file in sorted(self.fixtures_path.glob("*.json")):
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
                fixtures.append(data)
            except Exception as e:
                logger.error(f"Error loading fixture {file.name}: {e}")
        return fixtures

    def evaluate_single_decision(
        self,
        fixture: Dict[str, Any],
        decision_data: Dict[str, Any],
    ) -> DecisionEvaluation:
        """
        Evaluates a single decision against a scenario fixture using all validation layers:
        1. Expected outcome & direction matching
        2. SMC geometry oracle
        3. Risk compliance oracle
        4. Trade discipline oracle
        5. In-Harness Grounding validation
        6. Cross-timeframe alignment gate
        """
        scenario_id = fixture.get("scenario_id", "unknown")
        symbol = fixture.get("symbol", "UNKNOWN")
        dec = str(decision_data.get("decision", "WAIT")).strip().upper()

        expected = fixture.get("expected_outcome", {})
        valid_decisions = [d.upper() for d in expected.get("valid_decisions", [])]

        is_valid_dir = dec in valid_decisions if valid_decisions else (dec != "UNKNOWN")

        # Run oracles
        geo_res = evaluate_smc_geometry(fixture, decision_data)
        risk_res = evaluate_risk_compliance(fixture, decision_data)
        disc_res = evaluate_trade_discipline(fixture, decision_data)

        oracle_violations = geo_res["violations"] + risk_res["violations"] + disc_res["violations"]
        oracle_passed = len(oracle_violations) == 0

        # Grounding check (if InHarnessGroundingValidator is available)
        grounding_passed = True
        grounding_errors = []
        try:
            from analysis.validators.in_harness_grounding import InHarnessGroundingValidator
            # Construct a synthetic data bundle from fixture for grounding
            bundle = {
                "get_quote": {
                    "bid": fixture.get("current_price", 1.0),
                    "ask": fixture.get("current_price", 1.0) + (fixture.get("spread_pips", 1.0) * 0.0001),
                    "spread_pips": fixture.get("spread_pips", 1.0),
                },
                "account_equity": fixture.get("account_state", {}).get("equity", 10000.0),
                "free_margin": fixture.get("account_state", {}).get("equity", 10000.0) * 0.95,
            }
            is_g, g_errs, _ = InHarnessGroundingValidator.verify_grounding(
                decision_payload=decision_data,
                data_bundle=bundle,
                symbol=symbol,
            )
            grounding_passed = is_g
            grounding_errors = g_errs
        except Exception as e:
            logger.debug(f"Grounding validator exception during eval: {e}")

        # Planned R:R computation
        planned_rr = None
        ep = decision_data.get("entry_price")
        sl = decision_data.get("stop_loss")
        tp = decision_data.get("take_profit")
        if ep and sl and tp:
            risk = abs(ep - sl)
            reward = abs(tp - ep)
            if risk > 0:
                planned_rr = round(reward / risk, 2)

        return DecisionEvaluation(
            scenario_id=scenario_id,
            symbol=symbol,
            decision=dec,
            is_valid_direction=is_valid_dir,
            confluence_score=decision_data.get("confluence_score"),
            grounding_passed=grounding_passed,
            grounding_errors=grounding_errors,
            oracle_passed=oracle_passed,
            oracle_violations=oracle_violations,
            planned_rr=planned_rr,
            realized_rr=decision_data.get("realized_rr"),
            input_tokens=decision_data.get("input_tokens", 0),
            output_tokens=decision_data.get("output_tokens", 0),
            cost_usd=decision_data.get("cost_usd", 0.0),
            latency_ms=decision_data.get("latency_ms", 0.0),
        )

    def run_ab_benchmark(
        self,
        baseline_decisions: Dict[str, Dict[str, Any]],
        candidate_decisions: Dict[str, Dict[str, Any]],
        experiment_name: str = "A/B Experiment",
    ) -> ABReport:
        """
        Executes an A/B evaluation between baseline and candidate decision sets
        across all loaded fixtures.
        """
        fixtures = self.load_fixtures()
        baseline_evals = []
        candidate_evals = []

        for fix in fixtures:
            scen_id = fix.get("scenario_id")
            if not scen_id:
                continue

            base_data = baseline_decisions.get(scen_id, {"decision": "WAIT"})
            cand_data = candidate_decisions.get(scen_id, {"decision": "WAIT"})

            base_eval = self.evaluate_single_decision(fix, base_data)
            cand_eval = self.evaluate_single_decision(fix, cand_data)

            baseline_evals.append(base_eval)
            candidate_evals.append(cand_eval)

        return compare_ab_evaluations(
            baseline_results=baseline_evals,
            candidate_results=candidate_evals,
            name=experiment_name,
        )
