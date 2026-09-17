import pytest
from analysis.schemas.pydantic_schemas import (
    SubmitAssetAnalysisSchema,
    FundamentalBriefSchema,
    make_openai_strict_schema
)
from utils.llm.cache_breakpoint_manager import CacheBreakpointManager
from utils.llm.context_compaction import ContextCompactionEngine
from utils.llm.adaptive_thinking import PerSymbolAdaptiveThinkingAllocator


def test_make_openai_strict_schema_submit_asset():
    """Verify SubmitAssetAnalysisSchema strict transformation."""
    raw_schema = SubmitAssetAnalysisSchema.model_json_schema()
    strict_schema = make_openai_strict_schema(raw_schema)
    
    # 1. Root object must have additionalProperties: False
    assert strict_schema.get("additionalProperties") is False
    
    # 2. All properties must be in required
    props = strict_schema.get("properties", {})
    req = set(strict_schema.get("required", []))
    assert set(props.keys()) == req
    assert len(req) == 18
    
    # 3. Optional fields must have null in anyOf
    sl_prop = props.get("stop_loss", {})
    assert "anyOf" in sl_prop
    assert any(item.get("type") == "null" for item in sl_prop["anyOf"])
    
    # 4. Nested defs must also have additionalProperties: False
    defs = strict_schema.get("$defs", {})
    for def_name, def_obj in defs.items():
        if def_obj.get("type") == "object":
            assert def_obj.get("additionalProperties") is False
            def_props = def_obj.get("properties", {})
            assert set(def_props.keys()) == set(def_obj.get("required", []))


def test_make_openai_strict_schema_fundamental():
    """Verify FundamentalBriefSchema strict transformation."""
    raw_schema = FundamentalBriefSchema.model_json_schema()
    strict_schema = make_openai_strict_schema(raw_schema)
    
    assert strict_schema.get("additionalProperties") is False
    props = strict_schema.get("properties", {})
    req = set(strict_schema.get("required", []))
    assert set(props.keys()) == req
    assert len(req) == 14


def test_sliding_cache_breakpoint_turn_n_minus_2():
    """Verify sliding cache breakpoint strips old breakpoints and anchors Turn N-2."""
    cbm = CacheBreakpointManager()
    
    messages = [
        {"role": "user", "content": "Initial macro context prompt"},
        {"role": "assistant", "content": "Tool call get_price_history"},
        {"role": "user", "content": [{"type": "tool_result", "content": "bars...", "cache_control": {"type": "ephemeral"}}]},
        {"role": "assistant", "content": "Tool call get_indicators"},
        {"role": "user", "content": [{"type": "tool_result", "content": "indicators..."}]},
    ]
    
    # Apply sliding breakpoint
    updated = cbm.apply_to_messages(messages, checkpoint_turn_index=-2)
    
    # Count total cache_controls in updated messages (must be strictly 1)
    total_cc = 0
    cc_indices = []
    for idx, m in enumerate(updated):
        c = m.get("content")
        if isinstance(c, list):
            for b in c:
                if isinstance(b, dict) and "cache_control" in b:
                    total_cc += 1
                    cc_indices.append(idx)
        elif isinstance(c, str):
            pass
            
    assert total_cc == 1
    # Checkpoint should be at index len - 2 = 3 (the second to last message)
    assert cc_indices == [3]


def test_per_symbol_adaptive_thinking_budget():
    """Verify adaptive thinking allocator assigns higher budget to volatile assets."""
    btc_budget = PerSymbolAdaptiveThinkingAllocator.compute_symbol_budget(
        "BTCUSD", context={"vix": 22.0, "confluence_score": 7}
    )
    eur_budget = PerSymbolAdaptiveThinkingAllocator.compute_symbol_budget(
        "EURUSD", context={"vix": 16.0, "confluence_score": 9}
    )
    
    # BTC should receive significantly more thinking tokens than EUR
    assert btc_budget > eur_budget
    assert btc_budget >= 4000
    assert eur_budget <= 4096


def test_per_symbol_adaptive_thinking_levels():
    """Verify standardized thinking levels mapping."""
    crisis_level = PerSymbolAdaptiveThinkingAllocator.get_thinking_level(
        "XAUUSD", context={"vix": 32.0, "regime": "CRISIS"}
    )
    calm_level = PerSymbolAdaptiveThinkingAllocator.get_thinking_level(
        "EURUSD", context={"vix": 14.0, "confluence_score": 9}
    )
    
    assert crisis_level in ("high", "max", "medium")
    assert calm_level in ("minimal", "low")


@pytest.mark.asyncio
async def test_context_compaction_offload():
    """Verify compact_with_summary_model passes through if below threshold."""
    engine = ContextCompactionEngine()
    messages = [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "user request"},
        {"role": "assistant", "content": "response"}
    ]
    
    result = await engine.compact_with_summary_model(messages, context_window=128000)
    assert len(result) == 3
