"""
Backward-compatibility facade for monika.application.analysis.mcp.
Canonical location: monika.infrastructure.mcp
"""

import sys
import monika.infrastructure.mcp as _canonical

from monika.infrastructure.mcp.client import McpClientManager
from monika.infrastructure.mcp.server import MonikaMcpServer, run_mcp_server

__all__ = ["McpClientManager", "MonikaMcpServer", "run_mcp_server"]

sys.modules[__name__] = _canonical
