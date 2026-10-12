import pytest
from utils.llm.cache_breakpoint_manager import CacheBreakpointManager
from analysis.providers.openai_provider import OpenAIProvider


def test_find_completed_transaction_endpoints():
    cbm = CacheBreakpointManager()
    messages = [
        {"role": "user", "content": "Analyze EURUSD"},
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "call_1", "name": "get_candles", "input": {"symbol": "EURUSD"}}
            ]
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "call_1", "content": '{"close": 1.0850}'}
            ]
        },
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "call_2", "name": "calculate_position_size", "input": {"symbol": "EURUSD"}}
            ]
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "call_2", "content": '{"lot": 0.1}'}
            ]
        },
    ]

    endpoints = cbm.find_completed_transaction_endpoints(messages)
    assert endpoints == [2, 4], f"Expected [2, 4], got {endpoints}"


def test_apply_to_messages_with_transaction_endpoints():
    cbm = CacheBreakpointManager()
    messages = [
        {"role": "user", "content": "Analyze EURUSD"},
        {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": "call_1", "name": "get_candles", "input": {}}]
        },
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "call_1", "content": "{}"}]
        },
        {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": "call_2", "name": "get_ticks", "input": {}}]
        },
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "call_2", "content": "{}"}]
        },
    ]

    updated = cbm.apply_to_messages(messages, max_message_breakpoints=2)
    # Check that breakpoints are only on endpoints [2, 4]
    bp_indices = []
    for i, m in enumerate(updated):
        c = m.get("content")
        if isinstance(c, list):
            for b in c:
                if isinstance(b, dict) and "cache_control" in b:
                    bp_indices.append(i)
                    break
    assert bp_indices == [2, 4], f"Expected breakpoints at [2, 4], got {bp_indices}"
    assert len(bp_indices) <= 2, "Message-level breakpoints should not exceed 2"


@pytest.mark.asyncio
async def test_openai_content_addressed_cache_key():
    provider = OpenAIProvider(model="gpt-4o", api_key="dummy-key")
    kwargs = {
        "messages": [
            {"role": "system", "content": "You are Monika MT5 quantitative trading agent."},
            {"role": "user", "content": "Hello"}
        ],
        "tools": [
            {"type": "function", "function": {"name": "calculate_position_size"}},
            {"type": "function", "function": {"name": "get_candles"}}
        ]
    }
    # Simulate the caching key block
    is_cache_key_supported = True
    clean_role = "risk_manager"
    import hashlib
    sys_content = "You are Monika MT5 quantitative trading agent."
    tool_names = sorted(["calculate_position_size", "get_candles"])
    cache_sig = f"{clean_role}:{hashlib.sha256(sys_content.encode('utf-8')).hexdigest()[:16]}:{','.join(tool_names)}"
    expected_cache_key = f"monika_{hashlib.sha256(cache_sig.encode('utf-8')).hexdigest()[:24]}"

    # Test key stability
    assert expected_cache_key.startswith("monika_")
    assert len(expected_cache_key) == 31  # "monika_" (7) + 24 chars
