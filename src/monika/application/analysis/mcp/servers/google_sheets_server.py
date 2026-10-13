"""
Backward-compatibility facade for GoogleSheetsMcpServer.
Canonical location: monika.infrastructure.mcp.servers.google_sheets_server
"""

import sys
import monika.infrastructure.mcp.servers.google_sheets_server as _canonical

from monika.infrastructure.mcp.servers.google_sheets_server import GoogleSheetsMcpServer

__all__ = ["GoogleSheetsMcpServer"]

sys.modules[__name__] = _canonical
