# ==============================================================================
# File: analysis/tools/domain/code_execution_tool.py
# ==============================================================================

"""
Domain tool for Programmatic Tool Calling (PTC) and Sandboxed Code Execution.
Institutional-grade engine turn protection architecture.

Allows LLM models and specialist subagents to write and execute Python scripts
that run with persistent state and can batch-call internal Monika tools
without burning context window roundtrips.
"""

from __future__ import annotations

import atexit
import asyncio
import logging
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

from analysis.tools.kernel.code_execution_rpc import CodeExecutionRpcServer
from analysis.tools.kernel.persistent_session_kernel import PersistentSessionKernel
from analysis.tools.unified_registry import unified_tool_registry

logger = logging.getLogger("TradingAgent.Tools.CodeExecution")

# Registry of active session kernels
_ACTIVE_KERNELS: Dict[str, PersistentSessionKernel] = {}
_ACTIVE_RPC_SERVERS: Dict[str, CodeExecutionRpcServer] = {}


def shutdown_all_kernels() -> None:
    """Atexit hook to terminate all active background kernels and RPC servers."""
    for kernel in list(_ACTIVE_KERNELS.values()):
        try:
            kernel.terminate()
        except Exception:
            pass
    _ACTIVE_KERNELS.clear()

    for rpc_server in list(_ACTIVE_RPC_SERVERS.values()):
        try:
            rpc_server.stop()
        except Exception:
            pass
    _ACTIVE_RPC_SERVERS.clear()


atexit.register(shutdown_all_kernels)


def get_or_create_session_kernel(
    session_id: str = "default",
    timeout_seconds: float = 120.0,
    loop: Optional[asyncio.AbstractEventLoop] = None,
) -> PersistentSessionKernel:
    """Get existing or instantiate new persistent session kernel with loopback RPC."""
    if session_id in _ACTIVE_KERNELS:
        kernel = _ACTIVE_KERNELS[session_id]
        if kernel._is_alive and kernel.proc and kernel.proc.poll() is None:
            return kernel

    # Initialize RPC server first
    if session_id not in _ACTIVE_RPC_SERVERS:
        rpc_server = CodeExecutionRpcServer(loop=loop)
        rpc_server.start()
        _ACTIVE_RPC_SERVERS[session_id] = rpc_server
    else:
        rpc_server = _ACTIVE_RPC_SERVERS[session_id]

    kernel = PersistentSessionKernel(
        session_id=session_id,
        timeout_seconds=timeout_seconds,
        rpc_server=rpc_server,
    )
    _ACTIVE_KERNELS[session_id] = kernel
    return kernel


class ExecuteCodeInput(BaseModel):
    """
    Input schema for programmatic code execution.
    Executes Python scripts with in-memory persistence and internal tool-calling capability.
    """
    code: str = Field(
        ...,
        description="The Python code to execute. Can import 'monika_tools' to invoke Monika tools via call_tool(name, **kwargs)."
    )
    reset: bool = Field(
        False,
        description="If True, clears the session variable namespace before executing this code."
    )
    timeout: float = Field(
        60.0,
        ge=1.0,
        le=300.0,
        description="Execution timeout in seconds (default 60s, max 300s)."
    )
    session_id: str = Field(
        "default",
        description="Session identifier to isolate execution namespaces across different analysis workflows."
    )


@unified_tool_registry.register(
    name="execute_code",
    category="COMPUTATION",
    input_model=ExecuteCodeInput,
)
async def handle_execute_code(
    params: ExecuteCodeInput,
    context: Optional[Any] = None,
) -> str:
    """
    Execute Python code in the persistent session sandbox.
    """
    current_loop = asyncio.get_running_loop()
    kernel = get_or_create_session_kernel(
        session_id=params.session_id,
        timeout_seconds=params.timeout,
        loop=current_loop,
    )

    if params.reset:
        reset_msg, _ = kernel.reset()
        if not params.code.strip():
            return reset_msg

    # Execute in a thread pool to avoid blocking the asyncio event loop
    output, success = await asyncio.to_thread(
        kernel.execute,
        params.code,
        params.timeout,
    )

    status_tag = "[SUCCESS]" if success else "[ERROR/WARNING]"
    return f"{status_tag}\n{output}"
