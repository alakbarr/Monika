"""
Backward-compatibility facade for MCP servers package.
Canonical location: monika.infrastructure.mcp.servers
"""

import sys
import monika.infrastructure.mcp.servers as _canonical

sys.modules[__name__] = _canonical
