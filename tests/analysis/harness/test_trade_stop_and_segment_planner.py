import pytest
from analysis.harness.verification_evidence_ledger import VerificationEvidenceLedger
from analysis.harness.trade_stop_gates import TradeStopGate
from analysis.harness.symbol_segment_planner import SymbolSegmentPlanner


def test_verification_evidence_ledger():
    ledger = VerificationEvidenceLedger()
    assert not ledger.has_passed_evidence("EURUSD")

    # Irrelevant tool
    res = ledger.record_tool_execution("get_candles", {"symbol": "EURUSD"}, {"close": 1.08})
    assert res is None
    assert not ledger.has_passed_evidence("EURUSD")

    # Verification tool failed
    ledger.record_tool_execution("calculate_position_size", {"symbol": "EURUSD"}, {"status": "failed", "error": "Invalid SL"})
    assert not ledger.has_passed_evidence("EURUSD")

    # Verification tool passed
    ledger.record_tool_execution("calculate_position_size", {"symbol": "EURUSD"}, {"status": "success", "lot": 0.15})
    assert ledger.has_passed_evidence("EURUSD")
    assert not ledger.has_passed_evidence("XAUUSD")

    ledger.reset_turn()
    assert not ledger.has_passed_evidence("EURUSD")


def test_trade_stop_gate_blocks_unverified_trade():
    ledger = VerificationEvidenceLedger()
    
    # Model recommends BUY EURUSD without verification evidence
    text = '{"action": "BUY", "symbol": "EURUSD", "entry": 1.0850, "sl": 1.0820, "tp": 1.0910}'
    verdict = TradeStopGate.evaluate(text, ledger, stage_name="per_asset_EURUSD", stage_symbol="EURUSD")

    assert not verdict.should_stop
    assert verdict.detected_action == "BUY"
    assert "TRADE VERIFICATION STOP GATE" in verdict.nudge_text
    assert "calculate_position_size" in verdict.nudge_text


def test_trade_stop_gate_allows_verified_trade():
    ledger = VerificationEvidenceLedger()
    ledger.record_tool_execution("calculate_position_size", {"symbol": "EURUSD"}, {"status": "success", "lot": 0.2})

    text = 'DECISION: BUY EURUSD at 1.0850, SL: 1.0820, TP: 1.0910'
    verdict = TradeStopGate.evaluate(text, ledger, stage_name="per_asset_EURUSD", stage_symbol="EURUSD")

    assert verdict.should_stop
    assert verdict.detected_action == "BUY"
    assert verdict.nudge_text is None


def test_trade_stop_gate_allows_wait_without_evidence():
    ledger = VerificationEvidenceLedger()
    # No trade proposed
    text = 'DECISION: WAIT. Market structure is choppy and no A+ setup is present.'
    verdict = TradeStopGate.evaluate(text, ledger, stage_name="per_asset_EURUSD", stage_symbol="EURUSD")

    assert verdict.should_stop
    assert verdict.detected_action == "WAIT"


def test_symbol_segment_planner():
    # 1. Independent symbols -> parallel segment
    calls = [
        {"name": "get_candles", "input": {"symbol": "EURUSD"}},
        {"name": "get_candles", "input": {"symbol": "XAUUSD"}},
        {"name": "get_news_items", "input": {}},
    ]
    segments = SymbolSegmentPlanner.plan_segments(calls)
    assert len(segments) == 1
    assert segments[0][0] == "parallel"
    assert len(segments[0][1]) == 3

    # 2. Conflicting mutating tools on same symbol -> sequential separation
    calls_conflict = [
        {"name": "get_candles", "input": {"symbol": "EURUSD"}},
        {"name": "execute_trade", "input": {"symbol": "EURUSD"}},
        {"name": "get_candles", "input": {"symbol": "XAUUSD"}},
    ]
    segments_conflict = SymbolSegmentPlanner.plan_segments(calls_conflict)
    assert len(segments_conflict) >= 2
    # At least one sequential segment
    types = [s[0] for s in segments_conflict]
    assert "sequential" in types


def test_trade_stop_gate_rejection_reason():
    ledger = VerificationEvidenceLedger()
    text = '{"action": "SELL", "symbol": "GBPUSD", "entry": 1.2500, "sl": 1.2550, "tp": 1.2400}'
    verdict = TradeStopGate.evaluate(text, ledger, stage_name="per_asset_GBPUSD", stage_symbol="GBPUSD")

    assert not verdict.should_stop
    assert verdict.detected_action == "SELL"
    assert verdict.rejection_reason is not None
    assert "verification evidence" in verdict.rejection_reason
