import pytest
import json
from utils.llm.context_compaction import ContextCompactionEngine


def test_micro_prune_order():
    engine = ContextCompactionEngine()
    raw_order = json.dumps({
        "ticket": 123456,
        "symbol": "EURUSD",
        "price_open": 1.0850,
        "sl": 1.0820,
        "tp": 1.0920,
        "volume": 0.5,
        "status": "OPEN",
        "internal_comment_debug_blob": "large debug data " * 50
    })
    pruned = engine.micro_prune(raw_order, tool_name="get_open_positions")
    data = json.loads(pruned)
    assert data["ticket"] == 123456
    assert data["symbol"] == "EURUSD"
    assert "internal_comment_debug_blob" not in data


def test_micro_prune_ohlcv():
    engine = ContextCompactionEngine()
    bars = [{"time": i, "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.05, "volume": 100} for i in range(30)]
    raw_ohlcv = json.dumps(bars)
    pruned = engine.micro_prune(raw_ohlcv, tool_name="get_price_history")
    data = json.loads(pruned)
    assert data["total_bars_available"] == 30
    assert len(data["recent_bars"]) == 10


def test_emergency_guard_compaction():
    engine = ContextCompactionEngine()
    # 10 turns of messages
    messages = [{"role": "system", "content": "You are a trading agent."}]
    messages.append({"role": "user", "content": "Initial task: Analyze EURUSD"})
    for i in range(8):
        messages.append({"role": "tool", "content": f"Intermediate tool output turn {i} with data " * 50})
        messages.append({"role": "assistant", "content": f"Thought turn {i}"})
    messages.append({"role": "user", "content": "Final turn request"})

    compacted = engine.emergency_guard(messages, context_window=1000)
    # Must preserve system prompt + first user task + summary note + last 3 non-system turns
    assert len(compacted) < len(messages)
    assert compacted[0]["role"] == "system"
    assert "Initial task" in compacted[1]["content"]
    assert "SYSTEM NOTE" in compacted[2]["content"]


def test_mask_aged_observations_openai():
    engine = ContextCompactionEngine()
    messages = [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "User prompt"},
        {"role": "assistant", "content": "call 1"},
        {"role": "tool", "name": "get_price_history", "content": "large ohlcv table " * 100},
        {"role": "assistant", "content": "call 2"},
        {"role": "tool", "name": "get_atr", "content": "large atr series " * 100},
        {"role": "assistant", "content": "recent call"},
        {"role": "tool", "name": "get_spread_snapshot", "content": "recent data"},
        {"role": "assistant", "content": "finalizing"},
    ]
    masked = engine.mask_aged_observations(messages, keep_recent_turns=1)
    # Turn older than keep_recent_turns should be masked
    assert "Observation:" in masked[3]["content"]
    assert "Observation:" in masked[5]["content"]
    # Recent turn should remain untouched
    assert masked[7]["content"] == "recent data"


def test_mask_aged_observations_gemini_anthropic():
    engine = ContextCompactionEngine()
    messages = [
        {"role": "user", "content": "Start task"},
        {"role": "assistant", "content": [{"type": "tool_use", "name": "get_indicators", "id": "call_1"}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "call_1", "content": "huge indicator data " * 80}]},
        {"role": "assistant", "content": [{"type": "tool_use", "name": "get_atr", "id": "call_2"}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "call_2", "content": "huge atr data " * 80}]},
        {"role": "assistant", "content": [{"type": "tool_use", "name": "submit_asset_analysis", "id": "call_3"}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "call_3", "content": "decision: buy, stop_loss: 1.05"}]},
    ]
    masked = engine.mask_aged_observations(messages, keep_recent_turns=1)
    # call_1 in turn 1 should be masked
    assert "Prior tool output observed" in masked[2]["content"][0]["content"]
    # Protected/recent trade decision in turn 3 must NOT be masked
    assert "stop_loss: 1.05" in masked[6]["content"][0]["content"]


def test_mask_aged_observations_state_preserving_and_alias():
    engine = ContextCompactionEngine()
    messages = [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "User prompt"},
        {"role": "assistant", "content": "calling adr"},
        {"role": "tool", "name": "get_daily_range_context", "content": json.dumps({"adr": 0.0065, "target_tp_min_distance": 0.0032, "target_tp_max_distance": 0.0052, "target_sl_max_distance": 0.0022, "padding": "x" * 250})},
        {"role": "assistant", "content": "calling atr"},
        {"role": "tool", "name": "get_atr", "content": json.dumps({"atr_14": 0.0045, "padding": "y" * 250})},
        {"role": "assistant", "content": "calling submit"},
        {"role": "tool", "name": "submit_asset_analysis", "content": json.dumps({"decision": "buy", "stop_loss": 1.05})},
    ]
    # Test using turns_to_keep alias
    masked = engine.mask_aged_observations(messages, turns_to_keep=1)
    # Turn 1 tool result should preserve ADR values
    assert "adr=0.0065" in masked[3]["content"].lower()
    assert "target_tp_min_distance=0.0032" in masked[3]["content"]
    # Turn 2 tool result should preserve ATR value
    assert "atr_14=0.0045" in masked[5]["content"].lower()
    # submit_asset_analysis must remain completely untouched
    assert "stop_loss" in masked[7]["content"]


def test_mask_aged_observations_technical_and_smc_retention():
    engine = ContextCompactionEngine()
    messages = [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "User prompt"},
        {"role": "assistant", "content": "calling tech indicators"},
        {
            "role": "tool",
            "name": "get_technical_indicators",
            "content": json.dumps({
                "indicators": {"rsi_14": 48.5, "ema_20": 1.0820, "ema_200": 1.0750, "adx_14": 26.2},
                "padding": "z" * 300
            })
        },
        {"role": "assistant", "content": "calling smc"},
        {
            "role": "tool",
            "name": "get_smc_zones",
            "content": json.dumps({
                "order_blocks": [{"price_low": 1.0800, "price_high": 1.0825}],
                "fvg_zones": [{"top": 1.0850, "bottom": 1.0840}],
                "padding": "w" * 300
            })
        },
        {"role": "assistant", "content": "calling breaks"},
        {
            "role": "tool",
            "name": "get_structure_breaks",
            "content": json.dumps({
                "breaks": [{"type": "BOS_BULLISH", "level": 1.0835}],
                "padding": "v" * 300
            })
        },
        {"role": "assistant", "content": "calling submit"},
        {
            "role": "tool",
            "name": "submit_asset_analysis",
            "content": json.dumps({"decision": "buy", "stop_loss": 1.0790})
        },
    ]
    masked = engine.mask_aged_observations(messages, keep_recent_turns=1)
    # Turn 1: Indicators must retain RSI & EMAs
    assert "rsi_14=48.5" in masked[3]["content"]
    assert "ema_20=1.082" in masked[3]["content"]
    assert "ema_200=1.075" in masked[3]["content"]
    # Turn 2: SMC must retain OB & FVG counts/levels
    assert "unmitigated_obs=1" in masked[5]["content"].lower()
    assert "nearest_ob=[1.08-1.0825]" in masked[5]["content"].lower()
    # Turn 3: Structure breaks must retain last_break
    assert "last_break=bos_bullish@1.0835" in masked[7]["content"].lower()
    # Recent submit must be untouched
    assert "stop_loss" in masked[9]["content"]


def test_check_and_compact_intermediate_threshold():
    """Verify check_and_compact triggers mask_aged_observations when tokens > 10,000 and len(messages) > 4."""
    engine = ContextCompactionEngine()
    messages = [
        {"role": "system", "content": "You are a trading agent."},
        {"role": "user", "content": "Analyze USDJPY."},
        {"role": "assistant", "content": "Let me fetch price history."},
        {"role": "tool", "name": "get_price_history", "content": "OHLCV data string with lots of bars " * 1500},
        {"role": "assistant", "content": "Now checking spread."},
        {"role": "tool", "name": "get_spread_snapshot", "content": "current spread 0.8 pips"},
    ]
    tokens = engine.calculate_history_tokens(messages)
    assert tokens > 10000
    assert len(messages) > 4

    compacted = engine.check_and_compact(messages, context_window=200000)
    # Price history should have been masked into an observation summary
    assert "Observation:" in compacted[3]["content"]
    # Recent tool output (turn 2) remains untouched
    assert compacted[5]["content"] == "current spread 0.8 pips"


