import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from monika.application.agent.harness.agent_harness import AgentHarness
from monika.application.agent.harness.pseudo_tool_parser import extract_pseudo_tool_calls
from monika.application.agent.harness.turn_stop_auditor import TurnStopAuditor
from monika.application.agent.turn_phase_machine import TurnPhase, TurnState
from monika.infrastructure.providers.openai_provider import OpenAIProvider
from monika.infrastructure.providers.gemini_provider import GeminiProvider
from monika.infrastructure.providers.anthropic_provider import AnthropicProvider


class TestMandatoryToolEnforcement:
    def test_extract_pseudo_tool_calls_xml_format(self):
        text = """Here is my decision:
<tool_call name="submit_asset_analysis">
{"symbol": "EURUSD", "decision": "wait", "confidence": 0.7, "rationale": "Chop regime"}
</tool_call>"""
        extracted = extract_pseudo_tool_calls(
            text,
            available_tool_names={"submit_asset_analysis"},
            mandatory_tool="submit_asset_analysis",
        )
        assert len(extracted) == 1
        assert extracted[0]["name"] == "submit_asset_analysis"
        assert extracted[0]["input"]["decision"] == "wait"
        assert extracted[0]["input"]["symbol"] == "EURUSD"

    def test_extract_pseudo_tool_calls_markdown_fence(self):
        text = """Based on market conditions:
```json
{
  "name": "submit_asset_analysis",
  "arguments": {
    "symbol": "EURUSD",
    "decision": "buy",
    "confidence": 0.75,
    "rationale": "Trend continuation"
  }
}
```"""
        extracted = extract_pseudo_tool_calls(
            text,
            available_tool_names={"submit_asset_analysis"},
            mandatory_tool="submit_asset_analysis",
        )
        assert len(extracted) == 1
        assert extracted[0]["name"] == "submit_asset_analysis"
        assert extracted[0]["input"]["decision"] == "buy"

    def test_extract_pseudo_tool_calls_direct_payload(self):
        text = """```json
{
  "symbol": "EURUSD",
  "decision": "wait",
  "confidence": 0.6,
  "rationale": "ADX below threshold"
}
```"""
        extracted = extract_pseudo_tool_calls(
            text,
            available_tool_names={"submit_asset_analysis"},
            mandatory_tool="submit_asset_analysis",
        )
        assert len(extracted) == 1
        assert extracted[0]["name"] == "submit_asset_analysis"
        assert extracted[0]["input"]["decision"] == "wait"

    def test_turn_stop_auditor_arms_forced_tool_choice_on_nudge(self):
        harness = MagicMock()
        harness.get_mandatory_tool_for_stage.return_value = "submit_asset_analysis"
        harness._next_turn_tool_choice = None
        harness.verification_ledger = MagicMock()
        harness.fallback_client = None

        current_messages = []
        turn_state = TurnState(
            turn_id="test_turn",
            session_id="test_session",
            user_prompt="Analyze EURUSD",
            current_phase=TurnPhase.PREFLIGHT,
        )

        verdict = TurnStopAuditor.audit_completion(
            harness=harness,
            current_messages=current_messages,
            final_text="I am done with my analysis.",
            stage_name="per_asset_EURUSD",
            stage_symbol="EURUSD",
            turns=1,
            effective_max_turns=5,
            called_tools=set(),
            unpersisted_validation_failures=set(),
            turn_state=turn_state,
            tool_calls_made=0,
            emergency_recovery_turns_used=0,
            max_emergency_recovery_turns=2,
        )

        assert verdict.can_break is False
        assert len(current_messages) == 1
        assert "CRITICAL MANDATORY INSTRUCTION" in current_messages[0]["content"]
        assert harness._next_turn_tool_choice == {
            "type": "function",
            "function": {"name": "submit_asset_analysis"},
        }

    def test_turn_stop_auditor_triggers_proactive_fallback_swap(self):
        harness = MagicMock()
        harness.get_mandatory_tool_for_stage.return_value = "submit_asset_analysis"
        harness.fallback_client = MagicMock()
        harness._try_fallback_swap = MagicMock(return_value=True)

        current_messages = []
        turn_state = TurnState(
            turn_id="test_turn",
            session_id="test_session",
            user_prompt="Analyze EURUSD",
            current_phase=TurnPhase.PREFLIGHT,
        )

        verdict = TurnStopAuditor.audit_completion(
            harness=harness,
            current_messages=current_messages,
            final_text="Still no tool call on turn 2.",
            stage_name="per_asset_EURUSD",
            stage_symbol="EURUSD",
            turns=2,
            effective_max_turns=5,
            called_tools=set(),
            unpersisted_validation_failures=set(),
            turn_state=turn_state,
            tool_calls_made=0,
            emergency_recovery_turns_used=0,
            max_emergency_recovery_turns=2,
        )

        assert verdict.can_break is False
        harness._try_fallback_swap.assert_called_once()
        assert harness._next_turn_tool_choice == {
            "type": "function",
            "function": {"name": "submit_asset_analysis"},
        }

    @pytest.mark.asyncio
    async def test_openai_provider_tool_choice_propagation(self):
        provider = OpenAIProvider(
            model="gpt-4o-mini",
            api_key="test_key",
            settings={},
        )
        provider.client = MagicMock()
        provider.client.chat = MagicMock()
        provider.client.chat.completions = MagicMock()
        provider.client.chat.completions.create = AsyncMock(
            return_value=MagicMock(choices=[MagicMock(message=MagicMock(content="ok", tool_calls=None))])
        )

        tools = [
            {
                "name": "submit_asset_analysis",
                "description": "Submit analysis",
                "input_schema": {"type": "object", "properties": {"decision": {"type": "string"}}},
            }
        ]

        await provider.run_tool_agent(
            messages=[{"role": "user", "content": "analyze"}],
            tools=tools,
            system_prompt="sys",
            tool_choice="submit_asset_analysis",
        )

        call_kwargs = provider.client.chat.completions.create.call_args[1]
        assert "tool_choice" in call_kwargs
        assert call_kwargs["tool_choice"] == {
            "type": "function",
            "function": {"name": "submit_asset_analysis"},
        }

    @pytest.mark.asyncio
    async def test_anthropic_provider_tool_choice_propagation(self):
        provider = AnthropicProvider(
            model="claude-3-5-haiku-latest",
            api_key="test_key",
            settings={"llm": {"providers": {"anthropic": {"streaming": {"enabled": False}}}}},
        )
        provider.client = MagicMock()
        provider.client.messages = MagicMock()
        provider.client.messages.create = AsyncMock(return_value=MagicMock(content=[MagicMock(type="text", text="ok")]))

        tools = [
            {
                "name": "submit_asset_analysis",
                "description": "Submit analysis",
                "input_schema": {"type": "object", "properties": {"decision": {"type": "string"}}},
            }
        ]

        await provider.run_tool_agent(
            messages=[{"role": "user", "content": "analyze"}],
            tools=tools,
            system_prompt="sys",
            tool_choice="submit_asset_analysis",
        )

        create_kwargs = provider.client.messages.create.call_args[1]
        assert "tool_choice" in create_kwargs
        assert create_kwargs["tool_choice"] == {"type": "tool", "name": "submit_asset_analysis"}

    @pytest.mark.asyncio
    async def test_harness_mandatory_tool_missing_sets_success_false(self):
        llm_client = MagicMock()
        # Mock LLM returning text with no tool call
        choice_mock = MagicMock()
        choice_mock.message = MagicMock(content="Text only", tool_calls=None, reasoning=None)
        choice_mock.finish_reason = "stop"
        response_mock = MagicMock(choices=[choice_mock], usage=None)
        llm_client.run_tool_agent = AsyncMock(return_value=response_mock)
        llm_client.model = "test-model"
        llm_client.provider_name = "openai"

        harness = AgentHarness(
            llm_client=llm_client,
            settings={},
            max_tool_turns=1,
        )

        res = await harness.run_agent(
            session=None,
            system_prompt="sys",
            user_message="Analyze EURUSD",
            tools=[],
            stage_name="per_asset_EURUSD",
        )

        assert res["success"] is False
        assert "Mandatory submission tool 'submit_asset_analysis' was never called" in res["error"]
