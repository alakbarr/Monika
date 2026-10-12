import pytest
from analysis.validators.in_harness_grounding import InHarnessGroundingValidator

def test_grounding_valid_setup():
    data_bundle = {
        "current_price": 2735.0,
        "atr_14": 15.0,
        "smc_zones": [
            {"price_low": 2730.0, "price_high": 2735.0, "type": "OB", "is_mitigated": False},
            {"price_low": 2710.0, "price_high": 2715.0, "type": "FVG", "is_mitigated": False},
        ]
    }
    proposal = {
        "decision": "BUY",
        "entry_price": 2735.0,
        "stop_loss": 2718.0,  # Distance = 17.0 > 15.0 (1.0x ATR)
        "nearest_entry_zone": {"price_low": 2730.0, "price_high": 2735.0},
        "key_evidence": [
            "Price mitigating H4 unmitigated order block at 2730.00-2735.00",
            "Stop loss set at 2718.00 giving 1.13x ATR buffer from 15.0 ATR",
        ]
    }
    is_grounded, errors, metadata = InHarnessGroundingValidator.verify_grounding(proposal, data_bundle, "XAUUSD")
    assert is_grounded is True
    assert len(errors) == 0
    assert metadata["verified_anchors"] >= 2

def test_grounding_rejects_tight_sl():
    data_bundle = {
        "current_price": 2735.0,
        "atr_14": 15.0,
    }
    proposal = {
        "decision": "BUY",
        "entry_price": 2735.0,
        "stop_loss": 2730.0,  # Distance = 5.0 << 15.0 (too tight!)
        "key_evidence": ["Tight SL 5.0 pts"],
    }
    is_grounded, errors, metadata = InHarnessGroundingValidator.verify_grounding(proposal, data_bundle, "XAUUSD")
    assert is_grounded is False
    assert any("too tight for market noise" in e for e in errors)

def test_grounding_rejects_hallucinated_zone():
    data_bundle = {
        "current_price": 2735.0,
        "atr_14": 15.0,
        "smc_zones": [
            {"price_low": 2710.0, "price_high": 2715.0, "type": "FVG", "is_mitigated": False},
        ]
    }
    proposal = {
        "decision": "BUY",
        "entry_price": 2735.0,
        "stop_loss": 2715.0,
        # LLM invents an order block at 2748-2752 that does NOT exist in data_bundle!
        "nearest_entry_zone": {"price_low": 2748.0, "price_high": 2752.0},
        "key_evidence": ["Price at 2748.00 zone"],
    }
    is_grounded, errors, metadata = InHarnessGroundingValidator.verify_grounding(proposal, data_bundle, "XAUUSD")
    assert is_grounded is False
    assert any("does not match any empirical unmitigated zone" in e for e in errors)
    assert metadata["hallucination_flags"] >= 1

def test_grounding_allows_wait_decision():
    proposal = {"decision": "WAIT", "rationale": "Confluence score insufficient."}
    is_grounded, errors, _ = InHarnessGroundingValidator.verify_grounding(proposal, {}, "EURUSD")
    assert is_grounded is True
    assert len(errors) == 0
