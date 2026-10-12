# ==============================================================================
# File: tests/analysis/grounding/test_extended_grounding.py
# ==============================================================================

import pytest
from analysis.grounding.provenance_tagger import ProvenanceLedger
from analysis.validators.in_harness_grounding import InHarnessGroundingValidator


def test_lot_size_grounding_valid():
    ledger = ProvenanceLedger()
    # 0.1 lots on $10,000 account with 50 pip SL on EURUSD
    ok, err = ledger.verify_lot_size(
        symbol="EURUSD",
        lot_size=0.10,
        account_equity=10000.0,
        entry_price=1.0850,
        stop_loss=1.0800,
        risk_pct=1.0,
    )
    assert ok is True
    assert err is None


def test_lot_size_grounding_rejects_insane_hallucinations():
    ledger = ProvenanceLedger()
    # 50.0 lots on $1,000 account -> notional = 50 * 100,000 * 1.0850 = $5,425,000 (leverage > 5000x!)
    ok, err = ledger.verify_lot_size(
        symbol="EURUSD",
        lot_size=50.0,
        account_equity=1000.0,
        entry_price=1.0850,
        stop_loss=1.0800,
        risk_pct=1.0,
    )
    assert ok is False
    assert "Ungrounded lot size" in err
    assert "exceeds maximum permitted leverage" in err


def test_spread_grounding_blowout():
    ledger = ProvenanceLedger()
    # Empirical spread is 75.0 points (> ceiling of 60.0)
    ok, err = ledger.verify_spread(symbol="EURUSD", empirical_spread=75.0, max_spread_ceiling=60.0)
    assert ok is False
    assert "Spread blowout detected" in err

    # Normal spread is 12.0 points
    ok, err = ledger.verify_spread(symbol="EURUSD", empirical_spread=12.0, max_spread_ceiling=60.0)
    assert ok is True
    assert err is None


def test_spread_grounding_divergence():
    ledger = ProvenanceLedger()
    # Model cites 5.0 spread when empirical market is 25.0 points
    ok, err = ledger.verify_spread(symbol="XAUUSD", empirical_spread=25.0, cited_spread=5.0)
    assert ok is False
    assert "diverges substantially" in err


def test_margin_grounding_insufficient():
    ledger = ProvenanceLedger()
    # 5.0 lots EURUSD requires ~$5,425 margin at 1:100 leverage; free margin is only $2,000
    ok, err = ledger.verify_margin(
        symbol="EURUSD",
        lot_size=5.0,
        entry_price=1.0850,
        free_margin=2000.0,
        leverage=100.0,
    )
    assert ok is False
    assert "Insufficient margin" in err


def test_equity_grounding_invalid():
    ledger = ProvenanceLedger()
    ok, err = ledger.verify_equity(account_equity=25.0, min_equity=50.0)
    assert ok is False
    assert "below minimum operational floor" in err

    ok, err = ledger.verify_equity(account_equity=-100.0)
    assert ok is False
    assert "equity must be positive" in err


def test_in_harness_grounding_with_extended_checks():
    # Test InHarnessGroundingValidator flagging extended lot size violation
    decision_payload = {
        "decision": "BUY",
        "entry_price": 1.0850,
        "stop_loss": 1.0750,
        "take_profit": 1.1000,
        "lot_size": 25.0,  # Insane lot size for $2,000 account
        "rationale": "Strong bullish momentum with BOS confirmed.",
        "key_evidence": ["1.0850 entry with ATR 0.0050"],
    }
    data_bundle = {
        "price": 1.0850,
        "atr": 0.0050,
        "account_equity": 2000.0,
        "free_margin": 1900.0,
        "spread": 12.0,
    }

    is_grounded, errors, meta = InHarnessGroundingValidator.verify_grounding(
        decision_payload=decision_payload,
        data_bundle=data_bundle,
        symbol="EURUSD",
    )

    assert is_grounded is False
    assert any("Ungrounded lot size" in e for e in errors)
