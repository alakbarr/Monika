"""
Unit tests for SMC/ICT Prompt Evaluation Harness (Phase 1 Lean - Offline).
Validates schema compliance, structural integrity, rule adherence, and
confluence calculations against golden test fixtures without incurring API token costs.
"""

import json
import pytest
from pathlib import Path
from analysis.schemas.pydantic_schemas import SubmitAssetAnalysisSchema, TradeDirection

FIXTURES_PATH = Path(__file__).parent / "fixtures" / "smc_ict_fixtures.json"

@pytest.fixture
def smc_fixtures():
    assert FIXTURES_PATH.exists(), f"Fixtures file missing at {FIXTURES_PATH}"
    with open(FIXTURES_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("fixtures", [])

def test_fixtures_file_loaded(smc_fixtures):
    """Verify fixtures are present and well-formed."""
    assert len(smc_fixtures) >= 3
    for case in smc_fixtures:
        assert "id" in case
        assert "symbol" in case
        assert "expected_decision" in case
        assert "technical_data" in case

def test_fixture_schema_validation(smc_fixtures):
    """Ensure each fixture can construct valid SubmitAssetAnalysisSchema input."""
    for case in smc_fixtures:
        tech = case["technical_data"]
        decision = case["expected_decision"]
        
        # Build mock payload
        payload = {
            "symbol": case["symbol"],
            "decision": decision,
            "confidence": 0.85 if decision in ("buy", "sell") else 0.4,
            "entry_condition": {
                "type": "limit",
                "price": tech["entry_price"],
                "detail": f"Entry at FVG zone for {case['id']}"
            },
            "stop_loss": tech["stop_loss"],
            "take_profit": tech["take_profit"],
            "invalidation": "Breaks key structural level opposite to setup",
            "invalidation_price": tech["stop_loss"] if decision in ("buy", "sell") else None,
            "invalidation_direction": "below" if decision == "buy" else ("above" if decision == "sell" else None),
            "reevaluation_trigger": {"type": "time", "detail": "Re-evaluate in 6h"},
            "confluence_score": case.get("expected_min_confluence", 5),
            "priced_in_score": 3,
            "confluence_factors": ["near_fvg", "near_order_block", "liquidity_sweep_confirmed"],
            "rationale": f"Structured trade setup based on SMC playbook for {case['name']}"
        }
        
        # Validate schema instantiation
        validated = SubmitAssetAnalysisSchema.model_validate(payload)
        assert validated.symbol == case["symbol"]
        assert validated.decision == decision

def test_fixture_risk_reward_rules(smc_fixtures):
    """Verify risk-to-reward consistency on valid directional fixtures."""
    for case in smc_fixtures:
        if case["expected_decision"] in ("buy", "sell"):
            tech = case["technical_data"]
            risk = abs(tech["entry_price"] - tech["stop_loss"])
            reward = abs(tech["take_profit"] - tech["entry_price"])
            assert risk > 0
            rr = reward / risk
            expected_min_rr = case.get("expected_min_rr", 1.3)
            assert rr >= expected_min_rr, f"Case {case['id']} R:R {rr:.2f} below expected {expected_min_rr}"

def test_fixture_confluence_thresholds(smc_fixtures):
    """Verify confluence score thresholds align with decision logic."""
    for case in smc_fixtures:
        if case["expected_decision"] in ("buy", "sell"):
            min_conf = case.get("expected_min_confluence", 7)
            assert min_conf >= 7, f"Trade entry {case['id']} must require confluence >= 7"
        elif case["expected_decision"] == "wait":
            max_conf = case.get("expected_max_confluence", 6)
            assert max_conf < 7, f"Wait decision {case['id']} must have confluence < 7"
