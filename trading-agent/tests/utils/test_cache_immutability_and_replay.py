import pytest
from utils.llm.context_compaction import ContextCompactionEngine
from utils.llm.prompt_tiers import TieredSystemPrompt
from utils.llm.prompt_assembler import PromptAssembler


def test_snap_tool_boundary():
    compactor = ContextCompactionEngine({})
    
    # Message sequence where an assistant invokes a tool and tool returns result
    messages = [
        {"role": "user", "content": "Analyze market"},
        {"role": "assistant", "content": "Checking indicators", "tool_calls": [{"id": "c1", "function": {"name": "get_indicators"}}]},
        {"role": "tool", "name": "get_indicators", "tool_call_id": "c1", "content": '{"rsi": 55}'},
        {"role": "assistant", "content": "Checking candles", "tool_calls": [{"id": "c2", "function": {"name": "get_candles"}}]},
        {"role": "tool", "name": "get_candles", "tool_call_id": "c2", "content": '{"close": 1.085}'},
        {"role": "assistant", "content": "Analysis complete: Bullish."},
    ]
    
    # If cut lands exactly on index 2 (which is role="tool"), it should snap forward to 3
    snapped = compactor._snap_tool_boundary(messages, target_idx=2, min_idx=1, max_idx=len(messages) - 1)
    # Cut point at 3 starts at assistant with c2
    assert snapped == 3
    assert messages[snapped]["role"] != "tool"


def test_emergency_compact_canonical_tags():
    compactor = ContextCompactionEngine({})
    
    # Build 10 turns
    messages = [{"role": "user", "content": "Initial Prompt: EURUSD analysis"}]
    for i in range(10):
        messages.append({"role": "assistant", "content": f"Turn {i} step ATR_14: 0.0045 Close: 1.0850"})
        messages.append({"role": "user", "content": f"Proceed step {i}"})
        
    compacted = compactor.emergency_compact(messages, target_reduction=0.50)
    
    # Verify canonical tag is used
    bridge = compacted[1]
    assert bridge["role"] == "user"
    assert "<compacted-summary>" in bridge["content"]
    assert "</compacted-summary>" in bridge["content"]
    assert "ATR_14: 0.0045" in bridge["content"]


def test_tiered_system_prompt_quarantine():
    tp = TieredSystemPrompt(
        tier1_stable="Stable Identity and Rules",
        tier2_context="Tool Stubs and Schemas",
        tier3_volatile="Volatile Clock: 2026-09-21T19:30:00Z"
    )
    
    # Default without quarantine includes volatile
    full = tp.assemble(provider="default", quarantine_volatile=False)
    assert "Volatile Clock" in full
    
    # With quarantine, volatile is cleanly removed from system prompt
    quarantined = tp.assemble(provider="default", quarantine_volatile=True)
    assert "Volatile Clock" not in quarantined
    assert "Stable Identity and Rules" in quarantined
    assert "Tool Stubs and Schemas" in quarantined
    
    # compile_stable_system gives identical clean prefix
    stable = tp.compile_stable_system()
    assert stable == quarantined


def test_build_target_user_message():
    msg = PromptAssembler.build_target_user_message(
        symbol="EURUSD",
        cot_code="099741",
        effective_threshold=8,
        min_rr_ratio=1.5
    )
    assert "[ANALYSIS TARGET]" in msg
    assert "Symbol: EURUSD" in msg
    assert "COT Code: 099741" in msg
    assert "Effective Confluence Threshold: 8/14" in msg
    assert "Minimum R:R Ratio: 1.5" in msg
    assert "[END TARGET]" in msg
