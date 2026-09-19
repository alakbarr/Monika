"""
Configuration schema versioning and forward-compatible migration engine.
"""

import logging
from pathlib import Path
from typing import Any, Callable, Dict, Tuple, Union

import yaml

logger = logging.getLogger("TradingAgent.Config.Migrations")

CURRENT_CONFIG_VERSION = 1
SUPPORT_FLOOR_VERSION = 1

# Registry of version migrations: target_version -> callable(config) -> migrated_config
MIGRATION_REGISTRY: Dict[int, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}


def register_migration(version: int):
    """Decorator to register a migration function for a specific target version."""
    def decorator(fn: Callable[[Dict[str, Any]], Dict[str, Any]]):
        MIGRATION_REGISTRY[version] = fn
        return fn
    return decorator


def get_config_version(config: Dict[str, Any]) -> int:
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


def migrate_config(config: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    """
    Evaluates config schema version and applies sequential migrations up to CURRENT_CONFIG_VERSION.
    Returns (migrated_config_dict, was_modified).
    """
    if not isinstance(config, dict):
        return config, False

    current_ver = get_config_version(config)

    # Baseline legacy config (no _config_version) -> assign current baseline version
    if current_ver == 0:
        config["_config_version"] = CURRENT_CONFIG_VERSION
        return config, True

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
    migrated_cfg = config.copy()

    while current_ver < CURRENT_CONFIG_VERSION:
        next_ver = current_ver + 1
        if next_ver in MIGRATION_REGISTRY:
            logger.info(f"Applying config migration v{current_ver} -> v{next_ver}")
            migrated_cfg = MIGRATION_REGISTRY[next_ver](migrated_cfg)
        migrated_cfg["_config_version"] = next_ver
        current_ver = next_ver
        was_migrated = True

    return migrated_cfg, was_migrated
