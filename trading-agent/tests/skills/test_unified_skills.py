# ==============================================================================
# File: tests/skills/test_unified_skills.py
# ==============================================================================

"""
Unit Test Suite for Stage 6:
Unified Skills Runtime, Two-Tier Progressive Disclosure,
and Financial/Research Skill Catalog.
"""

import pytest

from skills.unified_runtime import UnifiedSkillsRuntime, get_skills_runtime


def test_skills_runtime_discovery():
    runtime = get_skills_runtime()
    runtime.reload()
    skills = runtime.list_skills()
    assert len(skills) > 0

    skill_names = {s["name"] if isinstance(s, dict) else s.name for s in skills}
    assert "financial-research" in skill_names
    assert "code-optimization" in skill_names
    assert "academic-literature" in skill_names


def test_two_tier_progressive_disclosure():
    runtime = get_skills_runtime()

    # Tier 1: Compact prompt index
    index_md = runtime.get_compact_prompt_index()
    assert "Available Specialization Skills" in index_md
    assert "financial-research" in index_md
    # Tier 1 should NOT dump full body text
    assert "## 1. Prediction Markets" not in index_md

    # Tier 2: On-demand instruction disclosure
    instructions = runtime.load_skill_instructions(
        "financial-research",
        context_vars={"SESSION_ID": "sess_123"},
    )
    assert "Prediction Markets (Polymarket" in instructions
    assert "Hyperliquid" in instructions


def test_skill_intent_matching():
    runtime = get_skills_runtime()

    # Test query for financial research (Hyperliquid / Polymarket)
    q1 = "Tolong periksa funding rates di hyperliquid dan odds polymarket"
    matched1 = runtime.match_skills_for_prompt(q1)
    assert "financial-research" in matched1

    # Test query for code optimization
    q2 = "Bagaimana cara refactor code ini dengan prinsip YAGNI dan stdlib?"
    matched2 = runtime.match_skills_for_prompt(q2)
    assert "code-optimization" in matched2

    # Test query for academic papers
    q3 = "Bantu cari paper di arxiv tentang order flow toxicity"
    matched3 = runtime.match_skills_for_prompt(q3)
    assert "academic-literature" in matched3
