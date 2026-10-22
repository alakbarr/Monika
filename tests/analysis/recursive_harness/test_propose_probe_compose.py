"""
Tests for Task-Level Recursion (Propose -> Probe -> Contrastive Select -> Compose)
and the Unified RecursiveHarnessService.
"""

from monika.domain.harness.models import HarnessViolationError
from monika.application.analysis.recursive_harness.composer import HarnessComposer
from monika.application.analysis.recursive_harness.library import DomainExperienceLibrary
from monika.application.analysis.recursive_harness.prober import HarnessProber, ProbeMetrics, ProbeResult
from monika.application.analysis.recursive_harness.proposer import HarnessProposer
from monika.application.analysis.recursive_harness.selector import ContrastiveSelection, ContrastiveSelector
from monika.application.analysis.recursive_harness.service import RecursiveHarnessService
from monika.application.analysis.recursive_harness.tree import HarnessTree


def test_proposer_generates_valid_candidates():
    proposer = HarnessProposer()
    base_tree = HarnessTree.build_baseline_tree()
    domain = "EURUSD_TREND"

    candidates = proposer.propose_candidates(
        base_tree=base_tree,
        domain=domain,
        regime_context={"volatility": "normal"},
        k_candidates=2,
    )

    assert len(candidates) == 2
    for cand in candidates:
        assert cand.tree is not None
        assert not cand.diff.is_empty


def test_prober_evaluates_candidates():
    prober = HarnessProber()
    base_tree = HarnessTree.build_baseline_tree()
    proposer = HarnessProposer()
    candidates = proposer.propose_candidates(base_tree, "EURUSD_TREND", {})

    results = prober.probe_candidates(base_tree, candidates, {"domain": "EURUSD_TREND"})
    assert len(results) == 3  # base + 2 candidates
    assert results[0].candidate_id == "base"
    for r in results:
        assert r.delivered_cleanly is True
        assert r.metrics.composite_score > 0.0


def test_contrastive_selector_picks_winner():
    selector = ContrastiveSelector(min_improvement_margin=0.03)
    base_tree = HarnessTree.build_baseline_tree()

    # Candidate A outperforms base
    cand_tree = HarnessTree.from_dict(
        {
            **base_tree.to_dict(),
            "skills/trading/playbooks/momentum.md": "# Momentum",
        }
    )

    results = [
        ProbeResult(
            candidate_id="base",
            tree=base_tree,
            metrics=ProbeMetrics(0.8, 0.8, 0.55, 1.5, 0.1),
        ),
        ProbeResult(
            candidate_id="cand_1",
            tree=cand_tree,
            metrics=ProbeMetrics(0.95, 0.95, 0.75, 2.2, 0.05),
        ),
    ]

    selection = selector.select("EURUSD_TREND", results, {})
    assert selection.chosen_candidate_id == "cand_1"
    assert selection.chosen_is_base is False
    assert "outperformed base" in selection.why
    assert selection.experience_cue != ""


def test_contrastive_selector_falls_back_to_base_on_insufficient_gain():
    selector = ContrastiveSelector(min_improvement_margin=0.05)
    base_tree = HarnessTree.build_baseline_tree()

    # Candidate 1 is barely better than base (< 5% gain)
    results = [
        ProbeResult(
            candidate_id="base",
            tree=base_tree,
            metrics=ProbeMetrics(0.80, 0.80, 0.60, 1.6, 0.1),
        ),
        ProbeResult(
            candidate_id="cand_1",
            tree=base_tree,
            metrics=ProbeMetrics(0.81, 0.80, 0.60, 1.6, 0.1),
        ),
    ]

    selection = selector.select("EURUSD_TREND", results, {})
    assert selection.chosen_is_base is True


def test_composer_merges_diff():
    composer = HarnessComposer()
    base_tree = HarnessTree.build_baseline_tree()
    new_skill = "skills/trading/playbooks/pullback.md"
    new_data = {**base_tree.to_dict(), new_skill: "# Pullback Strategy"}
    winner_tree = HarnessTree.from_dict(new_data)

    selection = ContrastiveSelection(
        chosen_candidate_id="cand_1",
        chosen_label="A",
        chosen_tree=winner_tree,
        chosen_is_base=False,
        composite_score=0.92,
        why="Superior score",
        experience_cue="Cue",
        experience_lesson="Lesson",
        evidence={},
    )

    result = composer.compose(base_tree, selection)
    assert result.was_modified is True
    assert new_skill in result.final_tree.components


def test_recursive_harness_service_end_to_end(tmp_path):
    library = DomainExperienceLibrary(root_dir=tmp_path)
    service = RecursiveHarnessService(library=library)

    domain = "METALS__VOLATILITY_EXPANSION"
    res = service.run_recursion_cycle(domain=domain, k_candidates=2)

    assert res.run_id != ""
    assert res.domain == domain
    assert res.final_tree is not None
    assert isinstance(res.summary, str)


def test_scenario_based_probe_runner():
    from monika.application.analysis.recursive_harness.prober import ScenarioBasedProbeRunner

    runner = ScenarioBasedProbeRunner()
    tree = HarnessTree.build_baseline_tree()

    # 1. Test fallback when no scenarios
    metrics = runner(tree, {"domain": "UNKNOWN"})
    assert metrics.composite_score > 0.0

    # 2. Test with explicit scenarios
    scenarios = [
        {"pnl": 150.0, "vix": 16.0, "spread_pips": 1.2},
        {"pnl": -50.0, "vix": 18.0, "spread_pips": 1.1},
        {"pnl": 200.0, "vix": 15.0, "spread_pips": 1.0},
    ]
    scenario_metrics = runner(tree, {"domain": "EURUSD_TREND", "scenarios": scenarios})
    assert scenario_metrics.composite_score > 0.0
    assert scenario_metrics.details.get("scenarios_evaluated") == 3
