# ==============================================================================
# File: tests/analysis/harness/test_context_compressor.py
# ==============================================================================

import pytest
from unittest.mock import AsyncMock, MagicMock

from analysis.harness.context_compressor import ContextCompressor


def test_compression_not_triggered_when_within_budget():
    compressor = ContextCompressor(settings={})
    messages = [
        {"role": "user", "content": "Analyze EURUSD."},
        {"role": "assistant", "content": "Checking market structure."},
        {"role": "user", "content": "Proceed."},
    ]
    res = pytest.importorskip("asyncio").run(compressor.compress(messages, max_context_chars=50000))
    assert res == messages


def test_deterministic_tool_pruning():
    compressor = ContextCompressor(settings={})
    messages = [
        {"role": "user", "content": "Analyze EURUSD."},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "get_price_history"}]},
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "t1",
                    "content": '{"error": "connection failed", "details": "' + "x" * 250 + '"}',
                }
            ],
        },
        {"role": "assistant", "content": [{"type": "tool_use", "id": "t2", "name": "get_price_history"}]},
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "t2",
                    "content": '{"symbol": "EURUSD", "close": 1.0850}',
                }
            ],
        },
    ]

    pruned = compressor.prune_deterministic_tools(messages)
    assert len(pruned) == len(messages)
    first_tool_res = pruned[2]["content"][0]["content"]
    assert "Pruned error tool observation" in first_tool_res


def test_protected_boundary_split():
    compressor = ContextCompressor(settings={})
    messages = [
        {"role": "user", "content": "Initial prompt - Head"},
        {"role": "assistant", "content": "Turn 1 assistant"},
        {"role": "user", "content": "Turn 1 user observation"},
        {"role": "assistant", "content": "Turn 2 assistant"},
        {"role": "user", "content": "Turn 2 user observation"},
        {"role": "assistant", "content": "Turn 3 assistant"},
        {"role": "user", "content": "Turn 3 user observation"},
        {"role": "assistant", "content": "Turn 4 assistant - Tail"},
        {"role": "user", "content": "Turn 4 user observation - Tail"},
        {"role": "assistant", "content": "Turn 5 assistant - Tail"},
        {"role": "user", "content": "Turn 5 user observation - Tail"},
        {"role": "assistant", "content": "Turn 6 assistant - Tail"},
        {"role": "user", "content": "Turn 6 user observation - Tail"},
    ]

    head, middle, tail = compressor.split_boundaries(messages, tail_turns=3)
    assert len(head) == 1
    assert head[0]["content"] == "Initial prompt - Head"
    assert len(tail) >= 6
    assert tail[0]["content"] == "Turn 4 assistant - Tail"
    assert len(middle) > 0


@pytest.mark.asyncio
async def test_summarize_middle_fallback_rule_extraction():
    compressor = ContextCompressor(settings={})
    middle_msgs = [
        {"role": "assistant", "content": "EURUSD price = 1.0850, ATR = 0.0055, RSI = 48.5"},
        {"role": "user", "content": "DXY = 104.2, VIX = 14.5, regime = RISK_ON"},
    ]
    summary = await compressor.summarize_middle(middle_msgs)
    assert "EURUSD price" in summary or "RSI" in summary or "DXY" in summary or "VIX" in summary


@pytest.mark.asyncio
async def test_summarize_middle_with_aux_client():
    mock_aux = AsyncMock()
    mock_aux.generate.return_value = "- Key Level: 1.0850 support held\n- RSI neutral\n- Bullish bias confirmed"

    compressor = ContextCompressor(settings={}, aux_client=mock_aux)
    middle_msgs = [
        {"role": "assistant", "content": "Testing middle chunk with lots of data..."},
        {"role": "user", "content": "Observed market reaction."},
    ]
    summary = await compressor.summarize_middle(middle_msgs)
    assert "Key Level: 1.0850" in summary
    mock_aux.generate.assert_awaited_once()


@pytest.mark.asyncio
async def test_full_4phase_compression():
    mock_aux = AsyncMock()
    mock_aux.generate.return_value = "• Established EURUSD support at 1.0820\n• DXY downtrend confirmed"

    compressor = ContextCompressor(settings={}, aux_client=mock_aux)
    messages = [
        {"role": "user", "content": "Head: Analyze EURUSD systematically."},
        {"role": "assistant", "content": "Intermediate turn 1"},
        {"role": "user", "content": "Observation 1: EURUSD price = 1.0850"},
        {"role": "assistant", "content": "Intermediate turn 2"},
        {"role": "user", "content": "Observation 2: ATR = 0.0060"},
        {"role": "assistant", "content": "Tail turn 1"},
        {"role": "user", "content": "Tail obs 1"},
        {"role": "assistant", "content": "Tail turn 2"},
        {"role": "user", "content": "Tail obs 2"},
        {"role": "assistant", "content": "Tail turn 3"},
        {"role": "user", "content": "Tail obs 3: Final confirmation."},
    ]

    compressed = await compressor.compress(messages, max_context_chars=100, tail_turns=3)

    assert compressed[0]["content"] == "Head: Analyze EURUSD systematically."
    assert any("[CONDENSED CONTEXT SUMMARY" in str(m.get("content", "")) for m in compressed)
    assert compressed[-1]["content"] == "Tail obs 3: Final confirmation."


@pytest.mark.asyncio
async def test_compression_not_triggered_when_message_count_high_but_chars_within_budget():
    """Verify that having > (tail_turns * 2) + 2 messages does NOT trigger compression if total chars <= max_context_chars."""
    compressor = ContextCompressor(settings={})
    # 12 short messages (exceeds default tail_turns*2 + 2 = 8), but total chars is ~200
    messages = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}"}
        for i in range(12)
    ]
    res = await compressor.compress(messages, max_context_chars=5000, tail_turns=3)
    # Should NOT be compressed because total_chars is well within 5000 budget
    assert res == messages


def test_snap_boundary_preserves_tool_pair_integrity():
    """Verify _snap_boundary pulls assistant tool_use into tail when split would land on tool_result."""
    compressor = ContextCompressor(settings={})
    messages = [
        {"role": "user", "content": "Head prompt"},
        {"role": "assistant", "content": "Turn 1"},
        {"role": "user", "content": "Obs 1"},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "t_pair", "name": "get_quote"}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t_pair", "content": "1.0850"}]},
        {"role": "assistant", "content": "Turn 3"},
        {"role": "user", "content": "Obs 3"},
    ]

    # If tail_start landed on index 4 (the tool_result), _snap_boundary shifts back to index 3 (the tool_use)
    snapped_idx = compressor._snap_boundary(messages, split_idx=4)
    assert snapped_idx == 3


@pytest.mark.asyncio
async def test_iterative_summary_chaining():
    """Verify that prior condensed summary in middle messages is retained and chained into new summary."""
    compressor = ContextCompressor(settings={})
    middle_msgs = [
        {
            "role": "user",
            "content": (
                "[CONDENSED CONTEXT SUMMARY — intermediate turns compressed for context budget]\n"
                "• Prior note: Key H4 resistance at 1.0900\n"
                "[END SUMMARY — continue analysis with recent observations below]"
            ),
        },
        {"role": "assistant", "content": "New observation: EURUSD price = 1.0860, RSI = 55.0"},
    ]

    summary = await compressor.summarize_middle(middle_msgs)
    assert "Prior Summary" in summary or "1.0900" in summary
    assert "1.0860" in summary or "RSI" in summary


def test_warm_prefix_preservation():
    from analysis.harness.context_compressor import ContextCompressor

    compressor = ContextCompressor(settings={})
    messages = [
        {"role": "system", "content": "System Identity Invariant"},
        {"role": "user", "content": "Initial User Objective: Trade breakout"},
        {"role": "assistant", "content": "Mid turn 1"},
        {"role": "user", "content": "Mid obs 1"},
        {"role": "assistant", "content": "Mid turn 2"},
        {"role": "user", "content": "Mid obs 2"},
        {"role": "assistant", "content": "Tail turn 1"},
        {"role": "user", "content": "Tail obs 1"},
        {"role": "assistant", "content": "Tail turn 2"},
        {"role": "user", "content": "Tail obs 2"},
    ]

    head, middle, tail = compressor.split_boundaries(messages, tail_turns=2)
    # Both system AND initial user instruction are kept in head
    assert len(head) == 2
    assert head[0]["role"] == "system"
    assert head[1]["role"] == "user"
    assert head[1]["content"] == "Initial User Objective: Trade breakout"
    assert len(middle) > 0


def test_safe_unicode_slice():
    from analysis.harness.context_compressor import safe_unicode_slice

    # Japanese text & currency symbols & emoji
    text = "東京市場 分析 🚀 EURUSD €1.0850 ¥155.20"
    sliced = safe_unicode_slice(text, 10)
    assert len(sliced) <= 10
    # Must be valid utf-8 string without error
    encoded = sliced.encode("utf-8")
    assert isinstance(encoded.decode("utf-8"), str)


def test_offload_historical_charts():
    from analysis.harness.context_compressor import offload_historical_charts

    messages = [
        {"role": "user", "content": "Show chart"},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Here is historical chart"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64," + "A" * 5000}},
            ],
        },
        {"role": "user", "content": "Next step"},
        {"role": "assistant", "content": "Second turn"},
        {"role": "user", "content": "Recent question"},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Recent chart"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,RECENT_IMAGE"}},
            ],
        },
    ]

    offloaded = offload_historical_charts(messages, retain_recent_turns=1)
    # Older assistant turn (turn 1) must have image offloaded
    old_content = offloaded[1]["content"]
    assert any("[CHART/IMAGE OFFLOADED" in b.get("text", "") for b in old_content if isinstance(b, dict))
    assert not any(b.get("type") == "image_url" for b in old_content if isinstance(b, dict))

    # Recent assistant turn (turn 3) must keep image intact
    recent_content = offloaded[5]["content"]
    assert any(b.get("type") == "image_url" for b in recent_content if isinstance(b, dict))


