# ==============================================================================
# File: tests/tools/test_phase2_ptc_and_sandboxes.py
# ==============================================================================

"""
Unit Test Suite for Phase 2:
Programmatic Tool Calling (PTC), Persistent Session Kernel, Multi-Backend Sandbox,
MCP Server, OAuth PKCE Flow, and Interactive Tools.
"""

import asyncio
import json
import socket
import sys
import tempfile
from pathlib import Path
import pytest

from analysis.tools.kernel.code_execution_rpc import (
    CodeExecutionRpcServer,
    generate_monika_tools_client_code,
)
from analysis.tools.kernel.persistent_session_kernel import PersistentSessionKernel
from analysis.tools.domain.code_execution_tool import (
    ExecuteCodeInput,
    handle_execute_code,
)
from execution.backends.local_backend import LocalTerminalBackend
from analysis.mcp.oauth_handler import (
    generate_pkce_pair,
    OAuthTokenStorage,
)
from analysis.mcp.mcp_serve import McpServerDispatcher
from analysis.tools.domain.clarify_tool import ClarifyInput, handle_clarify_with_user
from analysis.tools.domain.kanban_tools import KanbanBoardInput, handle_manage_kanban_board
from analysis.tools.domain.computer_use_tool import ComputerUseInput, handle_computer_use
from analysis.tools.unified_registry import unified_tool_registry


# ==============================================================================
# 1. CodeExecutionRpcServer Tests
# ==============================================================================

def test_code_execution_rpc_lifecycle_and_auth():
    def mock_dispatch(name, args):
        return f"MOCK_RESULT_{name}_{args.get('val', '')}"

    server = CodeExecutionRpcServer(
        allowed_tools={"mock_tool"},
        max_tool_calls=5,
        dispatch_fn=mock_dispatch,
    )
    port = server.start()
    try:
        assert port > 0

        # Helper to send RPC
        def send_rpc(payload: dict) -> dict:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect(("127.0.0.1", port))
            s.sendall((json.dumps(payload) + "\n").encode("utf-8"))
            resp = s.recv(4096).decode("utf-8").strip()
            s.close()
            return resp

        # 1. Valid authorized call
        valid_payload = {
            "token": server.rpc_token,
            "tool": "mock_tool",
            "args": {"val": 123},
        }
        resp = send_rpc(valid_payload)
        assert resp == "MOCK_RESULT_mock_tool_123"

        # 2. Unauthorized token
        invalid_payload = {
            "token": "wrong_token",
            "tool": "mock_tool",
            "args": {},
        }
        resp_err = json.loads(send_rpc(invalid_payload))
        assert "Unauthorized" in resp_err.get("error", "")

        # 3. Disallowed tool
        disallowed_payload = {
            "token": server.rpc_token,
            "tool": "forbidden_tool",
            "args": {},
        }
        resp_disallowed = json.loads(send_rpc(disallowed_payload))
        assert "not allowed" in resp_disallowed.get("error", "")

    finally:
        server.stop()


def test_monika_tools_client_code_generation():
    client_code = generate_monika_tools_client_code(
        port=12345,
        token="test_token_abc",
        allowed_tools={"get_market_quote", "read_database_records"},
    )
    assert "_RPC_PORT = 12345" in client_code
    assert "_RPC_TOKEN = \"test_token_abc\"" in client_code
    assert "def call_tool(" in client_code
    assert "def get_market_quote(" in client_code


# ==============================================================================
# 2. PersistentSessionKernel Tests
# ==============================================================================

def test_persistent_session_kernel_state_retention():
    kernel = PersistentSessionKernel(session_id="test_persistence", timeout_seconds=15.0)
    try:
        # Cell 1: Define variable and helper function
        code1 = """
a = 100
b = 250
def calculate_sum(x, y):
    return x + y
print(f"CELL1_INIT: a={a}, b={b}")
"""
        out1, success1 = kernel.execute(code1)
        assert success1
        assert "CELL1_INIT: a=100, b=250" in out1

        # Cell 2: Reuse variables and function from Cell 1
        code2 = """
result = calculate_sum(a, b)
print(f"CELL2_SUM={result}")
"""
        out2, success2 = kernel.execute(code2)
        assert success2
        assert "CELL2_SUM=350" in out2

        # Cell 3: Reset state
        reset_msg, reset_ok = kernel.reset()
        assert reset_ok

        # Cell 4: Check that 'a' is no longer defined
        code3 = "print(a)"
        out3, success3 = kernel.execute(code3)
        assert not success3
        assert "NameError" in out3

    finally:
        kernel.terminate()


# ==============================================================================
# 3. Domain Code Execution Tool Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_handle_execute_code_domain_tool():
    from analysis.tools.domain.code_execution_tool import shutdown_all_kernels
    try:
        input_params = ExecuteCodeInput(
            code="nums = [1, 2, 3, 4, 5]\nprint(f'SUM={sum(nums)}')",
            reset=True,
            timeout=10.0,
            session_id="test_domain_exec",
        )
        result = await handle_execute_code(input_params)
        assert "[SUCCESS]" in result
        assert "SUM=15" in result
    finally:
        shutdown_all_kernels()


# ==============================================================================
# 4. LocalTerminalBackend Tests
# ==============================================================================

def test_local_terminal_backend():
    backend = LocalTerminalBackend()
    assert backend.is_alive()

    # Test command execution
    cmd = "echo HELLO_MONIKA"
    stdout, stderr, code = backend.execute(cmd, timeout=10.0)
    assert code == 0
    assert "HELLO_MONIKA" in stdout

    # Test file operations
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_file = Path(tmp_dir) / "test_io.txt"
        assert backend.write_file(str(test_file), "Content Line 1\nContent Line 2\n")
        read_content = backend.read_file(str(test_file))
        assert "Content Line 1" in read_content


# ==============================================================================
# 5. MCP OAuth PKCE & Token Storage Tests
# ==============================================================================

def test_oauth_pkce_generation():
    verifier, challenge = generate_pkce_pair()
    assert len(verifier) >= 43
    assert len(challenge) > 20
    assert verifier != challenge


def test_oauth_token_storage():
    with tempfile.TemporaryDirectory() as tmp_dir:
        token_path = Path(tmp_dir) / "test_tokens.json"
        storage = OAuthTokenStorage(token_path)

        assert storage.load_tokens() is None

        test_data = {"access_token": "acc_123", "refresh_token": "ref_456", "expires_in": 3600}
        assert storage.save_tokens(test_data)

        loaded = storage.load_tokens()
        assert loaded == test_data

        storage.clear()
        assert storage.load_tokens() is None


# ==============================================================================
# 6. McpServerDispatcher Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_mcp_server_dispatcher_protocol():
    dispatcher = McpServerDispatcher(name="test-monika-mcp")

    # 1. Initialize
    init_req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {},
    }
    init_resp = await dispatcher.handle_request(init_req)
    assert init_resp["id"] == 1
    assert init_resp["result"]["serverInfo"]["name"] == "test-monika-mcp"
    assert "tools" in init_resp["result"]["capabilities"]

    # 2. Tools list
    list_req = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {},
    }
    list_resp = await dispatcher.handle_request(list_req)
    assert list_resp["id"] == 2
    tools = list_resp["result"]["tools"]
    assert len(tools) > 0
    tool_names = {t["name"] for t in tools}
    assert "execute_code" in tool_names

    # 3. Ping
    ping_req = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "ping",
        "params": {},
    }
    ping_resp = await dispatcher.handle_request(ping_req)
    assert ping_resp["id"] == 3
    assert ping_resp["result"] == {}


# ==============================================================================
# 7. Interactive Tools Tests (Clarify, Kanban, ComputerUse)
# ==============================================================================

@pytest.mark.asyncio
async def test_clarify_tool():
    params = ClarifyInput(
        question="Select risk tolerance level?",
        options=["conservative", "moderate", "aggressive"],
        default_choice="moderate",
        urgency="medium",
    )
    result_str = await handle_clarify_with_user(params)
    parsed = json.loads(result_str)
    assert parsed["type"] == "clarification_request"
    assert parsed["question"] == "Select risk tolerance level?"
    assert "moderate" in parsed["options"]


@pytest.mark.asyncio
async def test_kanban_tool():
    # 1. Add task
    add_param = KanbanBoardInput(
        action="add",
        title="Analyze EURUSD Liquidity Sweeps",
        column="backlog",
        priority="high",
        notes="Inspect 4H fair value gaps",
    )
    add_resp = await handle_manage_kanban_board(add_param)
    assert "successfully added" in add_resp

    # 2. List tasks
    list_param = KanbanBoardInput(action="list")
    list_resp = await handle_manage_kanban_board(list_param)
    assert "# Kanban Board Status" in list_resp
    assert "Analyze EURUSD Liquidity Sweeps" in list_resp


@pytest.mark.asyncio
async def test_computer_use_safeguards():
    # Out of bounds coordinates check
    params = ComputerUseInput(
        action="mouse_move",
        coordinate=[-100, 999999],
    )
    resp = await handle_computer_use(params)
    # Either pyautogui missing error or coordinate bounds error
    assert ("out of screen bounds" in resp.lower() or "gui automation unavailable" in resp.lower())
