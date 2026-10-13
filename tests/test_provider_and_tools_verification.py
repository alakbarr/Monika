"""
Unit test verifying unified provider error taxonomy and tool registry bridging (Fase 2).
"""

import pytest
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from pydantic import BaseModel, Field

from monika.infrastructure.credentials.error_taxonomy import FailoverReason as CanonicalFailoverReason
from monika.infrastructure.providers.provider_failover_classifier import FailoverReason as AnalysisFailoverReason
from monika.application.agent.error_classifier import FailoverReason as AgentFailoverReason


def test_failover_reason_unification():
    """Verify FailoverReason is a single canonical enum across all tiers."""
    assert AnalysisFailoverReason is CanonicalFailoverReason
    assert AgentFailoverReason is CanonicalFailoverReason

    # Verify key attributes and properties work uniformly
    reason = CanonicalFailoverReason.AUTH_PERMANENT
    assert reason.value == "auth_permanent"
    assert reason.should_failover is True

    # Trading domain errors do not failover LLMs
    broker_err = CanonicalFailoverReason.BROKER_MARGIN_CALL
    assert broker_err.is_trading_domain is True
    assert broker_err.should_failover is False

    # Context overflow compresses instead of failing over
    ctx_err = CanonicalFailoverReason.CONTEXT_OVERFLOW
    assert ctx_err.should_compress is True
    assert ctx_err.should_failover is False


@pytest.mark.asyncio
async def test_tool_registry_bridging_and_execution():
    """Verify tools registered in unified_tool_registry are discoverable and executable by ToolExecutor."""
    from monika.application.analysis.tools.unified_registry import unified_tool_registry, ToolEntry
    from monika.application.analysis.tools.registry import ToolRegistry
    from monika.application.analysis.tools.executor import ToolExecutor

    # Define a test tool model and handler
    class MockCustomInput(BaseModel):
        query_val: str = Field(description="Query value")

    async def mock_custom_handler(inp: Any, **kwargs):
        val = inp.query_val if hasattr(inp, "query_val") else str(inp)
        return {"status": "ok", "echo": val}

    # Register into unified_tool_registry
    tool_name = "test_custom_unified_tool"
    unified_tool_registry.register_tool(
        name=tool_name,
        category="CUSTOM",
        description="A mock tool to verify unified bridging",
        handler=mock_custom_handler,
        input_model=MockCustomInput,
    )

    try:
        # 1. Verify legacy ToolRegistry can see it via the bridge
        legacy_reg = ToolRegistry.get_instance()
        assert legacy_reg.has_tool(tool_name) is True
        fetched_tool = legacy_reg.get(tool_name)
        assert fetched_tool is not None
        assert fetched_tool.name == tool_name

        # 2. Verify ToolExecutor can dispatch and execute it without UnknownToolError
        mock_session = AsyncMock()
        mock_session._session_lock = None
        executor = ToolExecutor(session=mock_session, settings={})

        result = await executor.execute(tool_name, {"query_val": "monika_test_123"})
        assert isinstance(result, dict)
        assert result.get("status") == "ok"
        assert result.get("echo") == "monika_test_123"
    finally:
        # Cleanup registered test tool
        if tool_name in unified_tool_registry._tools:
            del unified_tool_registry._tools[tool_name]
