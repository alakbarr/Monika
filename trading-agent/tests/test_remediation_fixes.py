import pytest
from unittest.mock import AsyncMock, MagicMock
from graph.nodes.reflection_node import reflection_node
from analysis.providers.openai_provider import OpenAIProvider
from scheduler.edge_strategy_runner import EdgeStrategyRunner
from analysis.strategies.base_strategy import EdgeSignal

@pytest.mark.asyncio
async def test_reflection_node_contradiction_filtering():
    """Verify reflection node filters cross-pair contradictions with USD_STRONG recommendation."""
    state = {
        "actionable_trades": [
            ("EURUSD", {"decision": "buy", "confidence": 0.85}),   # Contradicts USD strong (short USD)
            ("USDJPY", {"decision": "buy", "confidence": 0.90}),   # Long USD
            ("GBPUSD", {"decision": "sell", "confidence": 0.80}),  # Long USD
        ],
        "summary": {},
        "vix_level": 18.0
    }
    
    mock_scheduler = MagicMock()
    config = {"configurable": {"scheduler": mock_scheduler}}
    
    # Run reflection node
    res = await reflection_node(state, config=config)
    
    # EURUSD buy should be filtered out by correlation/contradiction logic
    approved = res.get("approved_trades", [])
    remaining_symbols = [sym for sym, _ in approved]
    assert "EURUSD" not in remaining_symbols
    assert len(remaining_symbols) <= 2


def test_openai_provider_role_and_message_normalization():
    """Verify OpenAIProvider initializes role properly and normalizes Anthropic-style messages."""
    provider = OpenAIProvider(model="gpt-4o-mini", role="stage2_test")
    assert provider.role == "stage2_test"
    
    # Test normalization of Anthropic block structure
    anthropic_msgs = [
        {"role": "user", "content": "Analyze"},
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "call_123", "name": "get_dxy", "input": {}}
            ]
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "call_123", "name": "get_dxy", "content": {"dxy": 104.2}}
            ]
        }
    ]
    
    norm = provider._normalize_messages(anthropic_msgs)
    assert len(norm) == 3
    assert norm[1]["role"] == "assistant"
    assert norm[1]["tool_calls"][0]["function"]["name"] == "get_dxy"
    assert norm[2]["role"] == "tool"
    assert norm[2]["tool_call_id"] == "call_123"


def test_edge_strategy_runner_imports_edgesignal():
    """Verify EdgeStrategyRunner can reference EdgeSignal cleanly."""
    runner = EdgeStrategyRunner({})
    sig = EdgeSignal(
        strategy_id="gap_fade",
        symbol="EURUSD",
        valid=True,
        direction="buy",
        confidence=0.8,
        entry_price=1.0850,
        stop_loss=1.0800,
        take_profit=1.0950
    )
    assert sig.symbol == "EURUSD"
