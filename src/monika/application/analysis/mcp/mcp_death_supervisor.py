"""
Backward-compatibility facade for McpDeathSupervisor.
Canonical location: monika.infrastructure.mcp.mcp_death_supervisor
"""

import sys
import monika.infrastructure.mcp.mcp_death_supervisor as _canonical

from monika.infrastructure.mcp.mcp_death_supervisor import McpDeathSupervisor

__all__ = ["McpDeathSupervisor"]

sys.modules[__name__] = _canonical
