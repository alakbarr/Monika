"""
Unit test untuk verifikasi pencatatan komprehensif token_usage_log.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from analysis.providers.base_provider import BaseLLMClient


class DummyClient(BaseLLMClient):
    async def generate(self, prompt: str, system: str = "", temperature=None):
        return "response"

    async def classify_json(self, prompt: str, system_prompt=None, schema=None, temperature=None):
        return {"result": "ok"}

    async def run_tool_agent(self, messages, tools, system_prompt):
        return None

    async def run_agent(self, session, system_prompt, user_message, tools, stage_name="unknown", extra_context=None, prefetch_satisfied_tools=None):
        return {"success": True}

    async def run_chat_loop(self, system_prompt, conversation_history, new_user_message, tools, tool_executor=None):
        return {"reply": "ok"}

    async def run_agent_from_messages(self, session, system_prompt, messages, tools, max_tool_turns=15):
        return {"success": True}


@pytest.mark.asyncio
async def test_subsystem_inference():
    assert BaseLLMClient._infer_subsystem("stage1_fundamental", "generate") == "stage1"
    assert BaseLLMClient._infer_subsystem("stage2_per_asset_primary", "generate") == "stage2"
    assert BaseLLMClient._infer_subsystem("debate_bull", "generate") == "debate"
    assert BaseLLMClient._infer_subsystem("news_classification", "generate") == "news"
    assert BaseLLMClient._infer_subsystem("risk_gate_conservative", "generate") == "risk_gate"
    assert BaseLLMClient._infer_subsystem("chat_telegram", "generate") == "telegram"
    assert BaseLLMClient._infer_subsystem("trade_reflection", "generate") == "memory"
    assert BaseLLMClient._infer_subsystem("unknown", "unknown") == "system"


@pytest.mark.asyncio
async def test_save_token_usage_records_comprehensive_fields():
    client = DummyClient(
        model="claude-sonnet-5",
        role="stage1_fundamental",
        subsystem="stage1",
        symbol=None,
        cycle_id="cycle-20260827-01",
    )

    mock_session = AsyncMock()

    with patch("database.models.TokenUsageLog") as MockTokenUsageLog, \
         patch("utils.analytics.pricing.cost_usd", return_value=0.005) as mock_cost:

        await client._save_token_usage(
            model_name="claude-sonnet-5",
            task_name="generate",
            input_tokens=1000,
            output_tokens=200,
            session=mock_session,
            cached_tokens=400,
            cache_creation_tokens=100,
            thinking_tokens=50,
            execution_time_ms=350,
            status="success",
            slot_name="primary"
        )

        MockTokenUsageLog.assert_called_once_with(
            provider="dummy",
            model_name="claude-sonnet-5",
            task_name="generate",
            task_role="stage1_fundamental",
            subsystem="stage1",
            symbol=None,
            cycle_id="cycle-20260827-01",
            input_tokens=1000,
            output_tokens=200,
            thinking_tokens=50,
            total_tokens=1200,
            cached_tokens=400,
            cache_creation_tokens=100,
            cost_estimate=0.005,
            execution_time_ms=350,
            status="success",
            slot_name="primary",
        )
        mock_session.add.assert_called_once()
        mock_cost.assert_called_once_with("claude-sonnet-5", 1000, 200, cached_tokens=400, provider="dummy")
