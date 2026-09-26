# ==============================================================================
# File: tests/mcp/test_bidirectional_mcp.py
# ==============================================================================

"""
Unit Test Suite for Stage 8:
Bi-Directional MCP Subsystem, Monika MCP Server, Quant Tool Execution,
and Debounced McpEventBridge.
"""

import asyncio
import tempfile
import time
from pathlib import Path
import pytest

from analysis.mcp.protocol import (
    JsonRpcRequest,
    LATEST_PROTOCOL_VERSION,
)
from analysis.mcp.server import MonikaMcpServer
from analysis.mcp.event_bridge import McpEventBridge
from database.session_db_wal import SessionDbWal
from database.fts5_cjk import Fts5SessionSearch


# ==============================================================================
# 1. MonikaMcpServer Protocol & Tool Execution Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_mcp_server_initialize_and_tool_list():
    server = MonikaMcpServer()

    # Test initialize request
    init_req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": LATEST_PROTOCOL_VERSION,
            "clientInfo": {"name": "test-client", "version": "1.0"},
        },
    }
    init_res = await server.handle_request(init_req)
    assert init_res is not None
    assert init_res["result"]["serverInfo"]["name"] == "monika-trading-server"
    assert "tools" in init_res["result"]["capabilities"]

    # Test tools/list request
    list_req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
    list_res = await server.handle_request(list_req)
    assert list_res is not None
    tool_names = {t["name"] for t in list_res["result"]["tools"]}

    assert "monika_execute_quant_calc" in tool_names
    assert "monika_search_session_memory" in tool_names
    assert "monika_get_status" in tool_names


@pytest.mark.asyncio
async def test_mcp_server_execute_quant_calc():
    server = MonikaMcpServer()

    code = "ans = math.factorial(6)\nprint(f'FACTORIAL: {ans}')"
    call_req = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "monika_execute_quant_calc",
            "arguments": {"code": code},
        },
    }

    res = await server.handle_request(call_req)
    assert res is not None
    tool_out = res["result"]["content"][0]["text"]
    # The output is JSON string of outcome
    assert "FACTORIAL: 720" in tool_out


# ==============================================================================
# 2. McpEventBridge Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_mcp_event_bridge_debounced_detection():
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_file = Path(tmp_dir) / "state_changes.log"
        test_file.write_text("initial log\n")

        bridge = McpEventBridge(debounce_seconds=0.05)
        bridge.add_path(test_file)

        events_received = []

        async def _on_change(path: Path, mtime: float):
            events_received.append((path, mtime))

        bridge.subscribe(_on_change)
        bridge.start()

        # Sleep briefly then modify file
        await asyncio.sleep(0.06)
        test_file.write_text("modified log\n")

        # Wait for debounce monitor loop
        await asyncio.sleep(0.12)
        bridge.stop()

        assert len(events_received) >= 1
        assert events_received[0][0] == test_file
