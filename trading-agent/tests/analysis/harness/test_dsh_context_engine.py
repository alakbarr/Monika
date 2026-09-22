# ==============================================================================
# File: tests/analysis/harness/test_dsh_context_engine.py
# ==============================================================================

import pytest
from unittest.mock import AsyncMock, MagicMock
from analysis.harness.context_compressor import ContextCompressor, TRADING_SUMMARY_SECTIONS


def test_dsh_8_section_trading_summary_constants():
    """Verify standard 8 DSH trading sections are defined."""
    assert len(TRADING_SUMMARY_SECTIONS) == 8
    expected = [
        "market_regime",
        "technical_structure",
        "liquidity_pois",
        "intermarket_sentiment",
        "active_hypotheses",
        "established_levels",
        "risk_constraints",
        "completed_actions_evidence",
    ]
    assert TRADING_SUMMARY_SECTIONS == expected


@pytest.mark.asyncio
async def test_8_section_trading_summary_generation():
    """Verify that deterministic summarization populates the 8 XML sections."""
    compressor = ContextCompressor(settings={})
    middle_msgs = [
        {"role": "assistant", "content": "DXY = 104.5, VIX = 16.2, regime = RISK_ON"},
        {"role": "user", "content": "ATR = 0.0055, RSI = 58.2, BOS confirmed above 1.0850"},
        {"role": "assistant", "content": "Order Block = 1.0820, FVG = 1.0830-1.0840, liquidity sweep at Asian high"},
        {"role": "user", "content": "10Y Treasury yield = 4.25%, sentiment = bullish"},
        {"role": "assistant", "content": "bias = bullish, thesis = H4 trend continuation"},
        {"role": "user", "content": "EURUSD price = 1.0865, Stop Loss = 1.0810, Take Profit = 1.0960"},
        {"role": "assistant", "content": "lot size = 0.50, R:R = 1.72, ADR within limits"},
        {"role": "user", "content": "tool: get_indicators executed, verified quotes"},
    ]

    summary = await compressor.summarize_middle(middle_msgs)

    assert "<compacted-summary>" in summary
    assert "</compacted-summary>" in summary
    for sec in TRADING_SUMMARY_SECTIONS:
        assert f"<{sec}>" in summary
        assert f"</{sec}>" in summary

    # Check key domain facts
    assert "DXY = 104.5" in summary
    assert "ATR = 0.0055" in summary
    assert "EURUSD price = 1.0865" in summary
    assert "Stop Loss = 1.0810" in summary
    assert "R:R = 1.72" in summary


def test_tool_pair_snapping_openai_format():
    """Verify _snap_boundary pulls assistant turn when split lands on role=='tool'."""
    compressor = ContextCompressor(settings={})
    messages = [
        {"role": "system", "content": "You are Monika."},
        {"role": "user", "content": "Analyze XAUUSD"},
        {"role": "assistant", "content": "Fetching quotes", "tool_calls": [{"id": "c1", "function": {"name": "get_quote"}}]},
        {"role": "tool", "content": '{"symbol": "XAUUSD", "price": 2650.0}', "tool_call_id": "c1"},
        {"role": "assistant", "content": "Analyzing structure"},
        {"role": "user", "content": "Proceed"},
    ]

    # If split index lands on role=='tool' (index 3), must snap back to index 2 (assistant tool_call)
    snapped = compressor._snap_boundary(messages, split_idx=3)
    assert snapped == 2


@pytest.mark.asyncio
async def test_kv_cache_prefix_invariance():
    """Verify Head (frozen static prefix) remains byte-for-byte identical across turns."""
    compressor = ContextCompressor(settings={})
    head_sys = {"role": "system", "content": "FROZEN_STATIC_SYSTEM_PREFIX: Invariant rules and risk engine v2"}
    head_usr = {"role": "user", "content": "FROZEN_INITIAL_TASK: Intraday scan for EURUSD and XAUUSD"}

    conversation = [head_sys, head_usr]

    # Add 12 turns to trigger boundary split
    for i in range(12):
        role = "assistant" if i % 2 == 0 else "user"
        conversation.append({"role": role, "content": f"Turn {i} content with observations " + "X" * 300})

    compressed1 = await compressor.compress(conversation, max_context_chars=1000, tail_turns=2)
    assert compressed1[0] == head_sys
    assert compressed1[1] == head_usr

    # Add 4 more turns
    for i in range(12, 16):
        role = "assistant" if i % 2 == 0 else "user"
        conversation.append({"role": role, "content": f"Turn {i} content with observations " + "Y" * 300})

    compressed2 = await compressor.compress(conversation, max_context_chars=1000, tail_turns=2)
    # Head remains strictly invariant
    assert compressed2[0] == head_sys
    assert compressed2[1] == head_usr
    assert compressed2[0] == compressed1[0]
    assert compressed2[1] == compressed1[1]


@pytest.mark.asyncio
async def test_iterative_xml_compacted_summary_chaining():
    """Verify that prior <compacted-summary> block in middle messages is cleanly extracted and chained."""
    compressor = ContextCompressor(settings={})
    prior_summary_xml = (
        "<compacted-summary>\n"
        "  <technical_structure>• Prior H4 BOS at 1.0800</technical_structure>\n"
        "</compacted-summary>"
    )
    middle_msgs = [
        {"role": "user", "content": f"[CONDENSED CONTEXT SUMMARY]\n{prior_summary_xml}\n[END SUMMARY]"},
        {"role": "assistant", "content": "EURUSD price = 1.0890, RSI = 62.0"},
    ]

    summary = await compressor.summarize_middle(middle_msgs)
    assert "<compacted-summary>" in summary
    assert "Prior H4 BOS at 1.0800" in summary
    assert "1.0890" in summary
