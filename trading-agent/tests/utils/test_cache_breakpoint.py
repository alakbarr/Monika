import pytest
from utils.llm.cache_breakpoint_manager import CacheBreakpointManager


def test_wrap_system_tiers():
    mgr = CacheBreakpointManager()
    tier1 = "Identity and rules"
    tier2 = "Tool stubs list"
    tier3 = "Skills and lessons"

    blocks = mgr.wrap_system_tiers(tier1, tier2, tier3)
    assert len(blocks) == 2
    assert blocks[0]["text"] == f"{tier1}\n\n{tier2}"
    assert blocks[0]["cache_control"] == {"type": "ephemeral"}
    assert blocks[1]["text"] == tier3
    assert blocks[1]["cache_control"] == {"type": "ephemeral"}


def test_wrap_system_tiers_empty_skips():
    mgr = CacheBreakpointManager()
    blocks = mgr.wrap_system_tiers("Tier1 only", "", "")
    assert len(blocks) == 1
    assert blocks[0]["text"] == "Tier1 only"


def test_apply_to_messages():
    mgr = CacheBreakpointManager()
    messages = [
        {"role": "user", "content": "Turn 1 request"},
        {"role": "assistant", "content": "Turn 1 answer"},
        {"role": "user", "content": "Turn 2 request"},
        {"role": "assistant", "content": "Turn 2 answer"},
    ]

    # Checkpoint on turn -2 (Turn 2 request)
    updated = mgr.apply_to_messages(messages, checkpoint_turn_index=-2)
    assert len(updated) == 4
    # Ensure checkpoint has cache_control
    turn2_user = updated[2]
    assert isinstance(turn2_user["content"], list)
    assert turn2_user["content"][0]["cache_control"] == {"type": "ephemeral"}
