"""
Tests for HarnessTree snapshots, diffs, and serialization.
"""

import pytest

from monika.domain.harness.models import ComponentType, HarnessViolationError
from monika.application.analysis.recursive_harness.tree import HarnessTree


def test_harness_tree_from_dict_and_to_dict():
    data = {
        "systemprompt.md": "System prompt content",
        "guardrails.md": "Guardrails content",
        "skills/trading/playbooks/trend.md": "Trend skill content",
    }
    tree = HarnessTree.from_dict(data)
    assert len(tree.components) == 3
    assert tree.components["systemprompt.md"].component_type == ComponentType.SYSTEM_PROMPT
    assert tree.components["skills/trading/playbooks/trend.md"].component_type == ComponentType.SKILL

    res_dict = tree.to_dict()
    assert res_dict == data


def test_harness_tree_diff_and_apply_diff():
    base_data = {
        "systemprompt.md": "System prompt v1",
        "guardrails.md": "Guardrails v1",
        "skills/trading/playbooks/old.md": "Old skill",
    }
    base_tree = HarnessTree.from_dict(base_data)

    new_data = {
        "systemprompt.md": "System prompt v1",
        "guardrails.md": "Guardrails v2 modified",
        "skills/trading/playbooks/new.md": "New skill added",
    }
    new_tree = HarnessTree.from_dict(new_data)

    diff = base_tree.diff(new_tree)
    assert "skills/trading/playbooks/new.md" in diff.added
    assert "guardrails.md" in diff.modified
    assert "skills/trading/playbooks/old.md" in diff.removed

    # Apply diff to base tree
    applied_tree = base_tree.apply_diff(diff)
    assert applied_tree.to_dict() == new_tree.to_dict()


def test_harness_tree_directory_roundtrip(tmp_path):
    tree = HarnessTree.build_baseline_tree()
    custom_skill = "skills/trading/playbooks/scalp.md"
    tree_data = dict(tree.to_dict())
    tree_data[custom_skill] = "# Scalping Playbook\nHigh speed execution rules."
    tree_with_skill = HarnessTree.from_dict(tree_data)

    export_dir = tmp_path / "exported_harness"
    tree_with_skill.export_to_directory(export_dir)

    # Verify physical files exist
    assert (export_dir / "systemprompt.md").is_file()
    assert (export_dir / custom_skill).is_file()

    # Load back from directory
    reloaded = HarnessTree.load_from_directory(export_dir)
    assert reloaded.to_dict() == tree_with_skill.to_dict()


def test_harness_tree_text_diff():
    t1 = HarnessTree.build_baseline_tree()
    t2_data = dict(t1.to_dict())
    t2_data["guardrails.md"] += "\n- Added new rule."
    t2 = HarnessTree.from_dict(t2_data)

    diff_text = t1.text_diff(t2)
    assert "+- Added new rule." in diff_text
