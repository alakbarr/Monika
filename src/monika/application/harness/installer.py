"""
Backward-compatibility facade for plugin installer.
Canonical location: monika.application.plugins.engine.installer
"""

import sys
import monika.application.plugins.engine.installer as _canonical

from monika.application.plugins.engine.installer import (
    get_community_catalog,
    list_all_plugins_status,
    run_pip_install,
    run_pip_uninstall,
    toggle_plugin_state,
    validate_package_spec,
)

__all__ = [
    "get_community_catalog",
    "list_all_plugins_status",
    "run_pip_install",
    "run_pip_uninstall",
    "toggle_plugin_state",
    "validate_package_spec",
]

sys.modules[__name__] = _canonical
