import pytest
from monika.application.agent.harness.turn_failure_diagnostics import (
    TurnFailureDiagnostic,
    TurnFailureDiagnosticBuilder,
)
from monika.application.agent.harness.anti_slop_gate import (
    AntiSlopVerdict,
    AntiSlopQualityGate,
    smart_distill_text,
)


def test_turn_failure_diagnostic_schema_validation():
    err_str = "Field 'confluence_score' is required for BUY/SELL decision"
    diag = TurnFailureDiagnosticBuilder.from_schema_validation_error(
        turn_number=1,
        tool_name="submit_asset_analysis",
        tool_input={"symbol": "EURUSD", "decision": "buy"},
        error_msg=err_str,
    )
    assert diag.category == "tool_schema_error"
    assert diag.tool_name == "submit_asset_analysis"
    assert "confluence_score" in diag.root_cause
    directive = diag.format_directive()
    assert "TURN FAILURE DIAGNOSTIC" in directive
    assert "tool_schema_error" in directive
    assert "submit_asset_analysis" in directive
    assert "Required Remediation" in directive


def test_turn_failure_diagnostic_tool_execution():
    diag = TurnFailureDiagnosticBuilder.from_tool_execution_error(
        turn_number=2,
        tool_name="calculate_position_size",
        tool_input={"symbol": "BTCUSD", "entry": 65000.0, "stop_loss": 65000.0},
        error_msg="DivisionByZero in volume calculation: stop_loss equals entry",
    )
    assert diag.category == "tool_execution_error"
    assert "calculate_position_size" in diag.tool_name
    assert "DivisionByZero" in diag.root_cause
    directive = diag.format_directive()
    assert "tool_execution_error" in directive


def test_turn_failure_diagnostic_stop_gate_rejection():
    diag = TurnFailureDiagnosticBuilder.from_stop_gate_rejection(
        turn_number=3,
        gate_name="CodeVerifyStopGate",
        reason="File edits made to 'src/calc.py' but no test/verification command was executed.",
        remaining_turns=2,
    )
    assert diag.category == "stop_gate_rejection"
    assert "CodeVerifyStopGate" in diag.root_cause or "CodeVerifyStopGate" in diag.what_failed
    directive = diag.format_directive()
    assert "stop_gate_rejection" in directive


def test_turn_failure_diagnostic_slop_rejection():
    diag = TurnFailureDiagnosticBuilder.from_slop_rejection(
        turn_number=4,
        violations=["delve into", "a testament to"],
        stage_name="per_asset",
    )
    assert diag.category == "slop_quality_rejection"
    directive = diag.format_directive()
    assert "slop_quality_rejection" in directive
    assert "delve into" in directive


def test_anti_slop_gate_evaluation():
    slop_text = (
        "Certainly! Let us delve into the fascinating tapestry of market dynamics. "
        "It is important to remember that this is a testament to the robust macroeconomic landscape. "
        "In conclusion, hope this helps!"
    )
    verdict = AntiSlopQualityGate.evaluate(slop_text)
    assert verdict.passed is False
    assert len(verdict.violations) >= 1
    assert any("delve" in p for p in verdict.violations)

    clean_text = (
        "EURUSD D1 is in a confirmed downtrend following rejection at 1.0920 supply zone. "
        "H4 structure broke lower with ChoCH at 1.0850. RSI_14 is 42.1 (momentum expanding). "
        "Plan: Place limit SELL order at 1.0880 (unmitigated H1 FVG), SL at 1.0935 (above swing high), "
        "TP at 1.0770 (target liquidity). R:R is 2.0x with verified ATR_14 buffer of 1.4x."
    )
    clean_verdict = AntiSlopQualityGate.evaluate(clean_text)
    assert clean_verdict.passed is True
    assert len(clean_verdict.violations) == 0


def test_anti_slop_gate_sanitization():
    messy_text = (
        "Certainly! Here is the analysis:\n\n"
        "EURUSD trend is bearish. Resistance at 1.0900.\n\n"
        "Hope this helps! Let me know if you need anything else!"
    )
    sanitized = AntiSlopQualityGate.sanitize_surface_slop(messy_text)
    assert "Certainly!" not in sanitized
    assert "Hope this helps!" not in sanitized
    assert "EURUSD trend is bearish. Resistance at 1.0900." in sanitized


def test_smart_distill_text():
    long_narrative = (
        "First sentence establishes the macro context for US Dollar strength. "
        "Second sentence highlights the hawkish stance of the Federal Reserve amid persistent inflation. "
        "Third sentence details European economic stagnation and ECB rate cuts. "
        "Fourth sentence provides granular tactical support at 1.0820 and resistance at 1.0950."
    )
    distilled = smart_distill_text(long_narrative, max_chars=120)
    assert len(distilled) <= 125
    assert not distilled.endswith("..")
    # Must end at sentence or punctuation boundary
    assert distilled.endswith(".") or distilled.endswith("...")


@pytest.mark.asyncio
async def test_multi_persona_risk_fail_closed_default():
    from unittest.mock import AsyncMock, MagicMock
    from monika.application.analysis.debate.multi_persona_risk_llm import analyze_risk_multi_persona_llm

    mock_client = MagicMock()
    # Response where conservative persona omitted 'veto_trade' field
    mock_client.generate_content = AsyncMock(
        return_value="""{
            "conservative": {"risk_profile_assessment": "Cautious", "recommended_multiplier": 0.4},
            "aggressive": {"risk_profile_assessment": "Aggressive", "recommended_multiplier": 1.0, "veto_trade": false},
            "neutral": {"risk_profile_assessment": "Neutral", "recommended_multiplier": 0.7, "veto_trade": false}
        }"""
    )

    res = await analyze_risk_multi_persona_llm(mock_client, "EURUSD", {"confluence_score": 7})
    # Must fail-closed: missing veto_trade defaults to True!
    assert res["conservative"]["veto_trade"] is True
    assert res["aggressive"]["veto_trade"] is False
    assert res["neutral"]["veto_trade"] is False
