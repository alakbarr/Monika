# ==============================================================================
# File: analysis/mcp/protocol.py
# Description: Model Context Protocol (MCP) and JSON-RPC 2.0 Lightweight Transport
# Pure Python standard library implementation adhering to MCP 2024-11-05 spec.
# ==============================================================================

import json
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, field

# JSON-RPC 2.0 Standard Error Codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# MCP Protocol Version
LATEST_PROTOCOL_VERSION = "2024-11-05"


@dataclass
class JsonRpcRequest:
    method: str
    params: Optional[Dict[str, Any]] = None
    id: Optional[Union[str, int]] = None
    jsonrpc: str = "2.0"

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"jsonrpc": self.jsonrpc, "method": self.method}
        if self.params is not None:
            d["params"] = self.params
        if self.id is not None:
            d["id"] = self.id
        return d


@dataclass
class JsonRpcResponse:
    id: Optional[Union[str, int]]
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None
    jsonrpc: str = "2.0"

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"jsonrpc": self.jsonrpc, "id": self.id}
        if self.error is not None:
            d["error"] = self.error
        else:
            d["result"] = self.result if self.result is not None else {}
        return d


def make_error_response(
    req_id: Optional[Union[str, int]], code: int, message: str, data: Optional[Any] = None
) -> Dict[str, Any]:
    err = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": req_id, "error": err}


def make_result_response(req_id: Optional[Union[str, int]], result: Any) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}
