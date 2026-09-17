import pytest
from analysis.subagent_blackboard import SubagentBlackboard

def test_subagent_blackboard_slots():
    bb = SubagentBlackboard("EURUSD")
    bb.set_slot("market_invariants", {"price": 1.0850, "atr_14": 0.0045, "vix": 18.2})
    bb.set_slot("technical_poi", {"directional_bias": "BULLISH", "confidence": "HIGH", "nearest_entry_zone": {"low": 1.0830, "high": 1.0840}})
    bb.set_slot("bull_thesis", {"core_argument": "D1 trend intact with unmitigated H4 FVG retest."})

    exported = bb.export_distilled_context(max_tokens=500)
    assert "MARKET_INVARIANTS:" in exported
    assert "price: 1.085" in exported
    assert "TECH_POI:" in exported
    assert "Bias=BULLISH" in exported
    assert "BULL_THESIS:" in exported
    assert "D1 trend intact" in exported
