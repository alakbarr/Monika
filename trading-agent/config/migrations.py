"""
Compatibility facade shim for legacy migrations.py.
Re-exports from canonical monika.core.config.migrations.
"""

from __future__ import annotations

import monika.core.config.migrations as _canonical

from monika.core.config.migrations import (
    CURRENT_CONFIG_VERSION,
    DEFAULT_SUBSETS,
    SUPPORT_FLOOR_VERSION,
    get_config_version,
    migrate_config,
    migrate_settings,
    register_migration,
    require_parseable_config,
)

__all__ = ['CURRENT_CONFIG_VERSION', 'DEFAULT_SUBSETS', 'SUPPORT_FLOOR_VERSION', 'get_config_version', 'migrate_config', 'migrate_settings', 'register_migration', 'require_parseable_config']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
