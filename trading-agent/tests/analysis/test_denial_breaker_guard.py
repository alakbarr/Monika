"""
Unit tests for DenialCircuitBreakerGuard and ToolGuardrailController integration.
"""

from analysis.tools.tool_guardrails import ToolGuardrailController, DenialCircuitBreakerGuard


def test_denial_circuit_breaker_standalone():
    breaker = DenialCircuitBreakerGuard(threshold=3)

    v1 = breaker.evaluate("submit_asset_analysis")
    assert v1.allowed is True

    # Record 2 denials -> still not tripped
    assert breaker.record_denial() is False
    assert breaker.record_denial() is False
    assert breaker.evaluate("submit_asset_analysis").allowed is True

    # 3rd denial -> trips breaker
    assert breaker.record_denial() is True
    v_tripped = breaker.evaluate("submit_asset_analysis")
    assert v_tripped.allowed is False
    assert v_tripped.action == "reject"
    assert "Circuit breaker tripped" in v_tripped.reason

    # Reset
    breaker.reset()
    assert breaker.evaluate("submit_asset_analysis").allowed is True


def test_tool_guardrail_controller_denial_breaker_integration():
    controller = ToolGuardrailController({"denial_breaker_threshold": 3})

    # Record 3 denials
    controller.record_denial()
    controller.record_denial()
    controller.record_denial()

    verdict = controller.validate_tool_call("get_price_history", {"symbol": "XAUUSD"})
    assert verdict.allowed is False
    assert verdict.guard_name == "DenialCircuitBreakerGuard"

    # Successful advancing call resets counter
    controller.reset_all()
    controller.denial_breaker.reset()
    verdict_after = controller.validate_tool_call("get_price_history", {"symbol": "XAUUSD"})
    assert verdict_after.allowed is True
