"""
Unit tests for Harness^2 Production Integration in Monika:
- ScenarioBasedProbeRunner
- DatabaseMemoryGCAdapter
- GEPAEvolutionRunner
- Alpha Arena Leaderboard Persistence & Routing
- Playbook Rule Pruning & Cross-Symbol Generalization
- PlaybookCurator recursion hook
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from monika.domain.harness.models import HarnessDiff
from monika.application.analysis.harness.prober import HarnessProber, ProbeMetrics, ScenarioBasedProbeRunner
from monika.application.analysis.harness.tree import HarnessTree
from monika.application.analysis.memory.memory_lifecycle_gc import (
    DatabaseMemoryGCAdapter,
    MemoryLifecycleGC,
    MemoryNode,
)
from monika.application.analysis.memory.lesson_consolidator import (
    enforce_declarative_memory_rule,
    generalize_cross_symbol_lessons,
    prune_playbook_rules,
)
from monika.application.benchmark.alpha_arena import (
    AlphaArenaTournament,
    load_arena_leaderboard,
    persist_tournament_leaderboard,
)
from monika.application.benchmark.prompt_evolution import GEPAEvolutionRunner, GEPAFullEvolver
from monika.application.scheduler.playbook_curator import PlaybookCurator


def test_scenario_based_probe_runner_with_scenarios():
    runner = ScenarioBasedProbeRunner()
    tree = HarnessTree.build_baseline_tree()

    scenarios = [
        {"pnl": 120.0, "vix": 16.0, "spread_pips": 1.2},
        {"pnl": -40.0, "vix": 17.0, "spread_pips": 1.0},
        {"pnl": 250.0, "vix": 15.0, "spread_pips": 0.8},
        {"pnl": -100.0, "vix": 26.0, "spread_pips": 3.0},  # Filtered by fail-closed guardrail
    ]

    metrics = runner(tree, {"domain": "EURUSD_TREND", "scenarios": scenarios})
    assert isinstance(metrics, ProbeMetrics)
    assert metrics.violations_detected == 0
    assert metrics.composite_score > 0.0
    assert metrics.details.get("scenarios_evaluated") == 4
    assert metrics.win_rate_estimate >= 0.50


@pytest.mark.asyncio
async def test_database_memory_gc_adapter_lifecycle(tmp_path):
    gc_engine = MemoryLifecycleGC(base_stability_days=5.0, archive_dir=tmp_path)
    adapter = DatabaseMemoryGCAdapter(gc_engine=gc_engine)

    # Mock DB session and records
    now = datetime.now(timezone.utc)
    mock_reflection = MagicMock()
    mock_reflection.id = 101
    mock_reflection.status = "resolved"
    mock_reflection.specific_lesson = "Test empirical lesson"
    mock_reflection.reflection_text = None
    mock_reflection.created_at = now
    mock_reflection.resolved_at = now
    mock_reflection.was_profitable = True
    mock_reflection.confidence = 0.85
    mock_reflection.outcome_process_classification = None

    mock_candidate = MagicMock()
    mock_candidate.id = 202
    mock_candidate.status = "rejected"
    mock_candidate.lesson_text = "Deprecated candidate lesson"
    mock_candidate.proposed_at = now
    mock_candidate.promoted_at = None
    mock_candidate.evaluated_trades_count = 5
    mock_candidate.rejection_reason = None

    mock_session = AsyncMock()
    # Mock execute return values for reflection and candidate queries
    refl_result = MagicMock()
    refl_result.scalars.return_value.all.return_value = [mock_reflection]

    cand_result = MagicMock()
    cand_result.scalars.return_value.all.return_value = [mock_candidate]

    mock_session.execute.side_effect = [refl_result, cand_result]

    report = await adapter.run_database_gc(mock_session, as_of=now)
    assert report.total_scanned == 2
    assert report.active_retained >= 1


@pytest.mark.asyncio
async def test_alpha_arena_persistence_and_loading(tmp_path, monkeypatch):
    tournament = AlphaArenaTournament()
    tournament.record_match(
        "model_a",
        "model_b",
        metrics_a={"pnl_pct": 5.0, "sharpe_ratio": 1.8},
        metrics_b={"pnl_pct": 1.0, "sharpe_ratio": 0.5},
    )

    leaderboard = tournament.get_leaderboard()
    assert len(leaderboard) == 2
    assert leaderboard[0]["name"] == "model_a"
    assert leaderboard[0]["elo"] > 1200.0

    # Mock get_data_dir to tmp_path
    monkeypatch.setattr("monika.infrastructure.infra.paths.get_data_dir", lambda: tmp_path)

    # Mock DB session for persist
    mock_session = AsyncMock()
    mock_bind = MagicMock()
    mock_bind.dialect.name = "postgresql"
    mock_session.bind = mock_bind
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    mock_res.scalar_one.return_value = None
    mock_session.execute.return_value = mock_res

    await persist_tournament_leaderboard(tournament, mock_session)

    # Verify local cache file exists
    cache_file = tmp_path / "arena_leaderboard.json"
    assert cache_file.exists()
    cached_data = json.loads(cache_file.read_text(encoding="utf-8"))
    assert len(cached_data.get("standings", [])) == 2


def test_prune_playbook_rules_max_cap():
    # Generate 35 rules
    rules = [f"- Rule {i}: Actionable check number {i}" for i in range(1, 36)]
    body = "# Section Header\n\n" + "\n".join(rules)

    pruned = prune_playbook_rules(body, max_rules=25)
    bullet_lines = [l for l in pruned.split("\n") if l.strip().startswith("-")]
    assert len(bullet_lines) == 25
    # Should retain the latest rules
    assert "Rule 35" in pruned
    assert "# Section Header" in pruned


@pytest.mark.asyncio
async def test_generalize_cross_symbol_lessons():
    mock_session = AsyncMock()
    rows = []
    for sym in ["EURUSD", "GBPUSD", "XAUUSD"]:
        cand = MagicMock()
        cand.symbol = sym
        cand.status = "promoted"
        cand.lesson_text = f"Stop loss distance under high volatility creates premature stop hunt for {sym}"
        rows.append(cand)

    query_res = MagicMock()
    query_res.scalars.return_value.all.return_value = rows
    mock_session.execute.return_value = query_res

    universal_rules = await generalize_cross_symbol_lessons(mock_session, min_symbols=3)
    assert len(universal_rules) > 0
    assert "Empirical observation: Across" in universal_rules[0]


def test_playbook_curator_run_domain_harness_recursion(tmp_path):
    curator = PlaybookCurator()
    res = curator.run_domain_harness_recursion(
        domain="EURUSD__TRENDING",
        scenario_data={"domain": "EURUSD__TRENDING", "symbol": "EURUSD"},
    )
    assert res is not None
    assert res["domain"] == "EURUSD__TRENDING"
    assert "run_id" in res
    assert "composite_score" in res


@pytest.mark.asyncio
async def test_gepa_evolution_runner_execution():
    runner = GEPAEvolutionRunner()
    evolver = GEPAFullEvolver()

    # Test safety invariants
    safe_prompt = (
        "You are an SMC analyst.\n"
        "Must calculate_position_size carefully.\n"
        "Assess whether catalysts are priced_in.\n"
        "Filter untrusted_external_content strictly."
    )
    is_safe, violations = evolver.verify_invariant_compliance(safe_prompt)
    assert is_safe is True
    assert len(violations) == 0

    unsafe_prompt = "You are an analyst. Buy whenever price goes up."
    is_unsafe, violations = evolver.verify_invariant_compliance(unsafe_prompt)
    assert is_unsafe is False
    assert len(violations) > 0
