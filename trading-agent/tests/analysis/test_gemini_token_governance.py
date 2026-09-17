import pytest
import unittest
from unittest.mock import AsyncMock, patch, MagicMock
from analysis.providers.gemini_provider import GeminiProvider

class TestGeminiTokenGovernance(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.settings = {
            "llm": {
                "providers": {
                    "gemini": {
                        "api_key": "test-key-fake-123",
                        "streaming": {"enabled": False},
                        "timeout_seconds": 30
                    }
                }
            }
        }

    async def test_generate_respects_custom_max_tokens(self):
        provider = GeminiProvider(model="gemini-3.5-flash-lite", settings=self.settings)
        provider.max_tokens = 10000

        with patch("analysis.providers.gemini_provider.fetch_with_retry", new_callable=AsyncMock) as mock_fetch, \
             patch("analysis.providers.gemini_provider.get_session"), \
             patch("analysis.providers.gemini_provider.GeminiRateLimiter.try_acquire", return_value=True):
            
            mock_fetch.return_value = {
                "candidates": [{
                    "content": {"parts": [{"text": '{"result": "ok"}'}]},
                    "finishReason": "STOP"
                }]
            }

            # Panggilan dengan max_tokens eksplisit (misalnya specialist = 2048)
            res = await provider.generate("test prompt", max_tokens=2048)
            self.assertEqual(res, '{"result": "ok"}')

            called_payload = mock_fetch.call_args[1]["json"]
            self.assertEqual(called_payload["generationConfig"]["maxOutputTokens"], 2048)

    async def test_generate_falls_back_to_provider_max_tokens(self):
        provider = GeminiProvider(model="gemini-3.5-flash", settings=self.settings)
        provider.max_tokens = 36000

        with patch("analysis.providers.gemini_provider.fetch_with_retry", new_callable=AsyncMock) as mock_fetch, \
             patch("analysis.providers.gemini_provider.get_session"), \
             patch("analysis.providers.gemini_provider.GeminiRateLimiter.try_acquire", return_value=True):
            
            mock_fetch.return_value = {
                "candidates": [{
                    "content": {"parts": [{"text": 'analysis text'}]},
                    "finishReason": "STOP"
                }]
            }

            # Panggilan tanpa max_tokens eksplisit
            res = await provider.generate("test prompt")
            self.assertEqual(res, 'analysis text')

            called_payload = mock_fetch.call_args[1]["json"]
            self.assertEqual(called_payload["generationConfig"]["maxOutputTokens"], 36000)

    async def test_run_agent_nudges_on_missing_submit_tool(self):
        provider = GeminiProvider(model="gemini-3.5-flash", settings=self.settings)
        provider.max_tool_turns = 3

        mock_session = AsyncMock()

        # Turn 1: model returns text without tool_use, stop_reason="end_turn"
        turn1_resp = MagicMock()
        turn1_resp.content = [MagicMock(type="text", text="I think EURUSD is bullish.")]
        turn1_resp.stop_reason = "end_turn"
        turn1_resp.input_tokens = 100
        turn1_resp.output_tokens = 50
        turn1_resp.is_paid = False

        # Turn 2: model calls submit_asset_analysis
        turn2_resp = MagicMock()
        turn2_resp.content = [
            MagicMock(type="tool_use", name="submit_asset_analysis", input={"symbol": "EURUSD", "decision": "buy"}, id="call_1")
        ]
        turn2_resp.stop_reason = "tool_use"
        turn2_resp.input_tokens = 120
        turn2_resp.output_tokens = 60
        turn2_resp.is_paid = False

        # Turn 3: model final end_turn
        turn3_resp = MagicMock()
        turn3_resp.content = [MagicMock(type="text", text="Trade recorded successfully.")]
        turn3_resp.stop_reason = "end_turn"
        turn3_resp.input_tokens = 150
        turn3_resp.output_tokens = 30
        turn3_resp.is_paid = False

        with patch.object(provider, "run_tool_agent", side_effect=[turn1_resp, turn2_resp, turn3_resp]) as mock_run_tool, \
             patch("analysis.tools.tool_executor.ToolExecutor.execute", return_value={"status": "recorded"}), \
             patch.object(provider, "_save_token_usage", new_callable=AsyncMock), \
             patch.object(provider, "_log_tool_call", new_callable=AsyncMock):

            result = await provider.run_agent(
                session=mock_session,
                system_prompt="system",
                user_message="Analyze EURUSD",
                tools=[],
                stage_name="per_asset_EURUSD"
            )

            self.assertTrue(result["success"])
            self.assertEqual(result["tool_calls_made"], 1)
            self.assertEqual(mock_run_tool.call_count, 3)
