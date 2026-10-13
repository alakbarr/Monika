"""
Backward-compatibility facade for MCP protocol.
Canonical location: monika.infrastructure.mcp.protocol
"""

import sys
import monika.infrastructure.mcp.protocol as _canonical

from monika.infrastructure.mcp.protocol import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    LATEST_PROTOCOL_VERSION,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    JsonRpcRequest,
    JsonRpcResponse,
    make_error_response,
    make_result_response,
)

__all__ = [
    "PARSE_ERROR",
    "INVALID_REQUEST",
    "METHOD_NOT_FOUND",
    "INVALID_PARAMS",
    "INTERNAL_ERROR",
    "LATEST_PROTOCOL_VERSION",
    "JsonRpcRequest",
    "JsonRpcResponse",
    "make_error_response",
    "make_result_response",
]

sys.modules[__name__] = _canonical
