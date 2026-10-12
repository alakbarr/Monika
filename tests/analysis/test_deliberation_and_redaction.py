import pytest
from unittest.mock import AsyncMock, MagicMock
from analysis.grounding.provenance_tagger import (
    ProvenanceLedger,
    AutomatedFigureRedactionGate,
)
from analysis.debate.investment_judge import evaluate_debate


def test_redact_unprovenanced_figures():
    ledger = ProvenanceLedger()
    # Register verified facts from market prefetch tool
    ledger.register_fact("eurusd_close", 1.0850, tool_name="mt5_quote")
    ledger.register_fact("eurusd_atr", 0.0045, tool_name="indicator_calc")

    text = "The EURUSD closed at 1.0850 with ATR of 0.0045, but I predict it hits 1.4500 and inflation spikes to 88.5%."
    sanitized, redacted = ledger.redact_unprovenanced_figures(text)

    # 1.0850 and 0.0045 are verified and should remain
    assert "1.0850" in sanitized
    assert "0.0045" in sanitized
    # 1.4500 and 88.5 are hallucinated/unverified and must be redacted
    assert "[UNVERIFIED_FIGURE_REDACTED]" in sanitized
    assert 1.45 in redacted or 1.4500 in redacted
    assert 88.5 in redacted


def test_automated_figure_redaction_gate():
    ledger = ProvenanceLedger()
    ledger.register_fact("btc_price", 95000.0, tool_name="mt5_quote")

    gate = AutomatedFigureRedactionGate(ledger=ledger, strict=True)
    payload = {
        "bull_thesis": "BTC is strong at 95000.0 but target is 199999.0.",
        "bear_dissent": "Major resistance at 95000.0.",
    }

    cleaned_payload, redacted_nums, passed = gate.sanitize_payload(payload)
    assert not passed  # strict mode failed due to unverified 199999.0
    assert 199999.0 in redacted_nums
    assert "[UNVERIFIED_FIGURE_REDACTED]" in cleaned_payload["bull_thesis"]
    assert "95000.0" in cleaned_payload["bear_dissent"]


@pytest.mark.asyncio
async def test_investment_judge_brier_calibration():
    # Mock LLM client
    client = MagicMock()
    del client.classify_json
    client.default_temperature = 0.2
    client.max_tokens = 4096
    client.generate_content = AsyncMock(return_value='{"final_decision": "buy", "reason": "Solid setup", "risk_multiplier": 0.8}')

    # Case 1: Bear analyst has much lower Brier error (0.12 vs Bull 0.35) -> Dissenter advantage
    context = {
        "decision": "BUY",
        "market_regime": "trending",
        "bull_brier": 0.35,
        "bear_brier": 0.12,
    }
    bull_claim = {"strength_score": 7, "thesis": "Bull momentum"}
    bear_dissent = {"risk_severity": 6, "dissent": "Resistance ahead"}

    res = await evaluate_debate(
        client=client,
        symbol="EURUSD",
        original_context=context,
        bull_claim=bull_claim,
        bear_dissent=bear_dissent,
    )

    assert "brier_calibration" in res
    assert res["brier_calibration"]["bear_brier"] == 0.12
    # Bear has superior calibration advantage with severity 6 -> raw risk multiplier dampened by 0.75x: 0.8 * 0.75 = 0.60
    assert res["risk_multiplier"] == 0.60
