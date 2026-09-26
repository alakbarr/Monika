# ==============================================================================
# File: tests/tools/test_unified_tooling.py
# ==============================================================================

"""
Unit Test Suite for Stage 4:
Unified Modular Tooling, Parameter Coercion, ToolDispatcher,
and 3-Tier Execution Sandboxing.
"""

import asyncio
import tempfile
from pathlib import Path
import pytest

from analysis.tools.core.definition import (
    ExecutionTier,
    ToolCategory,
    ToolDefinition,
    ToolParameter,
)
from analysis.tools.core.coercion import coerce_arguments, coerce_value
from analysis.tools.core.decorator import monika_tool
from analysis.tools.core.toolset_registry import ToolsetRegistry
from analysis.tools.core.dispatcher import ToolDispatcher
from analysis.tools.environments.tier1_inprocess import Tier1InProcessEnvironment
from analysis.tools.environments.tier2_kernel import Tier2HostKernelEnvironment
from analysis.tools.environments.tier3_docker import Tier3DockerEnvironment
from database.session_db_wal import SessionDbWal


# ==============================================================================
# 1. Parameter Coercion Tests
# ==============================================================================

def test_coercion_types():
    param_int = ToolParameter(name="period", type_name="int", default=14)
    param_bool = ToolParameter(name="use_filter", type_name="bool", default=False)
    param_dict = ToolParameter(name="config", type_name="dict", default={})
    param_list = ToolParameter(name="symbols", type_name="list", default=[])

    spec = {
        "period": param_int,
        "use_filter": param_bool,
        "config": param_dict,
        "symbols": param_list,
    }

    raw = {
        "period": "20.0",
        "use_filter": "true",
        "config": '{"ema_len": 50}',
        "symbols": "EURUSD,GBPUSD,XAUUSD",
    }

    coerced = coerce_arguments(spec, raw)
    assert coerced["period"] == 20
    assert coerced["use_filter"] is True
    assert coerced["config"] == {"ema_len": 50}
    assert coerced["symbols"] == ["EURUSD", "GBPUSD", "XAUUSD"]


# ==============================================================================
# 2. Decorator & Registry Tests
# ==============================================================================

@monika_tool(
    name="compute_atr",
    description="Calculate Average True Range for symbol.",
    category=ToolCategory.QUANT_TRADING,
    tier=ExecutionTier.TIER_1_INPROCESS,
)
def compute_atr_sample(symbol: str, period: int = 14) -> float:
    """
    Calculate Average True Range for symbol.

    symbol: The trading ticker symbol.
    period: The lookback periods for smoothing.
    """
    return 0.0025


def test_monika_tool_decorator_and_registry():
    registry = ToolsetRegistry()
    tool_def = registry.register(compute_atr_sample)

    assert tool_def.name == "compute_atr"
    assert tool_def.category == ToolCategory.QUANT_TRADING
    assert tool_def.tier == ExecutionTier.TIER_1_INPROCESS
    assert "symbol" in tool_def.parameters
    assert tool_def.parameters["period"].default == 14

    # OpenAI schema test
    schema = tool_def.to_openai_schema()
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "compute_atr"
    assert "symbol" in schema["function"]["parameters"]["properties"]

    # Filter test
    filtered = registry.filter_tools(categories=[ToolCategory.QUANT_TRADING])
    assert len(filtered) == 1
    assert filtered[0].name == "compute_atr"


# ==============================================================================
# 3. Tool Dispatcher Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_tool_dispatcher_async_and_sync():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_dispatch.sqlite"
        wal_db = SessionDbWal(db_path)
        registry = ToolsetRegistry()

        @monika_tool(category=ToolCategory.CORE)
        async def async_fetch(val: int) -> int:
            await asyncio.sleep(0.01)
            return val * 2

        @monika_tool(category=ToolCategory.CORE)
        def sync_calc(a: int, b: int) -> int:
            return a + b

        registry.register(async_fetch)
        registry.register(sync_calc)

        dispatcher = ToolDispatcher(registry=registry, db=wal_db)

        # Execute async
        res1 = await dispatcher.execute("async_fetch", {"val": "10"}, session_id="s_disp", turn_ordinal=1)
        assert not res1.is_error
        assert res1.output == 20

        # Execute sync
        res2 = await dispatcher.execute("sync_calc", {"a": "5", "b": 15}, session_id="s_disp", turn_ordinal=1)
        assert not res2.is_error
        assert res2.output == 20

        # Check DB audit records
        tools = wal_db.get_tool_records("s_disp")
        assert len(tools) == 2
        assert tools[0]["tool_name"] == "async_fetch"
        assert tools[1]["tool_name"] == "sync_calc"

        wal_db.close()


@pytest.mark.asyncio
async def test_tool_dispatcher_timeout():
    registry = ToolsetRegistry()

    @monika_tool(timeout_seconds=0.1)
    async def slow_tool():
        await asyncio.sleep(0.5)
        return "done"

    registry.register(slow_tool)
    dispatcher = ToolDispatcher(registry=registry)

    res = await dispatcher.execute("slow_tool", {})
    assert res.is_error
    assert "timed out" in res.output.lower()


# ==============================================================================
# 4. 3-Tier Execution Sandbox Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_tier1_inprocess_sandbox():
    env = Tier1InProcessEnvironment()
    assert env.is_available()

    # Valid quant computation
    code_valid = """
x = math.sqrt(256)
val = x * 2
print(f"Calculated: {val}")
"""
    outcome = await env.run_python_code(code_valid)
    assert outcome.exit_code == 0
    assert "Calculated: 32.0" in outcome.stdout

    # Security violation: explicit import
    code_import = "import os; print(os.name)"
    outcome_sec = await env.run_python_code(code_import)
    assert outcome_sec.exit_code != 0
    assert "Security Violation" in outcome_sec.stderr


@pytest.mark.asyncio
async def test_tier2_host_kernel_sandbox():
    env = Tier2HostKernelEnvironment()
    assert env.is_available()

    # Safe command
    outcome = await env.run_command("python -c \"print('Hello Monika Tier 2')\"")
    assert outcome.exit_code == 0
    assert "Hello Monika Tier 2" in outcome.stdout

    # Terminal Guard rejection
    outcome_blocked = await env.run_command("rm -rf /")
    assert outcome_blocked.exit_code == 126
    assert "Security Violation" in outcome_blocked.stderr


@pytest.mark.asyncio
async def test_tier3_docker_sandbox_fallback():
    # If Docker is not available, should gracefully fall back to Tier 2 without raising
    env = Tier3DockerEnvironment()
    outcome = await env.run_command("python -c \"print('Docker or Fallback')\"")
    assert outcome.exit_code == 0
    assert "Docker or Fallback" in outcome.stdout
