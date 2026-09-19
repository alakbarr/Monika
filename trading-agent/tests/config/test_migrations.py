"""
Unit tests for config schema versioning, migration ladder, and fail-closed validation.
"""

import pytest
from pathlib import Path
from config.migrations import (
    CURRENT_CONFIG_VERSION,
    SUPPORT_FLOOR_VERSION,
    get_config_version,
    migrate_config,
    require_parseable_config,
    register_migration,
)


def test_get_config_version():
    assert get_config_version({}) == 0
    assert get_config_version({"_config_version": 1}) == 1
    assert get_config_version({"_config_version": "2"}) == 2


def test_migrate_config_baseline():
    raw = {"app_name": "Monika"}
    migrated, was_migrated = migrate_config(raw)
    assert was_migrated is True
    assert migrated["_config_version"] == CURRENT_CONFIG_VERSION


def test_migrate_config_ladder():
    # Register test migration
    @register_migration(2)
    def v1_to_v2(cfg):
        cfg["migrated_field"] = True
        return cfg

    # Temporarily adjust CURRENT_CONFIG_VERSION for test
    import config.migrations as m
    old_cur = m.CURRENT_CONFIG_VERSION
    try:
        m.CURRENT_CONFIG_VERSION = 2
        raw = {"app_name": "Monika", "_config_version": 1}
        migrated, was_migrated = migrate_config(raw)
        assert was_migrated is True
        assert migrated["_config_version"] == 2
        assert migrated["migrated_field"] is True
    finally:
        m.CURRENT_CONFIG_VERSION = old_cur


def test_require_parseable_config_valid(tmp_path: Path):
    cfg_file = tmp_path / "valid.yaml"
    cfg_file.write_text("app_name: Monika\n", encoding="utf-8")
    require_parseable_config(cfg_file)  # Should not raise


def test_require_parseable_config_invalid_syntax(tmp_path: Path):
    cfg_file = tmp_path / "corrupt.yaml"
    cfg_file.write_text("app_name: Monika:\n  broken yaml: [[\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        require_parseable_config(cfg_file)


def test_require_parseable_config_missing(tmp_path: Path):
    missing_file = tmp_path / "missing.yaml"
    with pytest.raises(SystemExit):
        require_parseable_config(missing_file)
