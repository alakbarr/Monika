# ==============================================================================
# File: tests/memory/test_adaptive_context_engine.py
# ==============================================================================

"""
Unit Test Suite for Stage 7:
Adaptive Pluggable Context Engine, Mechanical Anchor Index,
and Lossless State Archiving Pruner.
"""

import pytest

from analysis.memory.mechanical_anchor_index import MechanicalAnchorIndex
from analysis.memory.context_engine import ContextEngine
from graph.nodes.state_pruner import prune_after_fundamental, prune_after_debate


# ==============================================================================
# 1. Mechanical Anchor Index Tests
# ==============================================================================

def test_mechanical_anchor_extraction_and_rendering():
    index = MechanicalAnchorIndex()

    text = (
        "Order execution confirmed: ticket #789012. "
        "Symbol EURUSD, size 0.25 lots, risk 1.5% risk. "
        "Stop Loss at 1.0820 and Take Profit at 1.0950."
    )

    found = index.extract_anchors(text)

    assert "789012" in found["tickets"]
    assert found["price_levels"]["SL"] == 1.0820
    assert found["price_levels"]["TP"] == 1.0950
    assert 0.25 in found["lots"]
    assert 1.5 in found["risk_percentages"]

    rendered = index.render_anchor_block()
    assert "<mechanical-invariants>" in rendered
    assert "ACTIVE_TICKETS: 789012" in rendered
    assert "SL=1.082" in rendered
    assert "TP=1.095" in rendered
    assert "0.25 lots" in rendered
    assert "1.5%" in rendered


# ==============================================================================
# 2. Adaptive Context Engine Tests
# ==============================================================================

def test_context_engine_assembly():
    engine = ContextEngine(max_context_tokens=1000)

    # Process user turn with numerical anchor
    user_prompt = "Buy 0.1 lots GBPUSD ticket #123456 now."
    engine.process_incoming_turn(user_prompt)

    messages = [
        {"role": "user", "content": user_prompt},
        {"role": "assistant", "content": "Order dispatched successfully."},
    ]

    assembled = engine.assemble_context(
        system_prompt="You are Monika Trading Agent.",
        messages=messages,
        episodic_context="Past trade on GBPUSD was profitable with +45 pips.",
    )

    assert len(assembled) == 3
    sys_content = assembled[0]["content"]
    assert "You are Monika Trading Agent." in sys_content
    assert "<mechanical-invariants>" in sys_content
    assert "ACTIVE_TICKETS: 123456" in sys_content
    assert "<episodic-memory>" in sys_content


# ==============================================================================
# 3. Lossless State Archiving Pruner Tests
# ==============================================================================

def test_prune_after_fundamental_lossless():
    raw_conversation = "Huge verbose fundamental discussion text " * 50
    state = {
        "summary": {
            "fundamental": {
                "macro_bias": "BULLISH",
                "raw_conversation": raw_conversation,
                "unfiltered_headlines": ["H1", "H2", "H3"],
            }
        },
        "archived_payloads": {},
    }

    result = prune_after_fundamental(state)
    fund = result["summary"]["fundamental"]
    archives = result["archived_payloads"]

    # Active state key is replaced by compact reference
    assert "$ref" in fund["raw_conversation"]
    assert fund["raw_conversation"]["$ref"] == "archived_payloads/fundamental.raw_conversation"
    # Macro bias is kept intact
    assert fund["macro_bias"] == "BULLISH"

    # Original data preserved in archived_payloads
    assert archives["fundamental.raw_conversation"] == raw_conversation
    assert archives["fundamental.unfiltered_headlines"] == ["H1", "H2", "H3"]


def test_prune_after_debate_lossless():
    state = {
        "debate_states": {
            "EURUSD": {
                "consensus": "LONG",
                "raw_bull_text": "Detailed bull thesis",
                "raw_bear_text": "Detailed bear thesis",
            }
        },
        "asset_analyses": {
            "EURUSD": {
                "trend": "UP",
                "raw_candles": [1.08, 1.085, 1.082],
            }
        },
        "risk_debate_states": {},
        "archived_payloads": {},
    }

    result = prune_after_debate(state)
    archives = result["archived_payloads"]

    assert archives["debate.EURUSD.raw_bull_text"] == "Detailed bull thesis"
    assert archives["debate.EURUSD.raw_bear_text"] == "Detailed bear thesis"
    assert archives["asset.EURUSD.raw_candles"] == [1.08, 1.085, 1.082]

    # Active keys contain $ref pointers
    assert "$ref" in result["debate_states"]["EURUSD"]["raw_bull_text"]
    assert "$ref" in result["asset_analyses"]["EURUSD"]["raw_candles"]
