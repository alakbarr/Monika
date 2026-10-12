from tests.conftest import create_mock_async_session
import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path
from analysis.memory.skill_crystallizer import SkillCrystallizer
from database.models import DecisionReflection, SystemConfig


@pytest.mark.asyncio
async def test_skill_crystallizer_llm_synthesis(tmp_path):
    """Verifies that tactical rules use LLM synthesis or clean sentence extraction without naive slicing."""
    crystallizer = SkillCrystallizer()
    crystallizer.SKILLS_DIR = tmp_path

    mock_session = create_mock_async_session()
    mock_r1 = MagicMock()
    mock_r1.symbol = "BTCUSD"
    mock_r1.confidence = 0.92
    mock_r1.outcome_pnl_usd = 450.0
    mock_r1.reflection_text = "TREND | Strong momentum breakout"
    mock_r1.alpha_lesson = "Identify high volume breakout above H4 resistance before placing momentum entry. Ensure risk reward exceeds 1.5."
    mock_r1.specific_lesson = None
    mock_r1.rationale_summary = None

    mock_r2 = MagicMock()
    mock_r2.symbol = "BTCUSD"
    mock_r2.confidence = 0.88
    mock_r2.outcome_pnl_usd = 310.0
    mock_r2.reflection_text = "TREND | Strong momentum breakout"
    mock_r2.alpha_lesson = "Never chase liquidity without confirmed fair value gap retest. Stop loss must remain below swing low."
    mock_r2.specific_lesson = None
    mock_r2.rationale_summary = None

    mock_r3 = MagicMock()
    mock_r3.symbol = "BTCUSD"
    mock_r3.confidence = 0.89
    mock_r3.outcome_pnl_usd = 280.0
    mock_r3.reflection_text = "TREND | Strong momentum breakout"
    mock_r3.alpha_lesson = "Identify high volume breakout above H4 resistance before placing momentum entry."
    mock_r3.specific_lesson = None
    mock_r3.rationale_summary = None

    mock_r4 = MagicMock()
    mock_r4.symbol = "BTCUSD"
    mock_r4.confidence = 0.91
    mock_r4.outcome_pnl_usd = 350.0
    mock_r4.reflection_text = "TREND | Strong momentum breakout"
    mock_r4.alpha_lesson = "Ensure risk reward exceeds 1.5 before order placement."
    mock_r4.specific_lesson = None
    mock_r4.rationale_summary = None

    mock_r5 = MagicMock()
    mock_r5.symbol = "BTCUSD"
    mock_r5.confidence = 0.87
    mock_r5.outcome_pnl_usd = 220.0
    mock_r5.reflection_text = "TREND | Strong momentum breakout"
    mock_r5.alpha_lesson = "Never chase liquidity without confirmed fair value gap retest."
    mock_r5.specific_lesson = None
    mock_r5.rationale_summary = None

    mock_execute_res = MagicMock()
    mock_execute_res.scalars.return_value.all.return_value = [mock_r1, mock_r2, mock_r3, mock_r4, mock_r5]
    mock_session.execute.return_value = mock_execute_res

    res = await crystallizer.evaluate_and_crystallize(mock_session, symbol="BTCUSD")
    assert len(res) == 1
    skill_meta = res[0]
    skill_file = tmp_path / skill_meta["file"]
    assert skill_file.exists()

    content = skill_file.read_text(encoding="utf-8")
    assert "status: active" in content
    # Ensure synthesized tactical directives exist and contain high conviction rules
    assert "## Empirical Track Record" in content
    assert "## Core Tactical Directives" in content
    assert "## Invalidation Scenarios" in content
    assert "- " in content
    assert any(term in content.lower() for term in ["breakout", "liquidity", "resistance", "risk", "entry", "retest"])


@pytest.mark.asyncio
async def test_skill_attribution_and_auto_deprecation(tmp_path):
    """
    Closed-loop curation: track win-rate attribution and deprecate skills
    whose win-rate drops below 50% over recent trades (min_eval_trades=5).
    """
    crystallizer = SkillCrystallizer()
    crystallizer.SKILLS_DIR = tmp_path

    # Create dummy active crystallized skill file
    skill_name = "crystallized_eurusd_trend"
    skill_file = tmp_path / f"{skill_name}.md"
    skill_file.write_text(
        "---\n"
        f"name: {skill_name}\n"
        "symbol: EURUSD\n"
        "status: active\n"
        "win_count: 5\n"
        "---\n\n"
        "# Content\n",
        encoding="utf-8"
    )

    # Initial check: skill should be returned for EURUSD
    active_skills = crystallizer.get_crystallized_skills_for_symbol("EURUSD", skills_dir=tmp_path)
    assert skill_name in active_skills

    # Mock DB session for SystemConfig
    mock_session = create_mock_async_session()
    mock_session.add = MagicMock()
    existing_row = None

    async def mock_execute(stmt):
        m = MagicMock()
        m.scalar_one_or_none.return_value = existing_row
        return m

    mock_session.execute.side_effect = mock_execute

    # Record trades 1 to 4: losses (times_triggered < 5 -> status remains active)
    current_attr = None
    for i in range(1, 5):
        if current_attr:
            cfg_row = MagicMock()
            cfg_row.value = json.dumps(current_attr)
            existing_row = cfg_row
        current_attr = await crystallizer.record_skill_attribution(
            mock_session, skill_name, was_profitable=False, pnl=-50.0, min_eval_trades=5
        )
        assert current_attr["times_triggered"] == i
        assert current_attr["status"] == "active"  # Not deprecated yet because min_eval_trades = 5

    # Record 5th trade: loss (win rate now 0.0 < 50%, >= 5 trades)
    cfg_row = MagicMock()
    cfg_row.value = json.dumps(current_attr)
    existing_row = cfg_row

    attr5 = await crystallizer.record_skill_attribution(
        mock_session, skill_name, was_profitable=False, pnl=-60.0, min_eval_trades=5
    )
    assert attr5["times_triggered"] == 5
    assert attr5["recent_win_rate"] == 0.0
    assert attr5["status"] == "deprecated"

    # Verify skill file was updated on disk with status: deprecated
    file_content = skill_file.read_text(encoding="utf-8")
    assert "status: deprecated" in file_content
    assert "is_deprecated: true" in file_content

    # Verify that get_crystallized_skills_for_symbol now EXCLUDES the deprecated skill
    active_skills_after = crystallizer.get_crystallized_skills_for_symbol("EURUSD", skills_dir=tmp_path)
    assert skill_name not in active_skills_after


def test_is_skill_deprecated_helper(tmp_path):
    """Verifies that is_skill_deprecated correctly identifies deprecated files across directories."""
    dep_file = tmp_path / "crystallized_deprecated_test.md"
    dep_file.write_text("---\nstatus: deprecated\nis_deprecated: true\n---\n# Rule", encoding="utf-8")

    act_file = tmp_path / "crystallized_active_test.md"
    act_file.write_text("---\nstatus: active\n---\n# Rule", encoding="utf-8")

    assert SkillCrystallizer.is_skill_deprecated("crystallized_deprecated_test", skills_dir=tmp_path) is True
    assert SkillCrystallizer.is_skill_deprecated("crystallized_active_test", skills_dir=tmp_path) is False
    assert SkillCrystallizer.is_skill_deprecated("non_existent_skill", skills_dir=tmp_path) is False


@pytest.mark.asyncio
async def test_skill_crystallizer_configurable_threshold(tmp_path):
    """Verify min_crystallization_wins threshold gating."""
    crystallizer = SkillCrystallizer(settings={"learning": {"min_crystallization_wins": 6}})
    crystallizer.SKILLS_DIR = tmp_path

    mock_session = create_mock_async_session()
    reflections = []
    for i in range(5):
        r = MagicMock()
        r.symbol = "ETHUSD"
        r.confidence = 0.90
        r.outcome_pnl_usd = 200.0 + i * 10
        r.reflection_text = "TREND | Breakout"
        r.alpha_lesson = f"Test rule {i+1}"
        r.specific_lesson = None
        r.rationale_summary = None
        reflections.append(r)

    mock_execute_res = MagicMock()
    mock_execute_res.scalars.return_value.all.return_value = reflections
    mock_session.execute.return_value = mock_execute_res

    # With min_crystallization_wins = 6, 5 reflections should not trigger crystallization
    res = await crystallizer.evaluate_and_crystallize(mock_session, symbol="ETHUSD")
    assert len(res) == 0

