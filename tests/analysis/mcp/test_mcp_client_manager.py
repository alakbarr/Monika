# ==============================================================================
# File: tests/analysis/mcp/test_mcp_client_manager.py
# Description: Comprehensive unit tests for McpClientManager and McpBridgeHandler
# ==============================================================================

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from analysis.mcp.client import McpClientManager, MCPClientManager, McpBridgeHandler, McpServerProcess
from analysis.tools.registry import default_tool_registry
from analysis.tools.unified_registry import unified_tool_registry
from harness.context import PluginContext


@pytest.fixture(autouse=True)
def reset_singletons():
    McpClientManager.reset_instance()
    yield
    McpClientManager.reset_instance()


@pytest.mark.asyncio
async def test_mcp_client_manager_singleton_and_alias():
    # Verify singleton pattern
    mgr1 = McpClientManager.get_instance({"test": 1})
    mgr2 = McpClientManager.get_instance()
    assert mgr1 is mgr2
    assert mgr1.settings == {"test": 1}

    # Verify alias
    assert MCPClientManager is McpClientManager
    mgr3 = MCPClientManager.get_instance()
    assert mgr3 is mgr1


@pytest.mark.asyncio
async def test_mcp_client_manager_call_tool_mocked():
    mgr = McpClientManager.get_instance({
        "mcp": {
            "client": {
                "servers": {
                    "test_server": {
                        "transport": "stdio",
                        "command": "python",
                        "args": ["-m", "dummy"],
                    }
                }
            }
        }
    })

    mock_proc = MagicMock(spec=McpServerProcess)
    mock_proc.is_running = True
    mock_proc.timeout = 10.0
    mock_proc.call_tool = AsyncMock(return_value={"result": "hello_from_mcp"})
    mgr.servers["test_server"] = mock_proc

    res = await mgr.call_tool("test_server", "greet", {"name": "Monika"})
    assert res["ok"] is True
    assert res["result"] == {"result": "hello_from_mcp"}
    mock_proc.call_tool.assert_awaited_once_with("greet", {"name": "Monika"})


@pytest.mark.asyncio
async def test_mcp_client_manager_call_tool_unconfigured():
    mgr = McpClientManager.get_instance({})
    res = await mgr.call_tool("unknown_server", "tool", {})
    assert res["ok"] is False
    assert "not configured" in res["error"]


@pytest.mark.asyncio
async def test_mcp_bridge_handler_on_demand_start():
    mock_proc = MagicMock(spec=McpServerProcess)
    mock_proc.name = "lazy_server"
    mock_proc.is_running = False
    mock_proc.ensure_started = AsyncMock(return_value=True)
    mock_proc.call_tool = AsyncMock(return_value={"status": "ok"})

    handler = McpBridgeHandler(mock_proc, remote_tool_name="ping", local_tool_name="mcp_lazy_ping")
    res = await handler.execute({})
    assert res == {"status": "ok"}
    mock_proc.ensure_started.assert_awaited_once()
    mock_proc.call_tool.assert_awaited_once_with("ping", {})


@pytest.mark.asyncio
async def test_harness_context_call_mcp_integration():
    mgr = McpClientManager.get_instance({
        "mcp": {
            "client": {
                "servers": {
                    "quant_calc": {
                        "transport": "stdio",
                    }
                }
            }
        }
    })

    mock_proc = MagicMock(spec=McpServerProcess)
    mock_proc.is_running = True
    mock_proc.timeout = 10.0
    mock_proc.call_tool = AsyncMock(return_value={"sharpe": 2.45})
    mgr.servers["quant_calc"] = mock_proc

    ctx = PluginContext("test_plugin", None)
    call_res = await ctx.call_mcp("quant_calc", "compute_metrics", {"symbol": "BTCUSD"})
    assert call_res["ok"] is True
    assert call_res["result"] == {"sharpe": 2.45}
