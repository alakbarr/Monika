"""
Backward-compatibility facade for PluginContext.
Canonical location: monika.application.plugins.engine.context
"""

import sys
import monika.application.plugins.engine.context as _canonical

from monika.application.plugins.engine.context import PluginContext

__all__ = ["PluginContext"]

sys.modules[__name__] = _canonical
