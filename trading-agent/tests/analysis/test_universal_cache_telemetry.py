from types import SimpleNamespace
from analysis.providers.openai_provider import OpenAIProvider


def test_openai_extract_usage_with_cached_tokens():
    """Verify OpenAI cached_tokens extraction from prompt_tokens_details."""
    usage_obj = SimpleNamespace(
        prompt_tokens=1500,
        completion_tokens=250,
        prompt_tokens_details=SimpleNamespace(cached_tokens=1024),
        completion_tokens_details=SimpleNamespace(reasoning_tokens=128),
        total_cost=0.0045
    )
    inp, outp, cached, thinking, exact_cost, cache_creation = OpenAIProvider._extract_usage(usage_obj)
    assert inp == 1500
    assert outp == 250
    assert cached == 1024
    assert thinking == 128
    assert exact_cost == 0.0045
    assert cache_creation == 0


def test_deepseek_extract_usage_with_cache_hit_and_miss():
    """Verify DeepSeek prefix cache hit & miss extraction."""
    deepseek_usage = {
        "prompt_tokens": 3000,
        "completion_tokens": 400,
        "prompt_cache_hit_tokens": 2800,
        "prompt_cache_miss_tokens": 200,
        "completion_tokens_details": {"reasoning_tokens": 350}
    }
    inp, outp, cached, thinking, exact_cost, cache_creation = OpenAIProvider._extract_usage(deepseek_usage)
    assert inp == 3000
    assert outp == 400
    assert cached == 2800
    assert cache_creation == 200
    assert thinking == 350


def test_deterministic_tool_ordering_for_prefix_invariance():
    """Verify tools are lexicographically sorted to guarantee byte-identical prefix KV cache hits."""
    provider = OpenAIProvider(model="gpt-4o", api_key="sk-mock")
    unsorted_tools = [
        {"name": "submit_asset_analysis", "description": "Submit"},
        {"name": "calculate_position_size", "description": "Calc"},
        {"name": "get_price_history", "description": "Get price"},
        {"name": "get_atr", "description": "Get ATR"},
    ]
    converted = provider._convert_tools(unsorted_tools)
    names = [t["function"]["name"] for t in converted]
    assert names == [
        "calculate_position_size",
        "get_atr",
        "get_price_history",
        "submit_asset_analysis",
    ]
