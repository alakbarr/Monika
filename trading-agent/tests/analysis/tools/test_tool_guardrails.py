# ==============================================================================
# File: tests/analysis/tools/test_tool_guardrails.py
# ==============================================================================

import pytest
from analysis.tools.tool_guardrails import (
    ToolCallSignature,
    AntiOscillationGuard,
    MonotonicRiskGuard,
    ReadBeforeActGuard,
    MandatorySizingGuard,
    CategoryTurnCapGuard,
    ToolGuardrailController,
    GuardrailVerdict,
)


def test_tool_call_signature_deterministic():
    args1 = {"symbol": "EURUSD", "timeframe": "H1", "limit": 100}
    args2 = {"limit": 100, "symbol": "EURUSD", "timeframe": "H1"}
    sig1 = ToolCallSignature.compute("get_price_history", args1)
    sig2 = ToolCallSignature.compute("get_price_history", args2)
    assert sig1 == sig2
    assert sig1.startswith("get_price_history:")


def test_anti_oscillation_guard_detects_repeat():
    guard = AntiOscillationGuard(window_size=5)
    sig = "tool_a:12345"

    v1 = guard.evaluate(sig, "tool_a")
    assert v1.allowed is True
    guard.record(sig)

    # 2nd consecutive repeat -> suppressed
    v2 = guard.evaluate(sig, "tool_a")
    assert v2.allowed is False
    assert v2.action == "suppress"
    assert "already executed" in v2.reason


def test_monotonic_risk_guard():
    guard = MonotonicRiskGuard()

    # Paused trading -> buy order blocked
    v_paused = guard.evaluate(
        tool_name="submit_asset_analysis",
        args={"decision": "buy", "symbol": "XAUUSD"},
        context={"trading_paused": True},
    )
    assert v_paused.allowed is False
    assert "PAUSED" in v_paused.reason

    # Paused trading -> avoid decision allowed
    v_avoid = guard.evaluate(
        tool_name="submit_asset_analysis",
        args={"decision": "avoid", "symbol": "XAUUSD"},
        context={"trading_paused": True},
    )
    assert v_avoid.allowed is True

    # Risk denied in cycle -> buy blocked
    v_denied = guard.evaluate(
        tool_name="submit_asset_analysis",
        args={"decision": "buy", "symbol": "EURUSD"},
        context={"risk_denied": True},
    )
    assert v_denied.allowed is False
    assert "RiskGate" in v_denied.reason


def test_read_before_act_guard():
    guard = ReadBeforeActGuard()

    # Action before reading data -> blocked
    v_early = guard.evaluate("submit_asset_analysis", {"decision": "buy", "symbol": "GBPUSD"})
    assert v_early.allowed is False
    assert v_early.action == "nudge"
    assert "MUST query real-time data" in v_early.reason

    # Read market data first
    guard.record_call("get_price_history")

    # Now action is allowed
    v_after_read = guard.evaluate("submit_asset_analysis", {"decision": "buy", "symbol": "GBPUSD"})
    assert v_after_read.allowed is True


def test_mandatory_sizing_guard():
    guard = MandatorySizingGuard()

    # Missing lots and risk_percent -> rejected
    v_no_size = guard.evaluate("place_order", {"symbol": "XAUUSD", "action": "buy"})
    assert v_no_size.allowed is False
    assert "lacks mandatory position sizing" in v_no_size.reason

    # Invalid negative lots -> rejected
    v_neg = guard.evaluate("place_order", {"symbol": "XAUUSD", "action": "buy", "lot_size": -0.5})
    assert v_neg.allowed is False
    assert "strictly positive" in v_neg.reason

    # Valid lots -> allowed
    v_valid = guard.evaluate("place_order", {"symbol": "XAUUSD", "action": "buy", "lot_size": 0.1})
    assert v_valid.allowed is True


def test_category_turn_cap_guard():
    guard = CategoryTurnCapGuard(caps={"macro": 3})

    for i in range(3):
        v = guard.evaluate("get_dxy")
        assert v.allowed is True
        guard.record_call("get_dxy")

    # 4th call in macro exceeds quota of 3
    v_exceeded = guard.evaluate("get_vix")
    assert v_exceeded.allowed is False
    assert v_exceeded.action == "suppress"
    assert "quota exceeded" in v_exceeded.reason


def test_unified_tool_guardrail_controller():
    controller = ToolGuardrailController()

    # 1. First call: get_price_history (read tool)
    v1 = controller.validate_tool_call("get_price_history", {"symbol": "EURUSD"})
    assert v1.allowed is True
    controller.record_tool_call("get_price_history", {"symbol": "EURUSD"})

    # 2. Duplicate immediate call -> caught by anti-oscillation
    v2 = controller.validate_tool_call("get_price_history", {"symbol": "EURUSD"})
    assert v2.allowed is False
    assert v2.action == "suppress"

    # 3. Valid analysis submission after data read
    v3 = controller.validate_tool_call(
        "submit_asset_analysis",
        {"symbol": "EURUSD", "decision": "buy"},
    )
    assert v3.allowed is True


def test_unified_tool_guardrail_resets():
    controller = ToolGuardrailController()
    controller.category_turn_cap.caps["macro"] = 2

    # Fill turn cap
    controller.record_tool_call("get_dxy", {})
    controller.record_tool_call("get_vix", {})
    assert controller.validate_tool_call("get_yield_data", {}).allowed is False

    # reset_turn resets the turn cap
    controller.reset_turn()
    assert controller.validate_tool_call("get_yield_data", {}).allowed is True

    # Fill anti-oscillation
    assert controller.validate_tool_call("get_atr", {"symbol": "XAUUSD"}).allowed is True
    controller.record_tool_call("get_atr", {"symbol": "XAUUSD"})
    assert controller.validate_tool_call("get_atr", {"symbol": "XAUUSD"}).allowed is False

    # reset_all resets everything
    controller.reset_all()
    assert controller.validate_tool_call("get_atr", {"symbol": "XAUUSD"}).allowed is True
