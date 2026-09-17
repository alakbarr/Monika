import pytest
from analysis.memory.working_scratchpad import WorkingScratchpad


def test_working_scratchpad_lifecycle():
    WorkingScratchpad.clear("EURUSD")
    state = WorkingScratchpad.get_or_create("EURUSD")
    assert state["symbol"] == "EURUSD"
    assert state["bias"] == "NEUTRAL"

    # Update with calculations
    WorkingScratchpad.update_scratchpad("EURUSD", {
        "bias": "BULLISH",
        "h4_atr": 0.0045,
        "daily_adr": 0.0075,
        "invalidation_price": 1.0780,
        "rr_ratio": 2.1,
        "confluence_score": 9.0,
        "verified_confluences": ["d1_trend", "near_order_block"],
        "notes": ["Confirmed H4 BOS at 1.0820", "OTE retracement active"]
    })

    read_back = WorkingScratchpad.read_scratchpad("EURUSD")
    assert read_back["bias"] == "BULLISH"
    assert read_back["h4_atr"] == 0.0045
    assert read_back["daily_adr"] == 0.0075
    assert read_back["invalidation_price"] == 1.0780
    assert read_back["rr_ratio"] == 2.1
    assert read_back["confluence_score"] == 9.0
    assert "d1_trend" in read_back["verified_confluences"]
    assert len(read_back["notes"]) == 2

    # Summary text
    summary = WorkingScratchpad.get_summary_text("EURUSD")
    assert "SCRATCHPAD[EURUSD]: bias=BULLISH" in summary
    assert "ATR14=0.0045" in summary
    assert "ADR5=0.0075" in summary
    assert "Invalidation=1.0780" in summary
    assert "RR=2.10" in summary

    # Clear
    WorkingScratchpad.clear("EURUSD")
    fresh = WorkingScratchpad.get_or_create("EURUSD")
    assert fresh["bias"] == "NEUTRAL"
    assert fresh["h4_atr"] is None
