import pytest
from utils.llm.prompt_assembler import PromptAssembler
from utils.llm.prompt_compressor import estimate_tokens


def test_assemble_stage1():
    assembler = PromptAssembler({"trading": {"caveman_mode": True}})
    system, user = assembler.assemble_stage1(
        data_bundle="Sample Stage 1 Data",
        core_memory="Sample Core Memory",
        sticky_bias_context="USD sticky bias justification"
    )
    assert "senior macro-economic analyst" in system
    assert "[AGENT MEMORY]" in system
    assert "Sample Core Memory" in system
    assert "[PRE-FETCHED DATA]" in user
    # System prompt begins with Tier-0 Anchor ensuring >= 4,096 tokens for Gemini 3.x KV-cache threshold
    assert estimate_tokens(system) >= 4096


def test_assemble_stage1_tiers():
    assembler = PromptAssembler({"trading": {"caveman_mode": True}})
    t1, t2, t3 = assembler.assemble_stage1_tiers(core_memory="Sample Memory")
    assert "senior macro-economic analyst" in t1
    assert "AVAILABLE TOOL CATEGORIES" in t2
    assert "Sample Memory" in t3


def test_assemble_stage2():
    assembler = PromptAssembler({"trading": {"caveman_mode": True}})
    system, user = assembler.assemble_stage2(
        symbol="XAUUSD",
        data_bundle="Sample Stage 2 Data",
        effective_threshold=8,
        min_rr_ratio=1.4,
        core_memory="Sample Symbol Memory"
    )
    assert "XAUUSD" in system
    assert "Effective Confluence Threshold: 8/14" in system
    assert "Minimum R:R Ratio (Intraday Range Strategy): 1.4" in system
    assert "[AGENT MEMORY]" in system
    assert "AVAILABLE TOOL CATEGORIES" in system
    assert "[PRE-FETCHED DATA]" in user
    assert 1024 <= estimate_tokens(system) < 16000


def test_assemble_stage2_tiers():
    assembler = PromptAssembler({"trading": {"caveman_mode": True}})
    t1, t2, t3 = assembler.assemble_stage2_tiers(symbol="EURUSD")
    assert "SMC/ICT" in t1
    assert "AVAILABLE TOOL CATEGORIES" in t2
    assert "CURRENT ANALYSIS TARGET" in t3
    assert "EURUSD" in t3


def test_assemble_stage1_system_tuple_gemini_cache_threshold():
    assembler = PromptAssembler({"trading": {"caveman_mode": True}})
    static_sys, dynamic_note = assembler.assemble_stage1_system_tuple(
        core_memory="Sample Core Memory",
        behavioral_alert="Sample Alert",
        pad_for_gemini=True
    )
    assert "senior macro-economic analyst" in static_sys
    assert "CANONICAL SYSTEM GOVERNANCE" in static_sys
    assert "Sample Alert" in dynamic_note
    # Gemini 3 implicit caching threshold is 4,096 tokens (>= 16,384 chars)
    assert estimate_tokens(static_sys) >= 4096
