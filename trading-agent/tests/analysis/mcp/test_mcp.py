import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch

from analysis.mcp.protocol import (
    JsonRpcRequest,
    JsonRpcResponse,
    make_error_response,
    make_result_response,
    PARSE_ERROR,
    METHOD_NOT_FOUND,
)
from analysis.mcp.server import MonikaMcpServer
from analysis.mcp.client import McpClientManager, McpServerProcess, McpBridgeHandler
from analysis.tools.registry import default_tool_registry


def test_mcp_protocol_messages():
    req = JsonRpcRequest(method="tools/list", id=1)
    d = req.to_dict()
    assert d["jsonrpc"] == "2.0"
    assert d["method"] == "tools/list"
    assert d["id"] == 1

    resp = make_result_response(1, {"tools": []})
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == 1
    assert "tools" in resp["result"]

    err = make_error_response(2, METHOD_NOT_FOUND, "Not found")
    assert err["error"]["code"] == METHOD_NOT_FOUND
    assert err["error"]["message"] == "Not found"


@pytest.mark.asyncio
async def test_monika_mcp_server_lifecycle():
    server = MonikaMcpServer()

    # 1. Initialize
    init_req = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    init_res = await server.handle_request(init_req)
    assert init_res["id"] == 1
    assert "capabilities" in init_res["result"]
    assert "serverInfo" in init_res["result"]

    # 2. Notifications initialized
    notif = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    notif_res = await server.handle_request(notif)
    assert notif_res is None

    # 3. Ping
    ping_req = {"jsonrpc": "2.0", "id": 2, "method": "ping"}
    ping_res = await server.handle_request(ping_req)
    assert ping_res["result"] == {}

    # 4. Tools list
    tools_req = {"jsonrpc": "2.0", "id": 3, "method": "tools/list"}
    tools_res = await server.handle_request(tools_req)
    tools = tools_res["result"]["tools"]
    tool_names = [t["name"] for t in tools]
    assert "monika_get_status" in tool_names
    assert "monika_list_playbooks" in tool_names
    assert "monika_get_playbook" in tool_names


@pytest.mark.asyncio
async def test_monika_mcp_server_tool_execution():
    server = MonikaMcpServer(settings={"trading": {"mode": "paper"}})

    # Call monika_list_playbooks
    call_req = {
        "jsonrpc": "2.0",
        "id": 10,
        "method": "tools/call",
        "params": {
            "name": "monika_list_playbooks",
            "arguments": {},
        },
    }
    res = await server.handle_request(call_req)
    assert res["id"] == 10
    content = res["result"]["content"]
    assert len(content) > 0
    data = json.loads(content[0]["text"])
    assert data["status"] == "success"

    # Call monika_get_playbook
    call_pb = {
        "jsonrpc": "2.0",
        "id": 11,
        "method": "tools/call",
        "params": {
            "name": "monika_get_playbook",
            "arguments": {"name": "central_banks_framework"},
        },
    }
    pb_res = await server.handle_request(call_pb)
    assert pb_res["id"] == 11
    pb_content = json.loads(pb_res["result"]["content"][0]["text"])
    assert pb_content["status"] == "success"
    assert "content" in pb_content


@pytest.mark.asyncio
async def test_mcp_client_bridging():
    # Test bridging an external MCP server into default_tool_registry
    mock_server = MagicMock(spec=McpServerProcess)
    mock_server.call_tool = AsyncMock(return_value={"price": 1.0850})

    handler = McpBridgeHandler(mock_server, remote_tool_name="get_quote", local_tool_name="mcp_test_quote")
    default_tool_registry.register(
        handler,
        name="mcp_test_quote",
        category="MCP",
    )

    registered_h = default_tool_registry.get("mcp_test_quote")
    assert registered_h is not None

    result = await registered_h.execute({"symbol": "EURUSD"})
    assert result == {"price": 1.0850}
    mock_server.call_tool.assert_awaited_once_with("get_quote", {"symbol": "EURUSD"})
