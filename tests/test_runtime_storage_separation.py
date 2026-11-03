"""
Unit and integration tests for Runtime Storage Separation and Layered Resolution Engine.
Verifies that runtime state writes exclusively to DATA_DIR and never dirties Git-tracked source trees.
"""

import os
from pathlib import Path
import pytest

from monika.core.paths import (
    atomic_write_text,
    get_runtime_skills_dir,
    get_runtime_strategies_dir,
    get_runtime_playbooks_dir,
    get_static_skills_dir,
    get_static_strategies_dir,
)
from monika.application.skills.loader import (
    load_skill,
    list_skills,
    _read_skill_raw,
    invalidate_cache,
)
from monika.application.skills.usage_tracker import SkillUsageTracker
from monika.infrastructure.storage.playbook_catalog_repository import PlaybookCatalogRepository


def test_atomic_write_text(tmp_path):
    """Verify atomic write protocol creates target file cleanly and handles overwrites."""
    target = tmp_path / "subdir" / "test_file.txt"
    content = "Hello Atomic Monika"
    atomic_write_text(target, content)

    assert target.exists()
    assert target.read_text(encoding="utf-8") == content

    # Test atomic overwrite
    new_content = "Updated Atomic Content"
    atomic_write_text(target, new_content)
    assert target.read_text(encoding="utf-8") == new_content

    # Ensure no residual temp files remain
    temp_files = list(target.parent.glob(".tmp_*"))
    assert len(temp_files) == 0


def test_paths_anchoring_and_isolation():
    """Verify paths are correctly anchored and distinct."""
    static_skills = get_static_skills_dir()
    runtime_skills = get_runtime_skills_dir()
    runtime_strategies = get_runtime_strategies_dir()
    runtime_playbooks = get_runtime_playbooks_dir()
    static_strategies = get_static_strategies_dir()

    assert static_skills.name == "skills"
    assert "runtime_skills" in str(runtime_skills)
    assert "runtime_strategies" in str(runtime_strategies)
    assert "playbooks" in str(runtime_playbooks)
    assert "synthesized" in str(static_strategies)


def test_layered_skill_resolution_precedence(tmp_path, monkeypatch):
    """
    Verify that:
    1. Static template is loaded by default.
    2. Dynamic runtime skill takes precedence when present.
    3. 0-byte file in runtime directory does NOT shadow the static template.
    4. Removing runtime file cleanly falls back to static template.
    """
    invalidate_cache()
    rt_skills = tmp_path / "runtime_skills"
    rt_skills.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MONIKA_RUNTIME_DATA_DIR", str(tmp_path))

    # 1. Base static template read
    base_notes = load_skill("performance-notes")
    assert "Performance Notes — Auto-Generated Review" in base_notes or len(base_notes) > 0

    # 2. Dynamic runtime override
    dyn_dir = rt_skills / "trading" / "performance-notes"
    dyn_dir.mkdir(parents=True, exist_ok=True)
    dyn_file = dyn_dir / "SKILL.md"
    dyn_content = "---\nname: performance-notes\n---\n# DYNAMIC WEEKLY REVIEW 2026-11-03\nAll systems nominal."
    atomic_write_text(dyn_file, dyn_content)

    invalidate_cache()
    loaded_dyn = load_skill("performance-notes")
    assert "# DYNAMIC WEEKLY REVIEW 2026-11-03" in loaded_dyn

    # 3. 0-byte guard: write empty file to dynamic location
    dyn_file.write_text("", encoding="utf-8")
    invalidate_cache()
    loaded_fallback = load_skill("performance-notes")
    # Must fallback to static template, NOT return empty string
    assert "Performance Notes" in loaded_fallback
    assert len(loaded_fallback) > 0

    # 4. Fallback when dynamic file is unlinked
    dyn_file.unlink()
    invalidate_cache()
    loaded_clean = load_skill("performance-notes")
    assert "Performance Notes" in loaded_clean


def test_directory_traversal_defense(tmp_path, monkeypatch):
    """Verify that path traversal outside allowed roots is blocked."""
    monkeypatch.setenv("MONIKA_RUNTIME_DATA_DIR", str(tmp_path))

    with pytest.raises(ValueError, match="Invalid skill name|Path traversal detected"):
        _read_skill_raw("../../../etc/passwd")

    with pytest.raises(ValueError, match="Invalid skill name|Path traversal detected"):
        _read_skill_raw("..\\..\\windows\\system32")


def test_skill_usage_tracker_telemetry_isolation(tmp_path, monkeypatch):
    """Verify SkillUsageTracker writes to runtime telemetry directory and never inside skills/."""
    monkeypatch.setenv("MONIKA_RUNTIME_DATA_DIR", str(tmp_path))

    dummy_skill = tmp_path / "skills" / "trading" / "my-test-skill" / "SKILL.md"
    dummy_skill.parent.mkdir(parents=True, exist_ok=True)
    dummy_skill.write_text("Dummy content", encoding="utf-8")

    # Record use
    SkillUsageTracker.record_use(dummy_skill)

    # Assert no .usage.json file was created next to dummy_skill
    assert not (dummy_skill.parent / ".usage.json").exists()
    assert not (dummy_skill.parent / "SKILL.usage.json").exists()

    # Assert telemetry was written inside runtime telemetry dir
    rt_telemetry = tmp_path / "runtime_skills" / "telemetry"
    assert rt_telemetry.exists()
    telemetry_files = list(rt_telemetry.glob("*.usage.json"))
    assert len(telemetry_files) > 0


def test_playbook_catalog_layered_discovery(tmp_path, monkeypatch):
    """Verify PlaybookCatalogRepository discovers and merges playbooks from runtime directory."""
    monkeypatch.setenv("MONIKA_RUNTIME_DATA_DIR", str(tmp_path))

    rt_playbooks = tmp_path / "runtime_skills" / "playbooks"
    rt_playbooks.mkdir(parents=True, exist_ok=True)

    # Create a dynamic runtime playbook
    custom_pb = rt_playbooks / "eurusd_runtime_test_edge_playbook.md"
    custom_content = """---
symbol: EURUSD
name: eurusd_runtime_test_edge
timeframe: H1
profit_factor: 2.45
win_rate: 68.0
min_rr: 1.8
regimes: [TREND, VOLATILE]
tags: [runtime, edge]
---

## Setup Criteria
1. Institutional test criteria.
"""
    atomic_write_text(custom_pb, custom_content)

    repo = PlaybookCatalogRepository()
    specs = repo.load_playbooks_for_symbol("EURUSD")

    # Verify that the runtime playbook was parsed and returned
    matched = [s for s in specs if "runtime_test_edge" in s.name]
    assert len(matched) == 1
    assert matched[0].profit_factor == 2.45
