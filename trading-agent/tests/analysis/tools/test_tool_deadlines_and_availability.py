import asyncio
import pytest
from analysis.tools.registry import ToolDefinition


@pytest.mark.asyncio
async def test_tool_definition_timeout_deadline():
    async def slow_handler(args, **ctx):
        await asyncio.sleep(0.5)
        return {"result": "ok"}

    tool_def = ToolDefinition(
        name="slow_tool",
        description="A tool that exceeds deadline",
        parameters={},
        handler=slow_handler,
        timeout_seconds=0.1,  # Short deadline for testing
    )

    result = await tool_def.execute({})
    assert isinstance(result, dict)
    assert result.get("error") == "TOOL_TIMEOUT"
    assert "timed out" in result.get("message", "").lower()
    assert result.get("tool_name") == "slow_tool"


def test_tool_definition_availability_ttl_and_grace():
    check_counter = 0
    is_up = True

    def check():
        nonlocal check_counter
        check_counter += 1
        return is_up

    tool_def = ToolDefinition(
        name="mt5_quote_probe",
        description="Probes MT5 quote endpoint",
        parameters={},
        handler=lambda args, **ctx: "ok",
        check_fn=check,
    )

    # Initial check
    assert tool_def.is_available() is True
    assert check_counter == 1

    # Immediate second call within 30s TTL reuses cached result without calling check_fn again
    assert tool_def.is_available() is True
    assert check_counter == 1

    # Simulate transient failure when cache expires
    tool_def._last_check_time = 0.0  # Force cache expiry
    is_up = False
    # Because healthy_time was set previously, 60s grace window keeps it available
    assert tool_def.is_available() is True
    assert check_counter == 2
