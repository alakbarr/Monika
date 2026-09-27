"""
Unit tests for Token Efficiency Architectural Optimizations:
1. Dead Compaction Threshold Fixes (ContextCompactionEngine)
2. Tool Minification (minify_tool_definitions)
3. Rule Invariant Consolidation & Conditional Anchor Injection (CacheBreakpointManager & PromptAssembler)
4. Intelligent Thinking Budget Allocation (AdaptiveThinking & QuantizedThinkingAllocator)
5. Initial Bundle Distillation (ContextCompressor.distill_initial_bundle_after_turn_1)
6. Multi-Persona Risk Evaluation Batching (analyze_risk_multi_persona_llm)
7. S2-MAD Sparse Debate Blackboard (DebateBlackboard)
8. Retrieval-Augmented Tool Selection (RAToolSelector)
9. Semantic Caching with Financial Guardrails (TradingSemanticCache)
10. Adaptive LLMLingua-2 Hardware Detection (AdaptiveLLMLinguaCompressor)
"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock

# 1. Compaction Threshold Tests
def test_compaction_thresholds():
    from utils.llm.context_compaction import ContextCompactionEngine
    engine = ContextCompactionEngine()
    assert hasattr(engine, "SYNTHESIS_THRESHOLD_ABSOLUTE")
    assert hasattr(engine, "EMERGENCY_THRESHOLD_ABSOLUTE")
    assert engine.SYNTHESIS_THRESHOLD_ABSOLUTE == 28000
    assert engine.EMERGENCY_THRESHOLD_ABSOLUTE == 45000

    # Short conversation should remain intact
    msgs = [{"role": "user", "content": "hello"}]
    res = engine.check_and_compact(msgs, context_window=1000000)
    assert len(res) == 1

# 2. Tool Minification Tests
def test_minify_tool_definitions():
    from analysis.tools.tools_definitions import minify_tool_definitions
    raw_tools = [{
        "name": "test_tool",
        "description": "This is a very long descriptive sentence that explains everything about how this tool functions in exhaustive detail. And another sentence.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "The exact financial instrument symbol such as EURUSD or BTCUSD to analyze in detail."}
            }
        }
    }]
    minified = minify_tool_definitions(raw_tools)
    assert len(minified) == 1
    assert "And another sentence" not in minified[0]["description"]
    assert minified[0]["description"].endswith(".")

# 3. Conditional Anchor Injection Tests
def test_should_inject_anchor():
    from utils.llm.cache_breakpoint_manager import CacheBreakpointManager
    # Ollama/local should never inject anchor
    assert not CacheBreakpointManager.should_inject_anchor(model_name="llama3", provider_name="ollama", current_prompt_chars=500)
    assert not CacheBreakpointManager.should_inject_anchor(model_name="qwen", provider_name="groq", current_prompt_chars=500)
    
    # Prompt already exceeding threshold should not inject anchor
    assert not CacheBreakpointManager.should_inject_anchor(model_name="gemini-3-flash", provider_name="gemini", current_prompt_chars=25000)

# 4. Adaptive Thinking Cap Tests
def test_adaptive_thinking_caps():
    from utils.llm.adaptive_thinking import QuantizedThinkingAllocator, PerSymbolAdaptiveThinkingAllocator
    assert QuantizedThinkingAllocator.BUCKETS["MAX"] == 16000
    assert QuantizedThinkingAllocator.quantize(16000) == 16000

    # Low confluence exit test
    budget_low_conf = PerSymbolAdaptiveThinkingAllocator.compute_symbol_budget(
        symbol="EURUSD",
        context={"confluence_score": 3.0, "vix": 15.0}
    )
    assert budget_low_conf <= 4096

# 5. Initial Bundle Distillation Tests
def test_distill_initial_bundle_after_turn_1():
    from analysis.harness.context_compressor import ContextCompressor
    messages = [
        {"role": "user", "content": "Analyze XAUUSD.\n\n[PRE-FETCHED DATA]\n" + ("candle_row_data\n" * 500) + "regime: volatile\natr: 15.2"},
        {"role": "assistant", "content": "I will inspect XAUUSD."},
        {"role": "user", "content": "Tool observation"}
    ]
    distilled = ContextCompressor.distill_initial_bundle_after_turn_1(messages)
    assert "[PRE-FETCHED DATA DISTILLED]" in distilled[0]["content"]
    assert len(distilled[0]["content"]) < len(messages[0]["content"])

# 6. S2-MAD Debate Blackboard Tests
def test_debate_blackboard():
    from analysis.debate.blackboard import DebateBlackboard
    bb = DebateBlackboard(symbol="XAUUSD")
    bb.add_bull_thesis("Gold breaking out above 2650 resistance with strong volume.", key_levels=[2650.0], confidence=0.8)
    bb.add_bear_thesis("Gold facing massive liquidity pool rejection at 2650.", key_levels=[2650.0], confidence=0.7)
    
    contradictions = bb.extract_sparse_contradictions()
    assert len(contradictions) >= 1
    summary = bb.render_sparse_summary()
    assert "S²-MAD SPARSE DEBATE BLACKBOARD" in summary
    assert "2650" in summary

# 7. Retrieval-Augmented Tool Selection (RATS) Tests
def test_rat_tool_selector():
    from analysis.tools.tool_selector import RAToolSelector
    tools = [
        {"name": "calculate_position_size", "description": "Calculates lot size."},
        {"name": "submit_asset_analysis", "description": "Submits final decision."},
        {"name": "get_funding_rate", "description": "Fetches crypto perpetual funding rate."},
        {"name": "get_technical_indicators", "description": "Calculates RSI, MACD, EMA."},
        {"name": "get_forex_sentiment", "description": "Fetches retail forex sentiment."},
    ]
    selector = RAToolSelector(tools)
    selected = selector.select_tools(context_text="Analyze technical RSI for EURUSD", symbol="EURUSD", top_k=3)
    names = {t["name"] for t in selected}
    assert "calculate_position_size" in names
    assert "submit_asset_analysis" in names
    # Crypto tool should be pruned for forex symbol
    assert "get_funding_rate" not in names

# 8. Semantic Cache Guardrail Tests
def test_semantic_cache_guardrails():
    from utils.llm.semantic_cache import TradingSemanticCache
    cache = TradingSemanticCache.get_instance()
    
    # Execution tools must be blocked
    cache.set("execute_order_guard", "query", {"status": "executed"})
    assert cache.get("execute_order_guard", "query") is None

    # Macro explanations are allowed
    cache.set("macro_explanation", "what is NFP?", "Non-Farm Payrolls is a US employment indicator.")
    cached = cache.get("macro_explanation", "what is NFP?")
    assert cached is not None
    assert "Non-Farm Payrolls" in cached

# 9. Adaptive LLMLingua-2 Device Detection Tests
def test_llmlingua_device_and_heuristic():
    from utils.llm.llmlingua_compressor import AdaptiveLLMLinguaCompressor
    device = AdaptiveLLMLinguaCompressor.detect_device()
    assert device in ("cuda", "cpu")

    compressor = AdaptiveLLMLinguaCompressor.get_instance()
    text = (
        "Good morning everyone. As we have discussed in the previous meeting, "
        "the inflation rate increased to 3.2% while CPI core remained elevated at 2.8%. "
        "Federal Reserve FOMC minutes indicated interest rate cuts may be delayed. "
        "Thank you very much for your kind attention."
    )
    res = compressor.compress_text(text, rate=0.6)
    assert len(res) <= len(text)
    assert "3.2%" in res
    assert "FOMC" in res

# 10. OpenRouter Claude Cache Control Passthrough Tests
def test_openrouter_claude_cache_control():
    from analysis.providers.openai_provider import OpenAIProvider
    provider = OpenAIProvider(model="anthropic/claude-3.5-sonnet", api_key="sk-or-test")
    provider.provider_name = "openrouter"

    tools = [
        {"name": "tool_a", "description": "tool a", "input_schema": {"type": "object", "properties": {}}},
        {"name": "tool_b", "description": "tool b", "input_schema": {"type": "object", "properties": {}}},
    ]
    converted = provider._convert_tools(tools)
    assert len(converted) == 2
    # Last tool must have ephemeral cache_control
    assert "cache_control" not in converted[0]
    assert converted[1].get("cache_control") == {"type": "ephemeral"}

# 11. OpenRouter Provider Sticky Routing Tests
def test_openrouter_sticky_routing():
    from analysis.providers.openrouter_provider import OpenRouterProvider
    provider = OpenRouterProvider(model="deepseek/deepseek-chat", api_key="sk-or-test")
    kwargs = {}
    provider._apply_provider_routing(kwargs)

    assert "extra_body" in kwargs
    assert kwargs["extra_body"]["provider"]["allow_fallbacks"] is True
    assert "extra_headers" in kwargs
    assert "X-Session-ID" in kwargs["extra_headers"]

# 12. Ollama Keep-Alive Tests
def test_ollama_keep_alive():
    from analysis.providers.ollama_provider import OllamaProvider
    provider = OllamaProvider(model="llama3")
    kwargs = {}
    provider._apply_reasoning_params(kwargs)

    assert "extra_body" in kwargs
    assert kwargs["extra_body"].get("keep_alive") == "1h"

