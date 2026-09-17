"""
Unit tests for Programmatic Tool Calling (PTC) execution (H2).
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from analysis.tools.handlers.ptc_handler import PTCHandler


@pytest.mark.asyncio
async def test_ptc_pure_python_execution():
    """H2: PTC executes pure Python calculations without tool calls."""
    mock_executor = MagicMock()
    handler = PTCHandler(tool_executor=mock_executor)

    code = """
x = 10
y = 32
print(f"Result={x + y}")
"""
    res = await handler.execute(code)
    assert res["status"] == "success"
    assert "Result=42" in res["stdout"]
    assert res["tool_calls_made"] == 0


@pytest.mark.asyncio
async def test_ptc_tool_rpc_invocation():
    """H2: Subprocess can invoke tools via TCP RPC bridge back to tool executor."""
    mock_executor = MagicMock()
    mock_executor.execute = AsyncMock(return_value={"symbol": "EURUSD", "close": 1.0850})

    handler = PTCHandler(tool_executor=mock_executor)

    code = """
resp = tools.call_tool("get_price_history", symbol="EURUSD")
print(f"Fetched price: {resp.get('close')}")
"""
    res = await handler.execute(code, allowed_tools=["get_price_history"])
    assert res["status"] == "success"
    assert "Fetched price: 1.085" in res["stdout"]
    assert res["tool_calls_made"] == 1
    mock_executor.execute.assert_called_once()


@pytest.mark.asyncio
async def test_ptc_syntax_error_handling():
    """H2: Python syntax error in agent script is handled cleanly without crashing."""
    mock_executor = MagicMock()
    handler = PTCHandler(tool_executor=mock_executor)

    code = "def bad_syntax(:"
    res = await handler.execute(code)
    assert res["status"] == "error"
    assert "SyntaxError" in res["stderr"] or "SyntaxError" in res["stdout"]


@pytest.mark.asyncio
async def test_ptc_env_sanitization_prevents_secret_leak(monkeypatch):
    """P0-11: Verify sensitive environment variables are stripped from subprocess env."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-sensitive-secret-token")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://admin:supersecret@localhost/db")
    monkeypatch.setenv("MT5_PASSWORD", "super_secret_password")

    mock_executor = MagicMock()
    handler = PTCHandler(tool_executor=mock_executor)

    code = """
import os
print("KEY=" + os.environ.get("ANTHROPIC_API_KEY", "NONE"))
print("DB=" + os.environ.get("DATABASE_URL", "NONE"))
print("MT5=" + os.environ.get("MT5_PASSWORD", "NONE"))
"""
    res = await handler.execute(code)
    assert res["status"] == "success"
    assert "KEY=NONE" in res["stdout"]
    assert "DB=NONE" in res["stdout"]
    assert "MT5=NONE" in res["stdout"]
