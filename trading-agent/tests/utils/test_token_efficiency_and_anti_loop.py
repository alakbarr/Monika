import json
import pytest
from utils.llm.context_compaction import ContextCompactionEngine
from utils.llm.cache_breakpoint_manager import CacheBreakpointManager


def test_lossless_structural_pruning_ohlcv():
    engine = ContextCompactionEngine()
    bars = []
    # Create 40 synthetic bars with clear swing extremes
    for i in range(40):
        high = 1.1000 + (0.05 if i == 12 else 0.01)  # Peak at bar 12: 1.1500
        low = 1.0500 - (0.05 if i == 25 else 0.01)   # Trough at bar 25: 1.0000
        open_val = 1.0800 if i == 0 else 1.0700
        close_val = 1.0950 if i == 39 else 1.0750
        bars.append({
            "time": f"2026-09-01T{i:02d}:00:00Z",
            "open": open_val,
            "high": high,
            "low": low,
            "close": close_val,
            "volume": 1000
        })

    raw_json = json.dumps(bars)
    pruned_json = engine.micro_prune(raw_json, tool_name="get_price_history")
    result = json.loads(pruned_json)

    # 1. Verify backward compatibility
    assert result["total_bars_available"] == 40
    assert len(result["recent_bars"]) == 10

    # 2. Verify Lossless Structural Extrema preservation across the entire 40-bar series
    extrema = result["period_extrema"]
    assert extrema["high"] == 1.1500
    assert extrema["high_time"] == "2026-09-01T12:00:00Z"
    assert extrema["low"] == 1.0000
    assert extrema["low_time"] == "2026-09-01T25:00:00Z"
    assert extrema["open"] == 1.0800
    assert extrema["close"] == 1.0950
    assert extrema["net_change"] == round(1.0950 - 1.0800, 5)


def test_tool_family_quota_throttling():
    # Calling multiple different tools within the 'price_history' family
    session_history = [
        "get_price_history",
        "get_technical_indicators"
    ]

    # Third call in the same family should be blocked by default quota (max 2)
    allowed, warning = ContextCompactionEngine.check_tool_family_quota(
        tool_name="get_atr",
        session_calls=session_history,
        max_quota=2
    )
    assert allowed is False
    assert "Tool family quota reached" in warning
    assert "price_history" in warning

    # Call to an unrelated family (e.g. sentiment) should be permitted
    allowed_news, _ = ContextCompactionEngine.check_tool_family_quota(
        tool_name="get_news_items",
        session_calls=session_history,
        max_quota=2
    )
    assert allowed_news is True


def test_cache_breakpoint_wrap_classify_json():
    cbm = CacheBreakpointManager()
    sys_prompt = "You are an adjudication verifier."
    tool_schema = {
        "name": "emit_structured_response",
        "input_schema": {"type": "object", "properties": {"decision": {"type": "string"}}}
    }

    sys_blocks, cached_tools = cbm.wrap_classify_json(sys_prompt, tool_schema)

    assert len(sys_blocks) == 1
    assert sys_blocks[0]["type"] == "text"
    assert sys_blocks[0]["text"] == sys_prompt
    assert sys_blocks[0]["cache_control"] == {"type": "ephemeral"}

    assert len(cached_tools) == 1
    assert cached_tools[0]["name"] == "emit_structured_response"
    assert cached_tools[0]["cache_control"] == {"type": "ephemeral"}


def test_cache_breakpoint_apply_to_turn_one():
    cbm = CacheBreakpointManager()
    # Turn 1: single user message containing big pre-fetched bundle
    messages = [{"role": "user", "content": "Huge prefetch data payload..."}]

    cached_messages = cbm.apply_to_messages(messages)
    assert len(cached_messages) == 1
    content = cached_messages[0]["content"]
    assert isinstance(content, list)
    assert content[0]["cache_control"] == {"type": "ephemeral"}
    assert "Huge prefetch" in content[0]["text"]


def test_cache_breakpoint_wrap_classify_json_padded_anchor():
    cbm = CacheBreakpointManager()
    sys_prompt = "Short verifier prompt"
    tool_schema = {"name": "emit_structured_response", "input_schema": {"type": "object"}}

    sys_blocks, cached_tools = cbm.wrap_classify_json(sys_prompt, tool_schema, pad_to_cache_threshold=True)
    assert len(sys_blocks) == 1
    assert len(sys_blocks[0]["text"]) >= cbm.MIN_CACHEABLE_CHARS
    assert "CANONICAL SYSTEM GOVERNANCE" in sys_blocks[0]["text"]
    assert sys_prompt in sys_blocks[0]["text"]
    assert sys_blocks[0]["cache_control"] == {"type": "ephemeral"}


def test_truncate_to_budget_embedded_json_preservation():
    import json
    from utils.llm.prompt_compressor import truncate_to_budget
    raw_payload = {
        "symbol": "EURUSD",
        "current_price": 1.0855,
        "atr_14": 0.0045,
        "stop_loss": 1.0810,
        "take_profit": 1.0950,
        "order_blocks": [{"price_high": 1.0890, "price_low": 1.0870}],
        "unimportant_logs": ["log line " + str(i) for i in range(100)]
    }
    wrapped_text = f"Please perform per-asset analysis for EURUSD:\n[PRE-FETCHED DATA]\n{json.dumps(raw_payload)}"
    truncated = truncate_to_budget(wrapped_text, max_tokens=150)
    assert "EURUSD" in truncated
    assert "atr_14" in truncated
    assert "stop_loss" in truncated
    assert "take_profit" in truncated
    assert "order_blocks" in truncated


def test_extract_decisive_state_extended_coverage():
    import json
    from utils.llm.context_compaction import ContextCompactionEngine
    engine = ContextCompactionEngine()

    # Optimal levels
    levels_data = json.dumps({"optimal_entry": 1.0850, "optimal_sl": 1.0810, "optimal_tp": 1.0930, "rr_ratio": 2.0})
    res_levels = engine._extract_decisive_state("get_optimal_intraday_levels", levels_data)
    assert "optimal_entry=1.085" in res_levels
    assert "rr_ratio=2.0" in res_levels

    # Sweep
    sweep_data = json.dumps({"sweep_detected": True, "direction": "bullish", "price": 1.0820})
    res_sweep = engine._extract_decisive_state("detect_liquidity_sweep", sweep_data)
    assert "sweep=bullish@1.082" in res_sweep

    # COT
    cot_data = json.dumps({"net_position": 45000, "commercial_bias": "bullish", "long_pct": 68.5})
    res_cot = engine._extract_decisive_state("get_cot_report", cot_data)
    assert "cot_net=45000" in res_cot
    assert "cot_bias=bullish" in res_cot

