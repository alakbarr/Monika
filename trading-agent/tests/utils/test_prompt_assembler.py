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


def test_assemble_stage2_tiers_cache_invariance():
    assembler = PromptAssembler({"trading": {"caveman_mode": True}})
    t1_eur, t2_eur, t3_eur = assembler.assemble_stage2_tiers(symbol="EURUSD", include_target_in_system=False)
    t1_gbp, t2_gbp, t3_gbp = assembler.assemble_stage2_tiers(symbol="GBPUSD", include_target_in_system=False)
    assert t1_eur == t1_gbp
    assert t2_eur == t2_gbp
    assert "Symbol: EURUSD" not in t3_eur
    assert "Symbol: GBPUSD" not in t3_gbp
    # Tier 1 + Tier 2 invariant prefix (>= 4,096 tokens) guarantees cross-asset KV-cache hit
    assert estimate_tokens(f"{t1_eur}\n\n{t2_eur}") >= 4096


def test_canonical_prompt_section_ordering():
    from utils.llm.prompt_assembler import (
        SECTION_ORDERS,
        PromptSection,
        compare_sections,
        compose_ordered_prompt,
    )
    s1 = PromptSection(name="DOMAIN_SKILLS", content="Skills Content", order=2000)
    s2 = PromptSection(name="CANONICAL_TIER0_ANCHOR", content="Anchor Content", order=-2000)
    s3 = PromptSection(name="ROLE_MISSION", content="Mission Content", order=0)
    s4 = PromptSection(name="MANDATORY_RULES", content="Rules Content", order=500)

    # Regardless of input list order, compose_ordered_prompt must sort deterministically
    res = compose_ordered_prompt([s1, s4, s2, s3], separator=" | ")
    expected = "Anchor Content | Mission Content | Rules Content | Skills Content"
    assert res == expected

    # Tie-break by name
    t1 = PromptSection(name="B_SEC", content="Content B", order=500)
    t2 = PromptSection(name="A_SEC", content="Content A", order=500)
    res_tie = compose_ordered_prompt([t1, t2], separator=" | ")
    assert res_tie == "Content A | Content B"

