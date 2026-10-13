"""
Unit test verifying StateGraph memory optimization and fail-closed safety alignment (Fase 3).
"""

import pytest
from unittest.mock import patch, AsyncMock
from monika.application.graph.nodes.state_pruner import (
    prune_after_fundamental,
    prune_after_debate,
    _cap_archived_payloads,
    MAX_ARCHIVED_PAYLOAD_ENTRIES,
)
from monika.application.graph.reactive_graph import fast_debate_node


def test_state_pruner_ring_buffer_cap():
    """Verify archived_payloads does not grow unboundedly across turns."""
    # Test helper directly
    oversized = {f"key_{i}": f"value_{i}" for i in range(100)}
    capped = _cap_archived_payloads(dict(oversized), max_entries=50)
    assert len(capped) == 50
    # FIFO check: older keys (0..49) are evicted, newer keys (50..99) remain
    assert "key_0" not in capped
    assert "key_99" in capped

    # Test prune_after_fundamental preserves ring-buffer cap
    initial_archived = {f"old_turn_{i}": f"data_{i}" for i in range(MAX_ARCHIVED_PAYLOAD_ENTRIES)}
    state = {
        "summary": {
            "fundamental": {
                "brief": "Macro context",
                "raw_conversation": "large dialogue payload",
            }
        },
        "archived_payloads": initial_archived,
    }
    pruned = prune_after_fundamental(state)
    archived = pruned["archived_payloads"]
    assert len(archived) <= MAX_ARCHIVED_PAYLOAD_ENTRIES
    assert "fundamental.raw_conversation" in archived


@pytest.mark.asyncio
async def test_reactive_debate_node_fails_closed_on_error():
    """Verify reactive_debate_node drops actionable trades if debate subgraph raises an exception."""
    mock_trade = {"symbol": "EURUSD", "direction": "buy", "confidence": 0.8}
    state = {
        "actionable_trades": [mock_trade],
        "symbols": ["EURUSD"],
    }
    config = {"configurable": {"settings": {"trading": {"enable_debate": True}}}}

    # Simulate debate subgraph raising an unhandled exception
    with patch("graph.nodes.debate.subgraph.build_debate_subgraph") as mock_build:
        mock_sub = AsyncMock()
        mock_sub.ainvoke.side_effect = RuntimeError("Simulated LLM API failure in debate subgraph")
        mock_build.return_value = mock_sub

        res = await fast_debate_node(state, config=config)

        # Must fail-closed: actionable_trades must be empty!
        assert res.get("actionable_trades") == []
        assert "Debate subgraph failure" in res.get("error", "")
