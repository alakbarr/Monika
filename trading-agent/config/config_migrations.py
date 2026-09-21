"""
Configuration Version Migrations.

Automatically audits, heals, and applies schema updates across versions of settings.yaml.
Preserves existing user customizations while backfilling newly required institutional keys.
"""

import os
import copy
import logging
from typing import Dict, Any, List, Tuple

logger = logging.getLogger("TradingAgent.ConfigMigrations")

CURRENT_CONFIG_VERSION = 3

DEFAULT_SUBSETS: Dict[str, Any] = {
    "_config_version": CURRENT_CONFIG_VERSION,
    "token_budget": {
        "monthly_limit_usd": 150.0,
        "daily_limit_usd": 15.0,
        "cycle_limit_usd": 3.0,
        "warning_threshold_pct": 80.0,
        "critical_threshold_pct": 95.0,
    },
    "execution": {
        "adapter_type": "live",
        "remote_gateway_url": "http://127.0.0.1:8080",
    },
    "paper_trading": {
        "enabled": True,
        "initial_balance": 10000.0,
        "min_trades_for_live": 50,
        "min_win_rate_for_live": 0.55,
    },
    "learning_loop": {
        "auto_promote_playbooks": True,
        "consecutive_loss_limit": 3,
        "min_win_rate": 0.55,
    },
    "harness": {
        "compaction_cooldown_seconds": 120.0,
        "max_context_chars": 100000,
        "retain_recent_turns": 2,
    },
    "evals": {
        "simulation_clock_enabled": True,
    },
    "benchmark": {
        "max_drift_pct": 15.0,
    },
}


def migrate_settings(raw_settings: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """
    Applies schema migrations to in-memory settings dictionary.
    
    Returns:
        (migrated_settings, list_of_applied_migrations)
    """
    settings = copy.deepcopy(raw_settings)
    applied: List[str] = []

    version = settings.get("_config_version", 1)

    if version < 2:
        # Migration from v1 to v2
        v2_subsets = ["token_budget", "execution", "paper_trading", "learning_loop"]
        for section in v2_subsets:
            default_vals = DEFAULT_SUBSETS.get(section, {})
            if section not in settings:
                settings[section] = copy.deepcopy(default_vals)
                applied.append(f"Added missing section '{section}' with default schema")
            elif isinstance(default_vals, dict) and isinstance(settings[section], dict):
                for k, v in default_vals.items():
                    if k not in settings[section]:
                        settings[section][k] = copy.deepcopy(v)
                        applied.append(f"Added missing key '{section}.{k}'")
        settings["_config_version"] = 2
        applied.append("Upgraded config version to 2")
        version = 2

    if version < 3:
        # Migration from v2 to v3
        v3_subsets = ["harness", "evals", "benchmark"]
        for section in v3_subsets:
            default_vals = DEFAULT_SUBSETS.get(section, {})
            if section not in settings:
                settings[section] = copy.deepcopy(default_vals)
                applied.append(f"Added missing section '{section}' with default schema")
            elif isinstance(default_vals, dict) and isinstance(settings[section], dict):
                for k, v in default_vals.items():
                    if k not in settings[section]:
                        settings[section][k] = copy.deepcopy(v)
                        applied.append(f"Added missing key '{section}.{k}'")
        settings["_config_version"] = 3
        applied.append("Upgraded config version to 3")

    return settings, applied


def check_and_migrate_file(config_path: str) -> bool:
    """
    Checks config file on disk and applies migrations if version is behind.
    Uses AtomicConfigWriter to ensure crash-safe, atomic disk writes.
    Returns True if migrations were applied, False otherwise.
    """
    if not os.path.exists(config_path):
        return False

    import yaml
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        if not isinstance(data, dict):
            return False

        current_ver = data.get("_config_version", 1)
        if current_ver >= CURRENT_CONFIG_VERSION:
            return False

        migrated, applied = migrate_settings(data)
        if applied:
            logger.info(f"[ConfigMigration] Applying {len(applied)} migrations to {config_path}: {applied}")
            try:
                from config.atomic_writer import AtomicConfigWriter
                AtomicConfigWriter.write(config_path, migrated, create_backup=True)
            except Exception as w_err:
                logger.warning(f"Atomic write failed in migration ({w_err}), falling back to standard write.")
                with open(config_path, "w", encoding="utf-8") as f:
                    yaml.safe_dump(migrated, f, default_flow_style=False, sort_keys=False)
            return True
    except Exception as e:
        logger.warning(f"[ConfigMigration] Migration check failed for {config_path}: {e}")
        return False

    return False
