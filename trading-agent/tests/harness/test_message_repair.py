"""
Unit tests for 4-pass message history alternation and pairing repair.
"""

from analysis.harness.message_repair import repair_message_history


def test_merge_consecutive_assistants():
    messages = [
        {"role": "user", "content": "Analyze XAUUSD"},
        {"role": "assistant", "content": "Checking market structure."},
        {"role": "assistant", "content": "Structure is bullish on H4."},
    ]
    repaired = repair_message_history(messages)
    assert len(repaired) == 2
    assert repaired[0]["role"] == "user"
    assert repaired[1]["role"] == "assistant"
    assert "Checking market structure." in repaired[1]["content"]
    assert "Structure is bullish on H4." in repaired[1]["content"]


def test_drop_orphaned_tool_results():
    messages = [
        {"role": "user", "content": "Analyze"},
        {"role": "assistant", "content": "Calling tool", "tool_calls": [{"id": "call_123", "name": "get_quote"}]},
        {"role": "tool", "tool_call_id": "call_123", "content": "{'price': 2650.0}"},
        {"role": "tool", "tool_call_id": "call_999_orphaned", "content": "Stray result"},
    ]
    repaired = repair_message_history(messages)
    # The stray result call_999_orphaned must be discarded
    tool_msgs = [m for m in repaired if m.get("role") == "tool"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0]["tool_call_id"] == "call_123"


def test_prune_unanswered_tool_calls():
    messages = [
        {"role": "user", "content": "Analyze"},
        {
            "role": "assistant",
            "content": "Calling two tools",
            "tool_calls": [
                {"id": "call_answered", "name": "get_quote"},
                {"id": "call_unanswered", "name": "get_atr"},
            ],
        },
        {"role": "tool", "tool_call_id": "call_answered", "content": "ok"},
    ]
    repaired = repair_message_history(messages)
    asst = [m for m in repaired if m.get("role") == "assistant"][0]
    assert len(asst["tool_calls"]) == 1
    assert asst["tool_calls"][0]["id"] == "call_answered"
