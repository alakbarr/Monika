import pytest
from config.config_migrations import migrate_settings, CURRENT_CONFIG_VERSION


def test_migrate_settings_backfills_sections():
    raw = {
        "environment": "production",
        "_config_version": 1,
    }
    migrated, applied = migrate_settings(raw)

    assert migrated["_config_version"] == CURRENT_CONFIG_VERSION
    assert "token_budget" in migrated
    assert "paper_trading" in migrated
    assert "learning_loop" in migrated
    assert migrated["token_budget"]["monthly_limit_usd"] == 150.0
    assert len(applied) > 0


def test_migrate_settings_idempotent_on_current_version():
    raw = {
        "environment": "production",
        "_config_version": CURRENT_CONFIG_VERSION,
        "token_budget": {"monthly_limit_usd": 200.0},
    }
    migrated, applied = migrate_settings(raw)

    assert migrated["_config_version"] == CURRENT_CONFIG_VERSION
    assert applied == []
    assert migrated["token_budget"]["monthly_limit_usd"] == 200.0
