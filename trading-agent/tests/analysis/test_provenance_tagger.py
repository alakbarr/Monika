"""
Unit tests for analysis/grounding/provenance_tagger.py.
"""
import pytest
from analysis.grounding.provenance_tagger import ProvenanceLedger, ObservedFact


def test_provenance_ledger_registration():
    ledger = ProvenanceLedger()
    tool_output = {
        "symbol": "EURUSD",
        "close": 1.0850,
        "atr_14": 0.0055,
        "levels": [1.0820, 1.0910],
        "nested": {"fvg_low": 1.0835, "fvg_high": 1.0845},
    }

    count = ledger.register_from_tool_output("get_indicators", tool_output)
    assert count == 6
    assert len(ledger.facts) == 6


def test_provenance_ledger_verify_citation():
    ledger = ProvenanceLedger()
    ledger.register_fact("EURUSD.close", 1.08542, tool_name="get_market_price")
    ledger.register_fact("EURUSD.support", 1.08000, tool_name="get_support_resistance")

    # Exact or near citation within tolerance
    match = ledger.verify_citation(1.0854, tolerance=1e-4)
    assert match is not None
    assert match.field == "EURUSD.close"
    assert match.tool_name == "get_market_price"

    # With field hint
    match_hint = ledger.verify_citation(1.0800, field_hint="support", tolerance=1e-4)
    assert match_hint is not None
    assert match_hint.field == "EURUSD.support"

    # Completely ungrounded/hallucinated number
    hallucinated = ledger.verify_citation(1.1250, tolerance=1e-4)
    assert hallucinated is None


def test_provenance_ledger_text_citations():
    ledger = ProvenanceLedger()
    ledger.register_fact("gold.close", 2650.50, tool_name="mt5_rates")
    ledger.register_fact("gold.atr", 18.25, tool_name="indicator_tool")

    text = "Gold closed at 2650.50 with ATR 18.25. Proposing target at 2799.99."
    verified, unverified, unverified_nums = ledger.verify_text_citations(text, tolerance=1e-3)

    assert verified >= 2
    assert 2799.99 in unverified_nums
