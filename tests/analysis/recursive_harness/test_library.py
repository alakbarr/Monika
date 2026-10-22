"""
Tests for DomainExperienceLibrary (Harnessing-Level Recursion).
"""

from monika.application.analysis.recursive_harness.library import (
    DomainExperienceLibrary,
    sanitize_domain_slug,
)
from monika.application.analysis.recursive_harness.tree import HarnessTree


def test_sanitize_domain_slug():
    assert sanitize_domain_slug("FX / Trending") == "FX__TRENDING"
    assert sanitize_domain_slug("Metals | Volatility Expansion") == "METALS__VOLATILITY_EXPANSION"
    assert sanitize_domain_slug("Crypto/Range-Bound") == "CRYPTO__RANGE-BOUND"
    assert sanitize_domain_slug("   ") == "GENERAL__BALANCED"


def test_record_and_retrieve_experience(tmp_path):
    lib = DomainExperienceLibrary(root_dir=tmp_path)
    tree = HarnessTree.build_baseline_tree()

    domain = "METALS__VOLATILITY_EXPANSION"
    run_id = "test_run_001"
    cue = "Gold breakout during London/NY overlap session"
    lesson = "Require M15 candle close outside the value area before initiating continuation trade."
    evidence = {"win_rate": 0.80, "profit_factor": 2.4, "sample_size": 10}

    entry = lib.record_experience(
        domain=domain,
        run_id=run_id,
        tree=tree,
        cue=cue,
        lesson=lesson,
        evidence=evidence,
    )

    assert entry.run_id == run_id
    assert entry.domain == domain

    # Check file structure on disk
    domain_dir = tmp_path / domain
    assert (domain_dir / "INDEX.md").is_file()
    run_dir = domain_dir / "harnesses" / run_id
    assert (run_dir / "EXPERIENCE.md").is_file()
    assert (run_dir / "harness" / "systemprompt.md").is_file()

    # Check index content
    index_text = (domain_dir / "INDEX.md").read_text(encoding="utf-8")
    assert run_id in index_text

    # Check listing methods
    assert domain in lib.list_domains()
    assert run_id in lib.list_entries(domain)

    # Check latest harness retrieval
    latest_tree = lib.get_latest_harness(domain)
    assert latest_tree is not None
    assert latest_tree.to_dict() == tree.to_dict()

    # Check lesson prompt formatting
    lessons_prompt = lib.format_domain_lessons_for_prompt(domain)
    assert "Require M15 candle close" in lessons_prompt
