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


def test_atomic_writer_write_preserves_comments(tmp_path: Path):
    target_yaml = tmp_path / "settings.yaml"
    initial_content = """# Global System Settings
app_name: Monika # Primary bot
trading:
  # Crucial risk comment
  risk_limit: 5.0
  active_mode: live
"""
    target_yaml.write_text(initial_content, encoding="utf-8")

    # Full dictionary passed into write()
    new_data = {
        "app_name": "Monika",
        "trading": {
            "risk_limit": 10.0,
            "active_mode": "paper",
            "new_feature": True,
        },
    }
    AtomicConfigWriter.write(target_yaml, new_data, create_backup=True)

    result_text = target_yaml.read_text(encoding="utf-8")
    assert "# Global System Settings" in result_text
    assert "# Crucial risk comment" in result_text
    assert "risk_limit: 10.0" in result_text
    assert "active_mode: paper" in result_text
    assert "new_feature: true" in result_text.lower()


def test_atomic_writer_preserves_sexagesimal_and_leading_zero_quotes(tmp_path: Path):
    import yaml

    target_yaml = tmp_path / "settings.yaml"
    data = {
        "trading": {
            "schedule": {
                "cycle_times_local": ["07:00", "15:00", "20:00"],
            },
            "markets": {
                "gold": "088691",
                "euro_fx": "099741",
            },
        },
    }
    AtomicConfigWriter.write(target_yaml, data)

    raw_text = target_yaml.read_text(encoding="utf-8")
    assert "'15:00'" in raw_text or '"15:00"' in raw_text
    assert "'20:00'" in raw_text or '"20:00"' in raw_text
    assert "'088691'" in raw_text or '"088691"' in raw_text

    # Standard PyYAML (YAML 1.1) must parse them as str, NOT sexagesimal int (900, 1200)
    parsed = yaml.safe_load(raw_text)
    assert parsed["trading"]["schedule"]["cycle_times_local"] == ["07:00", "15:00", "20:00"]
    for t in parsed["trading"]["schedule"]["cycle_times_local"]:
        assert isinstance(t, str)

    assert parsed["trading"]["markets"]["gold"] == "088691"
    assert isinstance(parsed["trading"]["markets"]["gold"], str)


def test_atomic_writer_update_in_place_sanitizes_time_quotes(tmp_path: Path):
    import yaml

    target_yaml = tmp_path / "settings.yaml"
    initial_content = """trading:
  # Schedule section
  schedule:
    cycle_times_local:
    - '07:00'
"""
    target_yaml.write_text(initial_content, encoding="utf-8")

    update = {
        "trading": {
            "schedule": {
                "cycle_times_local": ["07:00", "15:00", "20:00"],
            }
        }
    }
    AtomicConfigWriter.update_in_place(target_yaml, update)

    raw_text = target_yaml.read_text(encoding="utf-8")
    assert "# Schedule section" in raw_text

    parsed = yaml.safe_load(raw_text)
    assert parsed["trading"]["schedule"]["cycle_times_local"] == ["07:00", "15:00", "20:00"]
    for t in parsed["trading"]["schedule"]["cycle_times_local"]:
        assert isinstance(t, str)
