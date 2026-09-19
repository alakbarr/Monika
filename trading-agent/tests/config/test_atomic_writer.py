"""
Unit tests for AtomicConfigWriter (comment preservation, fsync, and backups).
"""

import os
from pathlib import Path
from config.atomic_writer import AtomicConfigWriter


def test_atomic_writer_preserves_comments(tmp_path: Path):
    target_yaml = tmp_path / "settings.yaml"
    initial_content = """# Top-level critical system comment
app_name: Monika # Inline comment for app
trading:
  # Cost mode directive
  cost_mode: standard
  risk_limit: 5.0
"""
    target_yaml.write_text(initial_content, encoding="utf-8")

    # Update in-place
    AtomicConfigWriter.update_in_place(target_yaml, {"trading": {"cost_mode": "institutional"}}, create_backup=True)

    result_text = target_yaml.read_text(encoding="utf-8")

    assert "# Top-level critical system comment" in result_text
    assert "# Cost mode directive" in result_text
    assert "cost_mode: institutional" in result_text

    # Verify backup exists
    backup_dir = tmp_path / "backups"
    assert backup_dir.exists()
    backups = list(backup_dir.glob("settings_*.yaml"))
    assert len(backups) == 1
    assert "cost_mode: standard" in backups[0].read_text(encoding="utf-8")


def test_atomic_writer_prunes_backups_beyond_limit(tmp_path: Path):
    target_yaml = tmp_path / "settings.yaml"
    target_yaml.write_text("app_name: Monika\n", encoding="utf-8")

    for i in range(12):
        AtomicConfigWriter.backup(target_yaml, max_backups=5)

    backup_dir = tmp_path / "backups"
    backups = list(backup_dir.glob("settings_*.yaml"))
    assert len(backups) <= 5
