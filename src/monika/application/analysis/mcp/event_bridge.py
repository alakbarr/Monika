"""
Backward-compatibility facade for McpEventBridge.
Canonical location: monika.infrastructure.mcp.event_bridge
"""

import sys
import monika.infrastructure.mcp.event_bridge as _canonical

from monika.infrastructure.mcp.event_bridge import McpEventBridge

__all__ = ["McpEventBridge"]

sys.modules[__name__] = _canonical
