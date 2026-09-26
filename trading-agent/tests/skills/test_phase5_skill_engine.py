# ==============================================================================
# File: tests/skills/test_phase5_skill_engine.py
# ==============================================================================

import json
import pytest
from pathlib import Path

from skills.curator import SkillCurator
from skills.skill_manager import SkillManager
from skills.skills_hub import SkillsHub
from analysis.tools.domain.skill_tools import handle_skill_manage, SkillManageInput, handle_skills_list


@pytest.fixture
def temp_skills_dir(tmp_path):
    skills_base = tmp_path / "skills"
    skills_base.mkdir()
    (skills_base / "general").mkdir()
    (skills_base / "trading").mkdir()
    (skills_base / "crystallized").mkdir()

    # Create a dummy skill
    test_skill_dir = skills_base / "general" / "test_dummy"
    test_skill_dir.mkdir(parents=True)
    (test_skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: test_dummy\n"
        "description: \"Test dummy skill for automated tests.\"\n"
        "version: 1.0.0\n"
        "category: GENERAL\n"
        "tags: [test, dummy]\n"
        "---\n\n"
        "# Test Dummy\n"
        "Initial instructions line 1.\n"
        "Line 2: Target to be edited.\n"
        "Line 3: Final step.\n",
        encoding="utf-8"
    )
    return skills_base


def test_skill_manager_create_and_inspect(temp_skills_dir):
    hub = SkillsHub(search_directories=[str(temp_skills_dir)])
    manager = SkillManager(base_dir=temp_skills_dir, skills_hub=hub)

    # 1. Create a new skill
    content = "# Custom Workflow\nFollow step 1 and step 2 carefully."
    success, msg = manager.create_skill(
        name="custom_workflow",
        content=content,
        category="general",
        description="A custom automated workflow.",
        tags=["automation", "custom"],
    )
    assert success is True
    assert "created successfully" in msg

    # 2. Inspect skill info
    info = manager.get_skill_info("custom_workflow")
    assert info is not None
    assert info["name"] == "custom_workflow"
    assert info["category"] == "GENERAL"
    assert info["line_count"] > 0
    assert info["audit_safe"] is True


def test_skill_manager_edit_exact_and_fuzzy(temp_skills_dir):
    hub = SkillsHub(search_directories=[str(temp_skills_dir)])
    manager = SkillManager(base_dir=temp_skills_dir, skills_hub=hub)

    # 1. Exact replacement
    success, msg = manager.edit_skill(
        name="test_dummy",
        old_text="Line 2: Target to be edited.",
        replacement_text="Line 2: Successfully replaced with exact match.",
    )
    assert success is True

    # 2. Fuzzy replacement (with whitespace / slight indentation difference)
    fuzzy_target = "   Line 2: Successfully replaced with exact match.   \n  Line 3: Final step.  "
    replacement = "Line 2: Replaced via fuzzy matching.\nLine 3: Concluded."
    success_fuzzy, msg_fuzzy = manager.edit_skill(
        name="test_dummy",
        old_text=fuzzy_target,
        replacement_text=replacement,
        fuzzy_match=True,
    )
    assert success_fuzzy is True

    info = manager.get_skill_info("test_dummy")
    with open(info["path"], "r", encoding="utf-8") as f:
        file_content = f.read()
    assert "Line 2: Replaced via fuzzy matching." in file_content


def test_skill_manager_protected_immunity_and_archival(temp_skills_dir):
    hub = SkillsHub(search_directories=[str(temp_skills_dir)])
    manager = SkillManager(base_dir=temp_skills_dir, skills_hub=hub)

    # Protected core skill cannot be deleted
    success_prot, msg_prot = manager.delete_skill("adjudication_framework", force=False)
    assert success_prot is False
    assert "protected core playbook" in msg_prot

    # Archive regular skill
    success_del, msg_del = manager.delete_skill("test_dummy", archive_instead=True)
    assert success_del is True
    assert "archived successfully" in msg_del

    # Ensure moved to .archive
    archive_dirs = list((temp_skills_dir / ".archive").glob("test_dummy_*"))
    assert len(archive_dirs) == 1


@pytest.mark.asyncio
async def test_handle_skill_manage_tool_workflow(temp_skills_dir, monkeypatch):
    hub = SkillsHub(search_directories=[str(temp_skills_dir)])
    from analysis.tools.domain import skill_tools
    monkeypatch.setattr(skill_tools, "_SKILLS_HUB", hub)

    # Hot reload
    reload_resp = await handle_skill_manage(SkillManageInput(action="hot_reload"))
    reload_data = json.loads(reload_resp)
    assert reload_data["status"] == "reloaded"

    # Info
    info_resp = await handle_skill_manage(SkillManageInput(action="info", name="test_dummy"))
    info_data = json.loads(info_resp)
    assert info_data["name"] == "test_dummy"

    # Edit via tool
    edit_resp = await handle_skill_manage(
        SkillManageInput(
            action="edit",
            name="test_dummy",
            old_text="Initial instructions line 1.",
            replacement_text="Updated initial instructions line 1.",
        )
    )
    assert "updated successfully" in edit_resp
