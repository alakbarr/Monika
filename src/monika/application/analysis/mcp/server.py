"""
Backward-compatibility facade for MonikaMcpServer.
Canonical location: monika.infrastructure.mcp.server
"""

import sys
import monika.infrastructure.mcp.server as _canonical

from monika.infrastructure.mcp.server import MonikaMcpServer, run_mcp_server

__all__ = ["MonikaMcpServer", "run_mcp_server"]

sys.modules[__name__] = _canonical
