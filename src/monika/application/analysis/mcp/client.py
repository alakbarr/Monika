"""
Backward-compatibility facade for McpClientManager.
Canonical location: monika.infrastructure.mcp.client
"""

import sys
import monika.infrastructure.mcp.client as _canonical

from monika.infrastructure.mcp.client import (
    MCPClientManager,
    McpBridgeHandler,
    McpClientManager,
    McpServerProcess,
)

__all__ = [
    "McpClientManager",
    "MCPClientManager",
    "McpServerProcess",
    "McpBridgeHandler",
]

sys.modules[__name__] = _canonical
