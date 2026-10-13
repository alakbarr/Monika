"""
Backward-compatibility facade for ExcelMcpServer.
Canonical location: monika.infrastructure.mcp.servers.excel_server
"""

import sys
import monika.infrastructure.mcp.servers.excel_server as _canonical

from monika.infrastructure.mcp.servers.excel_server import ExcelMcpServer

__all__ = ["ExcelMcpServer"]

sys.modules[__name__] = _canonical
