from tests.conftest import create_mock_async_session
# ==============================================================================
# File: tests/analysis/memory/test_skill_curator.py
# ==============================================================================

import os
import shutil
import tempfile
from datetime import datetime, timezone, timedelta
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from monika.application.analysis.memory.skill_curator import SkillCurator


def test_calculate_similarity():
    text1 = "EURUSD BUY when H4 FVG holds and RSI is below 40."
    text2 = "EURUSD BUY when H4 FVG holds and RSI is below 42."
    text3 = "XAUUSD SELL on London breakout above daily resistance."

    sim_high = SkillCurator.calculate_similarity(text1, text2)
    sim_low = SkillCurator.calculate_similarity(text1, text3)

    assert sim_high > 0.85
    assert sim_low < 0.50


def test_curate_files_stale_and_archive():
    with tempfile.TemporaryDirectory() as temp_dir:
        curator = SkillCurator(playbooks_dir=temp_dir)

        now = datetime.now(timezone.utc)
        # Create 3 files: fresh (1d), stale (35d), old (95d)
        f_fresh = os.path.join(temp_dir, "playbook_fresh.md")
        f_stale = os.path.join(temp_dir, "playbook_stale.md")
        f_old = os.path.join(temp_dir, "playbook_old.md")

        with open(f_fresh, "w", encoding="utf-8") as f:
            f.write("# Fresh Playbook\nSetup content 1.")
        with open(f_stale, "w", encoding="utf-8") as f:
            f.write("# Stale Playbook\nSetup content 2.")
        with open(f_old, "w", encoding="utf-8") as f:
            f.write("# Old Playbook\nSetup content 3.")

        # Set mtimes
        os.utime(f_fresh, ((now - timedelta(days=1)).timestamp(), (now - timedelta(days=1)).timestamp()))
        os.utime(f_stale, ((now - timedelta(days=35)).timestamp(), (now - timedelta(days=35)).timestamp()))
        os.utime(f_old, ((now - timedelta(days=95)).timestamp(), (now - timedelta(days=95)).timestamp()))

        res = curator.curate_files()

        assert res["archived"] == 1
        assert res["stale"] == 1
        assert not os.path.exists(f_old)
        assert os.path.exists(os.path.join(curator.archive_dir, "playbook_old.md"))

        with open(f_stale, "r", encoding="utf-8") as f:
            stale_content = f.read()
        assert "# [STATUS: STALE]" in stale_content


def test_curate_files_deduplication():
    with tempfile.TemporaryDirectory() as temp_dir:
        curator = SkillCurator(playbooks_dir=temp_dir)

        f1 = os.path.join(temp_dir, "playbook_original.md")
        f2 = os.path.join(temp_dir, "playbook_duplicate.md")

        content1 = "# Playbook A\nCondition: BUY XAUUSD when H4 order block is mitigated and DXY falls."
        content2 = "# Playbook B\nCondition: BUY XAUUSD when H4 order block is mitigated and DXY falls down."

        with open(f1, "w", encoding="utf-8") as f:
            f.write(content1)
        with open(f2, "w", encoding="utf-8") as f:
            f.write(content2)

        res = curator.curate_files()

        assert res["deduplicated"] == 1
        remaining_files = [f for f in os.listdir(temp_dir) if f.endswith(".md")]
        archived_files = os.listdir(curator.archive_dir)
        assert len(remaining_files) == 1
        assert len(archived_files) == 1
        assert archived_files[0].startswith("dedup_")


def test_curate_files_distinct_playbooks_not_deduplicated():
    """Verify distinct symbols and distinct strategy names are never falsely deduplicated."""
    with tempfile.TemporaryDirectory() as temp_dir:
        curator = SkillCurator(playbooks_dir=temp_dir)

        # 1. Two different strategies with similar phrasing
        f1 = os.path.join(temp_dir, "audusd_asia_rsi14_fade_playbook.md")
        f2 = os.path.join(temp_dir, "audusd_aud_asian_bb_15_fade_playbook.md")

        content1 = (
            "---\nname: audusd_asia_rsi14_fade_playbook\nsymbol: AUDUSD\n---\n"
            "## Trigger Conditions\n- Long Trigger: sweeps support\n- Short Trigger: sweeps resistance"
        )
        content2 = (
            "---\nname: audusd_aud_asian_bb_15_fade_playbook\nsymbol: AUDUSD\n---\n"
            "## Trigger Conditions\n- Long Trigger: sweeps support\n- Short Trigger: sweeps resistance"
        )

        # 3. Different symbol entirely
        f3 = os.path.join(temp_dir, "eurusd_asia_rsi14_fade_playbook.md")
        content3 = (
            "---\nname: eurusd_asia_rsi14_fade_playbook\nsymbol: EURUSD\n---\n"
            "## Trigger Conditions\n- Long Trigger: sweeps support\n- Short Trigger: sweeps resistance"
        )

        for path, cont in [(f1, content1), (f2, content2), (f3, content3)]:
            with open(path, "w", encoding="utf-8") as f:
                f.write(cont)

        res = curator.curate_files()

        assert res["deduplicated"] == 0
        remaining_files = [f for f in os.listdir(temp_dir) if f.endswith(".md")]
        assert len(remaining_files) == 3


@pytest.mark.asyncio
async def test_curate_db_rules():
    curator = SkillCurator()
    mock_session = create_mock_async_session()

    # Mock execute return values
    res_stale = MagicMock(rowcount=3)
    res_archive = MagicMock(rowcount=2)

    # Active rules for deduplication
    r1 = MagicMock(
        symbol="EURUSD",
        rule_text="BUY on FVG pullback",
        rule_hash="hash1",
        times_triggered=10,
        wins_count=6,
        losses_count=4,
        total_pnl=120.0,
        status="active",
    )
    r2 = MagicMock(
        symbol="EURUSD",
        rule_text="BUY on FVG pullbacks",
        rule_hash="hash2",
        times_triggered=2,
        wins_count=1,
        losses_count=1,
        total_pnl=20.0,
        status="active",
    )

    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [r1, r2]
    res_rules = MagicMock()
    res_rules.scalars.return_value = mock_scalars

    mock_session.execute.side_effect = [res_stale, res_archive, res_rules]

    result = await curator.curate_db_rules(mock_session)

    assert result["stale_count"] == 3
    assert result["archive_count"] == 2
    assert result["dedup_count"] == 1
    assert r1.times_triggered == 12
    assert r2.status == "archived"
    mock_session.commit.assert_awaited_once()
