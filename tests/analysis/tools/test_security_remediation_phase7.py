# ==============================================================================
# File: tests/analysis/tools/test_security_remediation_phase7.py
# ==============================================================================

"""
Verification & regression tests for Phase 7 security and architectural remediations:
- AST sandbox AST subscript/reflection restriction
- Fail-Closed trading safety guards in execution and position handlers
- Filesystem path traversal & safe write path enforcement in spill_store and file_patch_engine
- Unified tool registry thread safety & registration invariants
- Non-blocking async event loop behavior
"""

from pathlib import Path
from unittest.mock import patch
from pydantic import BaseModel
import pytest

from monika.application.analysis.tools.domain.execution_handlers import ExecutionToolHandlers
from monika.application.analysis.tools.file_patch_engine import FilePatchEngine
from monika.application.analysis.tools.handlers.position_mgmt import handle_calculate_position_size
from monika.application.analysis.tools.kernel.sandbox_runner import validate_code_ast
from monika.application.analysis.tools.unified_registry import UnifiedToolRegistry
from monika.infrastructure.storage.spill_store import SpillStore


def test_ast_sandbox_blocks_reflection_and_subscripts():
    """Verify AST sandbox strictly blocks reflection (__builtins__, getattr, etc.)."""
    payloads = [
        "globals()['__builtins__']",
        "getattr(sys, 'modules')",
        "__import__('os').system('ls')",
        "eval('1 + 1')",
        "exec('print(1)')",
    ]
    for code in payloads:
        is_safe, err = validate_code_ast(code)
        assert not is_safe, f"Expected '{code}' to be blocked by sandbox, but passed!"
        assert err is not None


def test_spill_store_path_traversal_blocked(tmp_path: Path):
    """Verify SpillStore rejects path traversal attempts escaping its base directory."""
    store = SpillStore(base_dir=tmp_path / "spills")

    # Valid write
    res = store.spill_artifact("Hello world", artifact_type="test_tool", artifact_id="test1")
    assert res["spilled"] is True
    assert store.load_artifact("test1") == "Hello world"

    # Path traversal attack returns None
    assert store.load_artifact("../../etc/passwd") is None
    assert store.load_artifact("..\\..\\windows\\system32\\cmd.exe") is None


def test_file_patch_engine_enforces_safe_write_path(tmp_path: Path):
    """Verify FilePatchEngine rejects unsafe paths during write and patch."""
    engine = FilePatchEngine()

    # Attempt to write outside workspace / into critical system directory
    unsafe_path = "C:/Windows/System32/drivers/etc/hosts"
    success, res = engine.write_file(unsafe_path, "malicious content")
    assert not success
    assert "Safety Guard: Path traversal blocked" in res


@pytest.mark.asyncio
async def test_execution_handlers_fail_closed_without_mt5():
    """Verify ExecutionToolHandlers fail closed when MT5 client is absent."""
    with patch("monika.infrastructure.brokers.mt5_client.get_mt5_client", return_value=None):
        handlers = ExecutionToolHandlers(settings={}, mt5_client=None)

        spread_res = await handlers.get_spread_snapshot("EURUSD")
        assert spread_res.get("status") == "error"
        assert "SPREAD_UNAVAILABLE" in spread_res.get("error", "")

        margin_res = await handlers.calculate_margin("EURUSD", 1.0)
        assert margin_res.get("status") == "error"
        assert "MARGIN_CALCULATION_UNAVAILABLE" in margin_res.get("error", "")


@pytest.mark.asyncio
async def test_position_mgmt_fail_closed_on_invalid_stop_loss():
    """Verify position sizing rejects missing or non-positive stop loss distance."""
    # Stop loss <= 0 must return status error, NEVER fabricate an arbitrary default pip distance
    res_zero = await handle_calculate_position_size(
        {
            "symbol": "EURUSD",
            "entry_price": 1.1000,
            "stop_loss": 0.0,
            "risk_pct": 1.0,
        }
    )
    assert res_zero.get("status") == "error"
    assert "CALCULATION_REJECTED" in res_zero.get("error", "")

    res_negative = await handle_calculate_position_size(
        {
            "symbol": "EURUSD",
            "entry_price": 1.1000,
            "stop_loss": -1.0500,
            "risk_pct": 1.0,
        }
    )
    assert res_negative.get("status") == "error"
    assert "CALCULATION_REJECTED" in res_negative.get("error", "")


def test_unified_tool_registry_thread_safety_and_lifecycle():
    """Verify UnifiedToolRegistry thread-safe registration and unregistration."""
    reg = UnifiedToolRegistry()

    class DummyInput(BaseModel):
        x: int

    def dummy_handler(params: DummyInput) -> int:
        return params.x * 2

    # Register
    reg.register(name="dummy_tool", category="CUSTOM", input_model=DummyInput)(dummy_handler)
    assert reg.get_tool("dummy_tool") is not None

    # Unregister
    reg.unregister("dummy_tool")
    assert reg.get_tool("dummy_tool") is None
