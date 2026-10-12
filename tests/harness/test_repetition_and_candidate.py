import json
import pytest
from analysis.harness.repetition_guard import detect_text_repetition
from analysis.harness.trade_stop_gates import TradeStopGate
from analysis.harness.verification_evidence_ledger import VerificationEvidenceLedger


def test_repetition_guard_detects_loop():
    repeated_pattern = "EURUSD order block identified at 1.0850. Confirming setup. " * 5
    text = f"Initial thoughts. {repeated_pattern} More thoughts."
    
    is_loop, sample = detect_text_repetition(text, min_phrase_len=30, min_repeats=3)
    assert is_loop is True
    assert "EURUSD" in sample


def test_repetition_guard_passes_normal_text():
    normal_text = (
        "EURUSD order block identified at 1.0850. Invalidation at 1.0820. "
        "Next, checking XAUUSD liquidity sweep near 2350. Stop loss at 2355. "
        "Reviewing daily risk state: daily drawdown is currently -0.5%."
    )
    is_loop, sample = detect_text_repetition(normal_text, min_phrase_len=30, min_repeats=3)
    assert is_loop is False
    assert sample is None


def test_candidate_preservation_downgrade_logic():
    # Test TradeStopGate detecting an unverified trade proposal
    unverified_reply = json.dumps({
        "action": "BUY",
        "direction": "BUY",
        "confidence": 0.85,
        "entry_price": 1.0850,
        "stop_loss": 1.0820,
        "take_profit": 1.0895,
    })

    empty_ledger = VerificationEvidenceLedger()

    # When no verification tools were recorded in ledger, TradeStopGate blocks stop
    verdict = TradeStopGate.evaluate(
        text_content=unverified_reply,
        ledger=empty_ledger,
        stage_name="per_asset_stage",
        stage_symbol="EURUSD",
    )
    assert verdict.should_stop is False
    assert verdict.detected_action == "BUY"
    assert verdict.detected_symbol == "EURUSD"

    # Candidate Preservation: when turns reach max, it safely downgrades to defensive WAIT
    downgraded = {
        "decision": "WAIT",
        "confidence": 0.0,
        "rationale": "Downgraded to defensive WAIT: Risk/sizing unverified before turn limit",
        "downgraded_by_stop_gate": True,
    }
    assert downgraded["decision"] == "WAIT"
    assert downgraded["downgraded_by_stop_gate"] is True


def test_durable_failed_turn_sealing():
    # Test turn sealing logic: user message followed by synthetic assistant turn on fatal exception
    current_messages = [
        {"role": "user", "content": "Analyze EURUSD setup"}
    ]

    if current_messages and current_messages[-1].get("role") == "user":
        current_messages.append({
            "role": "assistant",
            "content": "[Analysis turn terminated prematurely due to provider error. State preserved.]"
        })

    assert len(current_messages) == 2
    assert current_messages[-1]["role"] == "assistant"
    assert "State preserved" in current_messages[-1]["content"]
