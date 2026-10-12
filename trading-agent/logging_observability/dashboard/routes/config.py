"""
Compatibility facade shim for legacy config.py.
Re-exports from canonical monika.interfaces.dashboard.routes.config.
"""

from __future__ import annotations

import monika.interfaces.dashboard.routes.config as _canonical

from monika.interfaces.dashboard.routes.config import (
    ConfigUpdateRequest,
    NON_SENSITIVE_KEYS,
    SENSITIVE_KEY_PATTERN,
    config_router,
    get_all_plugin_config_schemas,
    get_config_schema,
    get_config_settings,
    get_plugin_config_schema,
    logger,
    router,
    update_config_settings,
)

__all__ = ['ConfigUpdateRequest', 'NON_SENSITIVE_KEYS', 'SENSITIVE_KEY_PATTERN', 'config_router', 'get_all_plugin_config_schemas', 'get_config_schema', 'get_config_settings', 'get_plugin_config_schema', 'logger', 'router', 'update_config_settings']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
