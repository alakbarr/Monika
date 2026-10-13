"""
Backward-compatibility facade for mcp_serve.
Canonical location: monika.infrastructure.mcp.mcp_serve
"""

import sys
import monika.infrastructure.mcp.mcp_serve as _canonical

from monika.infrastructure.mcp.mcp_serve import McpServerDispatcher, main

__all__ = ["McpServerDispatcher", "main"]

sys.modules[__name__] = _canonical
