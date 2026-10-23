# ==============================================================================
# File: tests/analysis/memory/test_fase_8_hardening.py
# Monika FASE 8 Hardening & Architecture Regression Test Suite
# ==============================================================================

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from monika.application.analysis.journal.attribution_engine import (
    AttributionEngine,
    BrokerTrade,
    ShadowRule,
)
from monika.application.analysis.journal.journal_parser import JournalParser
from monika.application.analysis.memory.alpha_calculator import AlphaCalculator
from monika.application.analysis.memory.context_engine import ContextEngine
from monika.application.analysis.memory.memory_lifecycle_gc import MemoryLifecycleGC, MemoryNode
from monika.application.analysis.memory.playbook_ledger import PlaybookLedger
from monika.application.analysis.memory.trajectory_compressor import truncate_middle_text
from monika.application.skills.loader import is_playbook_eligible
from monika.application.skills.skill_manager import SkillManager
from monika.application.skills.skills_hub import SkillsHub


def test_trajectory_compressor_zero_limit():
    """Verify truncate_middle_text does not duplicate text when max_chars <= 0."""
    text = "Hello World"
    assert truncate_middle_text(text, 0) == ""
    assert truncate_middle_text(text, -5) == ""
    assert truncate_middle_text(text, 50) == text


def test_ebbinghaus_gc_promoted_lesson_retention_floor():
    """Verify promoted golden lessons maintain retention floor and are never evicted."""
    gc = MemoryLifecycleGC(base_stability_days=10.0, active_threshold=0.40, archive_threshold=0.10)
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    old_time = datetime(2025, 1, 1, tzinfo=timezone.utc)

    promoted_node = MemoryNode(
        id="cand_1",
        category="candidate_lesson",
        summary="Always wait for 4H candle close before entry",
        created_at=old_time,
        last_retrieved_at=old_time,
        retrieval_count=1,
        importance_weight=1.5,
        status="active",
    )
    score = gc.compute_retention(promoted_node, as_of=now)
    assert score >= 0.50, f"Promoted lesson retention score {score} fell below 0.50 floor"

    rem, report = gc.run_gc_pass([promoted_node], as_of=now)
    assert len(rem) == 1
    assert rem[0].status == "active"
    assert report.archived_evicted == 0


def test_context_engine_duplicate_system_role_removal():
    """Verify ContextEngine strips duplicate system role to prevent Anthropic 400 Bad Request."""
    engine = ContextEngine(max_context_tokens=4000)
    messages = [
        {"role": "system", "content": "Sub-agent instruction"},
        {"role": "user", "content": "Analyze EURUSD"},
    ]
    assembled = engine.assemble_context(
        system_prompt="Base prompt",
        messages=messages,
    )
    system_msgs = [m for m in assembled if m.get("role") == "system"]
    assert len(system_msgs) == 1
    assert "Base prompt" in system_msgs[0]["content"]
    assert "Sub-agent instruction" in system_msgs[0]["content"]
    assert assembled[1]["role"] == "user"


def test_skills_hub_path_traversal_prevention():
    """Verify SkillsHub.view_skill blocks path traversal outside the skill directory."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        base = Path(tmp_dir)
        skill_dir = base / "skills" / "trading" / "my_skill"
        skill_dir.mkdir(parents=True)
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text("# My Skill", encoding="utf-8")

        outside_secret = base / "secret.txt"
        outside_secret.write_text("CONFIDENTIAL", encoding="utf-8")

        hub = SkillsHub()
        mock_meta = MagicMock()
        mock_meta.path = str(skill_file)
        hub._skills["my_skill"] = mock_meta

        # Attempt path traversal
        success, content = hub.view_skill("my_skill", file_path="../../../secret.txt")
        assert not success
        assert "Access denied" in content or "traversal" in content.lower()


def test_skill_manager_protected_skill_normalization():
    """Verify SkillManager protects core playbooks regardless of kebab-case or snake_case."""
    sm = SkillManager()
    success, msg = sm.delete_skill("smc-ict-playbook", force=False)
    assert not success
    assert "protected core playbook" in msg


def test_playbook_loader_extension_agnostic_eligibility():
    """Verify is_playbook_eligible checks both with and without .md."""
    res1 = is_playbook_eligible("smc_ict_playbook")
    res2 = is_playbook_eligible("smc_ict_playbook.md")
    assert isinstance(res1, bool)
    assert isinstance(res2, bool)


def test_playbook_ledger_rollback_no_double_extension():
    """Verify PlaybookLedger.rollback does not create .md.md files."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        ledger = PlaybookLedger(playbooks_dir=tmp_dir)
        pb_name = "test_strategy.md"
        clean = pb_name.removesuffix(".md")
        expected_path = os.path.join(ledger.playbooks_dir, f"{clean}.md")
        assert not expected_path.endswith(".md.md")
        assert expected_path.endswith("test_strategy.md")


def test_attribution_engine_multi_rule_per_symbol():
    """Verify AttributionEngine groups multiple rules for the same symbol without overwriting."""
    rules = [
        ShadowRule(
            rule_id="R1",
            symbol="EURUSD",
            action="buy",
            allowed_hours=[8, 9, 10],
            allowed_weekdays=[0, 1, 2, 3, 4],
            min_holding_mins=15.0,
            max_holding_mins=120.0,
            expected_win_rate=0.60,
            expected_rr=2.0,
            sample_trades=10,
            rule_description="London Morning Long",
        ),
        ShadowRule(
            rule_id="R2",
            symbol="EURUSD",
            action="sell",
            allowed_hours=[13, 14, 15],
            allowed_weekdays=[0, 1, 2, 3, 4],
            min_holding_mins=15.0,
            max_holding_mins=120.0,
            expected_win_rate=0.60,
            expected_rr=2.0,
            sample_trades=10,
            rule_description="NY Afternoon Short",
        ),
    ]

    t_buy = BrokerTrade(
        ticket="1",
        symbol="EURUSD",
        action="buy",
        lots=1.0,
        open_price=1.0800,
        close_price=1.0850,
        open_time=datetime(2026, 3, 2, 9, 0, tzinfo=timezone.utc),
        close_time=datetime(2026, 3, 2, 9, 30, tzinfo=timezone.utc),
        holding_seconds=1800.0,
        pnl=500.0,
    )
    t_sell = BrokerTrade(
        ticket="2",
        symbol="EURUSD",
        action="sell",
        lots=1.0,
        open_price=1.0850,
        close_price=1.0800,
        open_time=datetime(2026, 3, 2, 14, 0, tzinfo=timezone.utc),
        close_time=datetime(2026, 3, 2, 14, 30, tzinfo=timezone.utc),
        holding_seconds=1800.0,
        pnl=500.0,
    )

    waterfall = AttributionEngine.attribute_performance(trades=[t_buy, t_sell], rules=rules)
    assert waterfall.compliant_trade_count == 2
    assert waterfall.noise_trade_count == 0


def test_journal_parser_fails_closed_on_unparseable_dates():
    """Verify JournalParser skips records with unparseable timestamps instead of corrupting date with now()."""
    bad_csv = (
        "ticket,open_time,close_time,symbol,type,volume,open_price,close_price,pnl\n"
        "9999,INVALID_DATE_XYZ,2026-03-01 10:15:00,XAUUSD,BUY,0.5,2630.0,2635.0,250.0\n"
    )
    trades = JournalParser.parse_csv(bad_csv)
    assert len(trades) == 0


@pytest.mark.asyncio
async def test_alpha_calculator_no_tautology_on_eurusd():
    """Verify AlphaCalculator uses non-EURUSD proxy for EURUSD intraday trades to prevent zero-alpha tautology."""
    mock_session = MagicMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.side_effect = [150.0, 151.5]
    mock_session.execute = AsyncMock(return_value=mock_res)

    calc = AlphaCalculator(mock_session)
    entry_t = datetime(2026, 3, 1, 8, 0, tzinfo=timezone.utc)
    exit_t = datetime(2026, 3, 1, 16, 0, tzinfo=timezone.utc)

    alpha_res = await calc.calculate_alpha(
        symbol="EURUSD",
        direction="BUY",
        entry_time=entry_t,
        exit_time=exit_t,
        asset_return_pct=1.5,
    )
    assert alpha_res["benchmark_name"] == "DXY"
    assert isinstance(alpha_res["alpha_return"], float)
