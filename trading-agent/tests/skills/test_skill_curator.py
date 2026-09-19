"""
Unit tests for skill usage tracker and curator lifecycle transitions.
"""

from datetime import datetime, timezone, timedelta
from pathlib import Path
from skills.usage_tracker import SkillUsageTracker
from skills.curator import SkillCurator


def test_usage_tracker(tmp_path: Path):
    skill = tmp_path / "test_strategy.md"
    skill.write_text("# Test Strategy\n", encoding="utf-8")

    SkillUsageTracker.record_view(skill)
    SkillUsageTracker.record_use(skill)

    data = SkillUsageTracker.load(skill)
    assert data["view_count"] == 1
    assert data["use_count"] == 1
    assert data["last_used_at"] is not None


def test_skill_curator_transitions(tmp_path: Path):
    curator = SkillCurator(skills_dir=tmp_path, stale_days=14, archive_days=30)

    # 1. Protected skill -> should remain active even if very old
    protected = tmp_path / "smc_ict_playbook.md"
    protected.write_text("# SMC\n", encoding="utf-8")
    old_time = datetime.now(timezone.utc) - timedelta(days=60)
    SkillUsageTracker.save(protected, {"created_at": old_time.isoformat(), "last_used_at": old_time.isoformat()})

    # 2. Stale skill (20 days idle) -> stale
    stale = tmp_path / "stale_setup.md"
    stale.write_text("# Stale\n", encoding="utf-8")
    stale_time = datetime.now(timezone.utc) - timedelta(days=20)
    SkillUsageTracker.save(stale, {"created_at": stale_time.isoformat(), "last_used_at": stale_time.isoformat()})

    # 3. Idle skill (45 days idle) -> archived
    idle = tmp_path / "idle_strategy.md"
    idle.write_text("# Idle\n", encoding="utf-8")
    idle_time = datetime.now(timezone.utc) - timedelta(days=45)
    SkillUsageTracker.save(idle, {"created_at": idle_time.isoformat(), "last_used_at": idle_time.isoformat()})

    report = curator.apply_lifecycle_transitions()

    assert "smc_ict_playbook" in report["active"]
    assert "stale_setup" in report["stale"]
    assert "idle_strategy" in report["archived"]

    # Verify idle skill was physically moved to .archive
    assert not idle.exists()
    assert (tmp_path / ".archive" / "idle_strategy.md").exists()
