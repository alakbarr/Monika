"""
Backward-compatibility facade for SqliteMcpServer.
Canonical location: monika.infrastructure.mcp.servers.sqlite_server
"""

import sys
import monika.infrastructure.mcp.servers.sqlite_server as _canonical

from monika.infrastructure.mcp.servers.sqlite_server import SqliteMcpServer

__all__ = ["SqliteMcpServer"]

sys.modules[__name__] = _canonical
