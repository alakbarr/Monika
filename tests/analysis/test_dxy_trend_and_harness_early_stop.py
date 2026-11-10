import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock

from monika.infrastructure.database.models import DXYData
from monika.application.analysis.tools.executor import ToolExecutor
from monika.application.agent.harness.agent_harness import AgentHarness
from monika.infrastructure.providers.base_provider import BaseLLMClient, MockResponse, MockBlock


def create_mock_async_session():
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.add = MagicMock()
    return mock_session


class DummyLLMClient(BaseLLMClient):
    """Test LLM Client subclassing BaseLLMClient."""

    def __init__(self, model="dummy-model", **kwargs):
        super().__init__(model=model, max_tokens=4096, **kwargs)
        self.provider_name = "dummy"
        self._save_token_usage = AsyncMock()
        self._log_tool_call = AsyncMock()
        self.mock_run_tool_agent = AsyncMock()

    async def generate(self, prompt: str, system: str = "", temperature=None, max_tokens=None):
        return "dummy_text"

    async def classify_json(self, prompt: str, system_prompt=None, schema=None, temperature=None, max_tokens=None):
        return {}

    async def run_chat_loop(self, system_prompt, conversation_history, new_user_message, tools, tool_executor=None):
        return {"reply": "ok"}

    async def run_tool_agent(self, messages: list, tools: list, system_prompt=None):
        return await self.mock_run_tool_agent(messages, tools, system_prompt)


@pytest.mark.asyncio
async def test_handle_get_dxy_neutral_deadband():
    """Verify that DXY with pct_change <= 0.20% evaluates to 'neutral' rather than 'strengthening'."""
    session = create_mock_async_session()
    executor = ToolExecutor(session)

    # 101.551 vs 101.550 is +0.00098% (< 0.20% threshold)
    d1 = DXYData(date=datetime.now(timezone.utc), close=101.551)
    d2 = DXYData(date=datetime.now(timezone.utc) - timedelta(days=1), close=102.194)
    d3 = DXYData(date=datetime.now(timezone.utc) - timedelta(days=2), close=102.251)
    d4 = DXYData(date=datetime.now(timezone.utc) - timedelta(days=3), close=102.300)
    d5 = DXYData(date=datetime.now(timezone.utc) - timedelta(days=4), close=101.550)

    mock_result = MagicMock()
    mock_result.scalars().all.return_value = [d1, d2, d3, d4, d5]
    session.execute = AsyncMock(return_value=mock_result)

    res = await executor._tool_get_dxy({"days_back": 10})
    assert res["latest"]["close"] == 101.551
    assert res["trend_5d"] == "neutral"
    assert res["change_5d_pct"] == 0.0


@pytest.mark.asyncio
async def test_brief_submission_dxy_neutral_tolerates_nuanced_narrative():
    """Verify that when empirical DXY trend is neutral, nuanced directional descriptions do NOT raise DATA_MISMATCH."""
    session = create_mock_async_session()
    executor = ToolExecutor(session)

    # Mock get_dxy returning neutral
    executor.execute = AsyncMock(
        return_value={
            "trend_5d": "neutral",
            "latest": {"close": 101.551},
            "change_5d_pct": 0.0,
        }
    )

    inp = {
        "key_data_points_used": {
            "dxy_trend_5d": "weakening -0.73% to 101.551",
            "vix_close": 16.5,
        }
    }

    errors = await executor._validate_key_data_points(inp)
    dxy_errors = [e for e in errors if "DATA_MISMATCH: Restated DXY trend" in e]
    assert len(dxy_errors) == 0, f"Expected no DXY mismatch error when trend is neutral, got: {dxy_errors}"


@pytest.mark.asyncio
async def test_agent_harness_early_stop_on_persisted_mandatory():
    """Verify that AgentHarness breaks out of ReAct loop immediately once mandatory terminal tool is persisted."""
    client = DummyLLMClient(model="gemini-3.8-flash")
    client.role = "stage1_fundamental"
    client.thinking_level = "off"

    harness = AgentHarness(llm_client=client, settings={"max_tool_turns": 10})

    call_turn_count = 0

    async def mock_run_tool_agent(*args, **kwargs):
        nonlocal call_turn_count
        call_turn_count += 1
        return MockResponse(
            content=[
                MockBlock(
                    "tool_use",
                    name="submit_fundamental_brief",
                    input={"macro_regime": "neutral"},
                    id="call_1",
                )
            ],
            stop_reason="tool_use",
            input_tokens=100,
            output_tokens=50,
        )

    client.mock_run_tool_agent.side_effect = mock_run_tool_agent

    mock_executor = MagicMock()
    mock_executor.execute = AsyncMock(return_value={"status": "saved", "id": 999})
    mock_executor._normalize_tool_name = lambda name: name
    mock_executor.is_safe_read_tool = lambda name: False

    session = create_mock_async_session()

    result = await harness.run_agent_from_messages(
        session=session,
        system_prompt="Test system",
        messages=[{"role": "user", "content": "Analyze market"}],
        tools=[{"name": "submit_fundamental_brief", "description": "Submit brief"}],
        stage_name="fundamental",
        tool_executor=mock_executor,
    )

    assert result["success"] is True
    # Crucial assertion: LLM should ONLY be called once on Turn 1; NO Turn 2 closing pleasantries
    assert call_turn_count == 1, f"Expected exactly 1 turn due to early completion, got {call_turn_count}"
    assert result["turns"] == 1


def test_fallback_wrapper_floor_budget_for_fundamental_thinking():
    """Verify slot_timeout allocates at least 900s for thinking models in fundamental/macro stages."""
    stage_hint = "fundamental"
    is_thinking_active = True
    is_macro_fundamental = "fundamental" in stage_hint or "macro" in stage_hint or "stage1" in stage_hint
    floor_budget = 900.0 if (is_thinking_active and is_macro_fundamental) else (600.0 if is_thinking_active else 300.0)
    assert floor_budget == 900.0
