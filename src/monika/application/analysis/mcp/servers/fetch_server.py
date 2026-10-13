"""
Backward-compatibility facade for FetchMcpServer.
Canonical location: monika.infrastructure.mcp.servers.fetch_server
"""

import sys
import monika.infrastructure.mcp.servers.fetch_server as _canonical

from monika.infrastructure.mcp.servers.fetch_server import FetchMcpServer

__all__ = ["FetchMcpServer"]

sys.modules[__name__] = _canonical
