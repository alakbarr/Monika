"""
Compatibility facade shim for legacy settings.py.
Re-exports from canonical monika.core.config.settings.
"""

from __future__ import annotations

import monika.core.config.settings as _canonical

from monika.core.config.settings import (
    DEFAULT_MONTHLY_BUDGET_USD,
    get_installation_tier,
    get_settings,
    load_all_config,
    load_settings,
    load_settings_with_lkg,
    logger,
    validate_config,
)

__all__ = ['DEFAULT_MONTHLY_BUDGET_USD', 'get_installation_tier', 'get_settings', 'load_all_config', 'load_settings', 'load_settings_with_lkg', 'logger', 'validate_config']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
