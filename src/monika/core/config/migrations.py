"""
Configuration schema versioning and forward-compatible migration engine.
Single Source of Truth for settings.yaml schema migrations.
"""

from __future__ import annotations

import copy
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any, Union

import yaml

logger = logging.getLogger("TradingAgent.Config.Migrations")

CURRENT_CONFIG_VERSION = 3
SUPPORT_FLOOR_VERSION = 1

DEFAULT_SUBSETS: dict[str, Any] = {
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
    "security": {
        "quarantine_days": 30,
        "prompt_injection_threshold": 0.85,
        "ssrf_allowed_ports": [80, 443],
        "denial_breaker_threshold": 5,
        "audit_logging": True,
    },
}

MIGRATION_REGISTRY: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {}


def register_migration(version: int):
    """Decorator to register a migration function for a specific target version."""

    def decorator(fn: Callable[[dict[str, Any]], dict[str, Any]]):
        MIGRATION_REGISTRY[version] = fn
        return fn

    return decorator


def get_config_version(config: dict[str, Any]) -> int:
    """Returns the integer schema version of the config dictionary."""
    if not isinstance(config, dict):
        return 0
    return int(config.get("_config_version", 0))


def require_parseable_config(path: Union[str, Path]) -> None:
    """
    Fail-closed validation: verify that the configuration file exists and has valid YAML syntax
    before the agent initializes execution loops.
    """
    target = Path(path).resolve()
    if not target.exists():
        raise SystemExit(f"[FATAL] Configuration file not found: {target}")

    try:
        raw_text = target.read_text(encoding="utf-8")
        parsed = yaml.safe_load(raw_text)
        if not isinstance(parsed, dict):
            raise ValueError(f"Root YAML element must be a dictionary, got {type(parsed).__name__}")
    except Exception as exc:
        logger.critical(f"Fail-closed: configuration at {target} is unparseable: {exc}")
        raise SystemExit(
            f"\n[FATAL] Configuration file has syntax or parse errors: {target}\n"
            f"Details: {exc}\n"
            "Aborting startup to prevent running with unintended or corrupted defaults.\n"
        ) from exc


def _apply_v1_to_v2(cfg: dict[str, Any]) -> dict[str, Any]:
    """Applies schema updates from v1 to v2."""
    settings = copy.deepcopy(cfg)
    v2_subsets = ["token_budget", "execution", "paper_trading", "learning_loop"]
    for section in v2_subsets:
        default_vals = DEFAULT_SUBSETS.get(section, {})
        if section not in settings:
            settings[section] = copy.deepcopy(default_vals)
        elif isinstance(default_vals, dict) and isinstance(settings[section], dict):
            for k, v in default_vals.items():
                if k not in settings[section]:
                    settings[section][k] = copy.deepcopy(v)
    settings["_config_version"] = 2
    return settings


def _apply_v2_to_v3(cfg: dict[str, Any]) -> dict[str, Any]:
    """Applies schema updates from v2 to v3."""
    settings = copy.deepcopy(cfg)
    v3_subsets = ["harness", "evals", "benchmark", "security"]
    for section in v3_subsets:
        default_vals = DEFAULT_SUBSETS.get(section, {})
        if section not in settings:
            settings[section] = copy.deepcopy(default_vals)
        elif isinstance(default_vals, dict) and isinstance(settings[section], dict):
            for k, v in default_vals.items():
                if k not in settings[section]:
                    settings[section][k] = copy.deepcopy(v)
    settings["_config_version"] = 3
    return settings


MIGRATION_REGISTRY[2] = _apply_v1_to_v2
MIGRATION_REGISTRY[3] = _apply_v2_to_v3


def migrate_settings(raw_settings: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """
    Applies schema migrations to in-memory settings dictionary.

    Returns:
        (migrated_settings, list_of_applied_migrations)
    """
    settings = copy.deepcopy(raw_settings)
    applied: list[str] = []

    version = settings.get("_config_version", 1)

    if version < 2:
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
        v3_subsets = ["harness", "evals", "benchmark", "security"]
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
        version = 3

    return settings, applied


def migrate_config(config: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """
    Evaluates config schema version and applies sequential migrations up to CURRENT_CONFIG_VERSION.
    Returns (migrated_config_dict, was_modified).
    """
    if not isinstance(config, dict):
        return config, False

    current_ver = get_config_version(config)

    # Baseline legacy config (no _config_version) -> assign current baseline version and backfill required defaults
    if current_ver == 0:
        migrated, _ = migrate_settings(config)
        migrated["_config_version"] = CURRENT_CONFIG_VERSION
        return migrated, True

    if current_ver < SUPPORT_FLOOR_VERSION:
        raise ValueError(
            f"Config schema version {current_ver} is below minimum supported floor {SUPPORT_FLOOR_VERSION}. "
            "Please regenerate or manually update config."
        )

    if current_ver > CURRENT_CONFIG_VERSION:
        logger.warning(
            f"Config version {current_ver} is newer than software version {CURRENT_CONFIG_VERSION}. "
            "Running without schema modifications."
        )
        return config, False

    was_migrated = False
    migrated_cfg = copy.deepcopy(config)

    while current_ver < CURRENT_CONFIG_VERSION:
        next_ver = current_ver + 1
        if next_ver in MIGRATION_REGISTRY:
            logger.info(f"Applying config migration v{current_ver} -> v{next_ver}")
            migrated_cfg = MIGRATION_REGISTRY[next_ver](migrated_cfg)
        migrated_cfg["_config_version"] = next_ver
        current_ver = next_ver
        was_migrated = True

    return migrated_cfg, was_migrated


__all__ = [
    "CURRENT_CONFIG_VERSION",
    "SUPPORT_FLOOR_VERSION",
    "register_migration",
    "get_config_version",
    "require_parseable_config",
    "migrate_config",
    "migrate_settings",
    "DEFAULT_SUBSETS",
]
