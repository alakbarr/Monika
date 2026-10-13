"""
Backward-compatibility facade for FilesystemMcpServer.
Canonical location: monika.infrastructure.mcp.servers.filesystem_server
"""

import sys
import monika.infrastructure.mcp.servers.filesystem_server as _canonical

from monika.infrastructure.mcp.servers.filesystem_server import FilesystemMcpServer

__all__ = ["FilesystemMcpServer"]

sys.modules[__name__] = _canonical
