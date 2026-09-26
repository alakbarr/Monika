# ==============================================================================
# File: tests/analysis/mcp/test_mcp_dispatcher_and_routes.py
# ==============================================================================

import pytest
from httpx import AsyncClient, ASGITransport
from analysis.mcp.dispatcher import MonikaMcpDispatcher
from cli.subcommands.mcp import McpSubcommand
from logging_observability.dashboard.api import app


@pytest.mark.asyncio
async def test_mcp_dispatcher_tool_list():
    dispatcher = MonikaMcpDispatcher()
    tools = dispatcher.get_tool_list()
    assert len(tools) > 0

    tool_names = {t["name"] for t in tools}
    # Verify built-in quant tools are included
    assert "monika_get_status" in tool_names
    assert "monika_get_open_positions" in tool_names
    assert "monika_get_macro_regime" in tool_names


@pytest.mark.asyncio
async def test_mcp_dispatcher_quant_call():
    dispatcher = MonikaMcpDispatcher()
    req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "monika_get_status",
            "arguments": {},
        },
    }
    resp = await dispatcher.handle_request(req)
    assert resp is not None
    assert resp["id"] == 1
    assert "result" in resp
    content = resp["result"]["content"]
    assert "kill_switch" in content[0]["text"]
    assert "mode" in content[0]["text"]


@pytest.mark.asyncio
async def test_mcp_cli_subcommand_instantiation():
    subcmd = McpSubcommand()
    assert subcmd.name == "mcp"


@pytest.mark.asyncio
async def test_dashboard_mcp_routes():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Test tools listing
        resp = await ac.get("/api/mcp/tools")
        assert resp.status_code == 200
        data = resp.json()
        assert "tools" in data
        assert data["count"] > 0

        # Test JSON-RPC direct POST message
        rpc_req = {
            "jsonrpc": "2.0",
            "id": 42,
            "method": "initialize",
            "params": {},
        }
        post_resp = await ac.post("/api/mcp/messages", json=rpc_req)
        assert post_resp.status_code == 200
        body = post_resp.json()
        assert body["id"] == 42
        assert body["result"]["serverInfo"]["name"] == "monika-agent"
