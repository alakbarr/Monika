import pytest
from utils.llm.prompt_tiering import build_tiered_prompt, TieredPrompt


def test_tiered_prompt_assembly():
    t1 = "You are a professional forex trading analyst."
    t2 = "Risk Rule: Max 1% risk per trade. Use ATR for stop loss."
    t3 = "Current Time: 2026-09-06T12:00:00Z. EURUSD Price: 1.0850."

    tp = build_tiered_prompt(tier1_identity=t1, tier2_domain=t2, tier3_runtime=t3)

    cacheable_prefix, dynamic_suffix = tp.compile_tuple()
    assert t1 in cacheable_prefix
    assert t2 in cacheable_prefix
    assert t3 not in cacheable_prefix
    assert dynamic_suffix == t3

    full_prompt = tp.compile_full()
    assert t1 in full_prompt
    assert t2 in full_prompt
    assert t3 in full_prompt


def test_tiered_prompt_empty_handling():
    tp = TieredPrompt(tier1_identity="Core Identity")
    prefix, suffix = tp.compile_tuple()
    assert prefix == "Core Identity"
    assert suffix == ""
    assert tp.compile_full() == "Core Identity"
