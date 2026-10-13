"""
Backward-compatibility facade for McpSchemaCache.
Canonical location: monika.infrastructure.mcp.mcp_schema_cache
"""

import sys
import monika.infrastructure.mcp.mcp_schema_cache as _canonical

from monika.infrastructure.mcp.mcp_schema_cache import McpSchemaCache

__all__ = ["McpSchemaCache"]

sys.modules[__name__] = _canonical
