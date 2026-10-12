"""
Compatibility facade shim for legacy config_migrations.py.
Re-exports from canonical monika.core.config.config_migrations.
"""

from __future__ import annotations

import monika.core.config.config_migrations as _canonical

from monika.core.config.config_migrations import (
    CURRENT_CONFIG_VERSION,
    check_and_migrate_file,
    logger,
    migrate_settings,
)

__all__ = ['CURRENT_CONFIG_VERSION', 'check_and_migrate_file', 'logger', 'migrate_settings']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
