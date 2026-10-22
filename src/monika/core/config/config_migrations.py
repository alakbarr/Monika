"""
Configuration Version Migrations Backward Compatibility Facade.

Single Source of Truth has been unified into `monika.core.config.migrations`.
This module preserves existing import paths for compatibility.
"""

from __future__ import annotations

from monika.core.config.migrations import (
    CURRENT_CONFIG_VERSION,
    DEFAULT_SUBSETS,
    get_config_version,
    migrate_config,
    migrate_settings,
    register_migration,
    require_parseable_config,
)

__all__ = [
    "CURRENT_CONFIG_VERSION",
    "DEFAULT_SUBSETS",
    "get_config_version",
    "migrate_config",
    "migrate_settings",
    "register_migration",
    "require_parseable_config",
]
