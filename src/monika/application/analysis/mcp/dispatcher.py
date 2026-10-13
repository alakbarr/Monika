"""
Backward-compatibility facade for MonikaMcpDispatcher.
Canonical location: monika.infrastructure.mcp.dispatcher
"""

import sys
import monika.infrastructure.mcp.dispatcher as _canonical

from monika.infrastructure.mcp.dispatcher import MonikaMcpDispatcher

__all__ = ["MonikaMcpDispatcher"]

sys.modules[__name__] = _canonical
