# ==============================================================================
# File: tests/analysis/mcp/test_mcp_client_manager.py
# Description: Comprehensive unit tests for McpClientManager and McpBridgeHandler
# ==============================================================================

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from monika.infrastructure.mcp.client import (
    McpClientManager,
    MCPClientManager,
    McpBridgeHandler,
    McpServerProcess,
)
from monika.application.analysis.tools.registry import default_tool_registry
from monika.application.analysis.tools.unified_registry import unified_tool_registry
from monika.application.plugins.engine.context import PluginContext


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
    mgr = McpClientManager.get_instance(
        {
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
        }
    )

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
    mgr = McpClientManager.get_instance(
        {
            "mcp": {
                "client": {
                    "servers": {
                        "quant_calc": {
                            "transport": "stdio",
                        }
                    }
                }
            }
        }
    )

    mock_proc = MagicMock(spec=McpServerProcess)
    mock_proc.is_running = True
    mock_proc.timeout = 10.0
    mock_proc.call_tool = AsyncMock(return_value={"sharpe": 2.45})
    mgr.servers["quant_calc"] = mock_proc

    ctx = PluginContext("test_plugin", None)
    call_res = await ctx.call_mcp("quant_calc", "compute_metrics", {"symbol": "BTCUSD"})
    assert call_res["ok"] is True
    assert call_res["result"] == {"sharpe": 2.45}


@pytest.mark.asyncio
async def test_mcp_server_connection_start_fallback_on_not_implemented():
    """Verify MCPServerConnection.start() falls back to _PopenStdioProcess when create_subprocess_exec raises NotImplementedError."""
    from monika.infrastructure.mcp.client import MCPServerConnection, _PopenStdioProcess

    server = MCPServerConnection(
        "test_fallback",
        {
            "transport": "stdio",
            "command": "python",
            "args": ["-m", "dummy"],
        },
    )

    mock_fallback_proc = MagicMock(spec=_PopenStdioProcess)
    mock_fallback_proc.pid = 9999
    mock_fallback_proc.returncode = None
    mock_fallback_proc.stdin = MagicMock()
    mock_fallback_proc.stdin.write = MagicMock()
    mock_fallback_proc.stdin.drain = AsyncMock()
    mock_fallback_proc.stdout = MagicMock()
    mock_fallback_proc.stdout.readline = AsyncMock(return_value=b"")
    mock_fallback_proc.stderr = MagicMock()
    mock_fallback_proc.stderr.readline = AsyncMock(return_value=b"")
    mock_fallback_proc.terminate = MagicMock()
    mock_fallback_proc.kill = MagicMock()
    mock_fallback_proc.wait = AsyncMock(return_value=0)

    with patch("asyncio.create_subprocess_exec", side_effect=NotImplementedError()):
        with patch("asyncio.to_thread", new=AsyncMock(return_value=mock_fallback_proc)) as mock_to_thread:
            server.send_request = AsyncMock(return_value={"result": {"protocolVersion": "2024-11-05"}})
            server.send_notification = AsyncMock()

            started = await server.start()
            assert started is True
            assert server.process is mock_fallback_proc
            assert mock_to_thread.awaited
            assert mock_to_thread.call_args[0][0] is _PopenStdioProcess
            await server.stop()


@pytest.mark.asyncio
async def test_mcp_server_process_concurrent_start_idempotent():
    """Verify McpServerProcess handles concurrent start calls without spawning duplicate processes."""
    proc = McpServerProcess(
        "test_concurrent",
        {
            "transport": "stdio",
            "command": "python",
            "args": ["-m", "dummy"],
        },
    )

    mock_proc = MagicMock()
    mock_proc.pid = 12345
    mock_proc.returncode = None
    mock_proc.stdin = MagicMock()
    mock_proc.stdout = MagicMock()
    mock_proc.stdout.readline = AsyncMock(return_value=b"")
    mock_proc.stderr = MagicMock()
    mock_proc.stderr.readline = AsyncMock(return_value=b"")

    spawn_count = 0

    async def fake_create_subprocess(*args, **kwargs):
        nonlocal spawn_count
        spawn_count += 1
        await asyncio.sleep(0.01)  # Simulate startup delay to test race condition
        return mock_proc

    with patch("asyncio.create_subprocess_exec", side_effect=fake_create_subprocess):
        proc.send_request = AsyncMock(return_value={"result": {"protocolVersion": "2024-11-05"}})
        proc.send_notification = AsyncMock()

        # Run two concurrent starts
        res1, res2 = await asyncio.gather(proc.start(), proc.start())
        assert res1 is True
        assert res2 is True
        # Process should have been spawned exactly once
        assert spawn_count == 1
        assert proc.is_running is True

        # Sequential third start should return immediately without spawning
        res3 = await proc.start()
        assert res3 is True
        assert spawn_count == 1

        await proc.stop()


@pytest.mark.asyncio
async def test_mcp_client_manager_initialize_servers_idempotent():
    """Verify McpClientManager.initialize_servers is thread-safe and does not re-start active servers."""
    mgr = McpClientManager.get_instance(
        {
            "mcp": {
                "enabled": True,
                "client": {
                    "servers": {
                        "srv1": {
                            "enabled": True,
                            "transport": "stdio",
                            "command": "python",
                            "args": ["-m", "dummy"],
                        }
                    }
                },
            }
        }
    )

    mock_proc = MagicMock(spec=McpServerProcess)
    mock_proc.is_running = False
    mock_proc.ensure_started = AsyncMock(return_value=True)
    mock_proc.list_tools = AsyncMock(
        return_value=[
            {
                "name": "ping",
                "description": "ping tool",
                "inputSchema": {"type": "object", "properties": {}},
            }
        ]
    )

    async def fake_ensure_started():
        mock_proc.is_running = True
        return True

    mock_proc.ensure_started.side_effect = fake_ensure_started

    with patch("monika.infrastructure.mcp.client.McpServerProcess", return_value=mock_proc):
        # First concurrent run
        c1, c2 = await asyncio.gather(mgr.initialize_servers(), mgr.initialize_servers())
        assert c1 == 1
        assert c2 == 1
        assert "srv1" in mgr.servers

        # Sequential run
        c3 = await mgr.initialize_servers()
        assert c3 == 1

        await mgr.stop()
