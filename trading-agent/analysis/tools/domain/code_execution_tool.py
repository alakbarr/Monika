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


from pathlib import Path

_SCRIPTS_DIR = Path("data/user_scripts")


class SaveScriptInput(BaseModel):
    name: Optional[str] = Field(None, description="Script filename or identifier (e.g. 'custom_backtest' or 'sweep_scanner.py').")
    script_name: Optional[str] = Field(None, description="Alternative parameter for script filename.")
    code: str = Field(..., description="The complete Python code content to save.")
    description: Optional[str] = Field(None, description="Brief description of what the script does.")


@unified_tool_registry.register(
    name="save_script",
    category="COMPUTATION",
    input_model=SaveScriptInput,
)
async def handle_save_script(params: Any, context: Optional[Any] = None) -> Dict[str, Any]:
    """Save custom Python script to data/user_scripts/ for persistent reuse."""
    if isinstance(params, dict):
        p_name = params.get("script_name") or params.get("name") or "custom_script.py"
        p_code = params.get("code", "")
        p_desc = params.get("description")
    else:
        p_name = getattr(params, "script_name", None) or getattr(params, "name", None) or "custom_script.py"
        p_code = getattr(params, "code", "")
        p_desc = getattr(params, "description", None)

    _SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    clean_name = p_name.strip().replace(" ", "_")
    if not clean_name.endswith(".py"):
        clean_name += ".py"

    file_path = _SCRIPTS_DIR / clean_name
    header = f'"""\nDescription: {p_desc or "User custom script"}\n"""\n\n' if p_desc else ""
    full_code = header + p_code

    await asyncio.to_thread(file_path.write_text, full_code, encoding="utf-8")
    return {"status": "success", "file_path": str(file_path.resolve()), "name": clean_name, "message": f"Script saved successfully to {file_path.resolve()}"}


class ListSavedScriptsInput(BaseModel):
    pass


@unified_tool_registry.register(
    name="list_saved_scripts",
    category="COMPUTATION",
    input_model=ListSavedScriptsInput,
)
async def handle_list_saved_scripts(params: Any = None, context: Optional[Any] = None) -> Dict[str, Any]:
    """List all saved Python scripts stored in data/user_scripts/."""
    _SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    scripts = []
    for f in _SCRIPTS_DIR.glob("*.py"):
        try:
            stat = f.stat()
            first_line = ""
            with open(f, "r", encoding="utf-8") as s_file:
                first_few = [s_file.readline().strip() for _ in range(3)]
                first_line = " ".join([l for l in first_few if l])
            scripts.append({
                "name": f.name,
                "size_bytes": stat.st_size,
                "preview": first_line[:100],
            })
        except Exception:
            pass
    return {"status": "success", "count": len(scripts), "scripts": scripts}


class RunSavedScriptInput(BaseModel):
    name: Optional[str] = Field(None, description="The name of the saved script to execute (e.g. 'custom_backtest.py').")
    script_name: Optional[str] = Field(None, description="Alternative parameter for script name.")
    timeout: float = Field(60.0, ge=1.0, le=300.0, description="Execution timeout in seconds.")
    session_id: str = Field("default", description="Session identifier.")


@unified_tool_registry.register(
    name="run_saved_script",
    category="COMPUTATION",
    input_model=RunSavedScriptInput,
)
async def handle_run_saved_script(params: Any, context: Optional[Any] = None) -> Dict[str, Any]:
    """Run a previously saved script from data/user_scripts/."""
    if isinstance(params, dict):
        p_name = params.get("script_name") or params.get("name") or ""
        p_timeout = float(params.get("timeout", 60.0))
        p_session_id = str(params.get("session_id", "default"))
    else:
        p_name = getattr(params, "script_name", None) or getattr(params, "name", None) or ""
        p_timeout = float(getattr(params, "timeout", 60.0))
        p_session_id = str(getattr(params, "session_id", "default"))

    clean_name = p_name.strip().replace(" ", "_")
    if not clean_name.endswith(".py"):
        clean_name += ".py"

    file_path = _SCRIPTS_DIR / clean_name
    if not file_path.exists():
        return {"status": "error", "message": f"Script '{clean_name}' does not exist in data/user_scripts/."}

    code = await asyncio.to_thread(file_path.read_text, encoding="utf-8")
    exec_params = ExecuteCodeInput(code=code, timeout=p_timeout, session_id=p_session_id)
    out = await handle_execute_code(exec_params, context=context)
    return {"status": "success", "output": str(out), "script": clean_name}

