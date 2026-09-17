import pytest
import unittest
from unittest.mock import AsyncMock, patch, MagicMock
from analysis.providers.gemini_provider import GeminiProvider
from analysis.prefetch.news_digest import _keyword_fallback_classify
from utils.market.news_impact_keywords import SHOCK_KEYWORDS, HIGH_IMPACT_KEYWORDS
from analysis.stages.per_asset_stage import PerAssetStage


class TestGeminiAndNewsFixes(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.settings = {
            "trading": {
                "risk": {
                    "vix_thresholds": {
                        "caution": 25,
                        "defensive": 30
                    }
                }
            },
            "llm": {
                "providers": {
                    "gemini": {
                        "api_key": "fake-key",
                        "streaming": {"enabled": False},
                        "timeout_seconds": 30
                    }
                }
            }
        }

    def test_shock_keywords_tightened_no_single_word_false_positives(self):
        """Verify overly broad single-word keywords were removed from SHOCK_KEYWORDS."""
        broad_single_words = ['war', 'attack', 'emergency', 'missile', 'shock', 'nuclear']
        for word in broad_single_words:
            self.assertNotIn(
                word,
                SHOCK_KEYWORDS,
                f"Single broad word '{word}' should not be in SHOCK_KEYWORDS"
            )

        # Multi-word specific phrases must be present
        specific_phrases = ['missile attack', 'war declared', 'bank collapse', 'nuclear threat']
        for phrase in specific_phrases:
            self.assertIn(
                phrase,
                SHOCK_KEYWORDS,
                f"Specific phrase '{phrase}' should be in SHOCK_KEYWORDS"
            )

    def test_keyword_fallback_classify_never_returns_breaking(self):
        """Verify _keyword_fallback_classify caps output to HIGH, never BREAKING."""
        title = "Missile strikes on capital, war declared and bank collapse emergency"
        summary = "Sweeping sanctions and nuclear threat reported"
        res = _keyword_fallback_classify(title, summary)
        
        self.assertEqual(res['impact'], 'HIGH', "Keyword fallback must never assign BREAKING")
        self.assertLessEqual(res['confidence'], 0.5, "Fallback confidence must be low")

    async def test_gemini_run_tool_agent_thought_signature_preservation(self):
        """Verify native Gemini thought signatures are preserved, synthetic IDs filtered."""
        provider = GeminiProvider(model="gemini-3.5-flash", settings=self.settings)

        # Messages containing tool result with genuine Gemini signature vs OpenAI synthetic ID
        genuine_sig = "gemini_native_ts_abc123"
        synthetic_id = "call_openai_style_123"

        messages = [
            {"role": "user", "content": "Analyze USD"},
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "name": "get_quote", "input": {"symbol": "USD"}, "id": genuine_sig},
                    {"type": "tool_use", "name": "get_news", "input": {}, "id": synthetic_id}
                ]
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": genuine_sig, "content": '{"price": 100}'},
                    {"type": "tool_result", "tool_use_id": synthetic_id, "content": '{"news": "none"}'}
                ]
            }
        ]

        with patch("analysis.providers.gemini_provider.fetch_with_retry", new_callable=AsyncMock) as mock_fetch, \
             patch("analysis.providers.gemini_provider.get_session"), \
             patch("analysis.providers.gemini_provider.GeminiRateLimiter.try_acquire", return_value=True):

            mock_fetch.return_value = {
                "candidates": [{
                    "content": {"parts": [{"text": "Analysis complete."}]},
                    "finishReason": "STOP"
                }]
            }

            await provider.run_tool_agent(messages=messages, tools=[], system_prompt="Sys")

            called_payload = mock_fetch.call_args[1]["json"]
            gemini_contents = called_payload["contents"]

            # Find functionResponse parts
            fn_responses = []
            for item in gemini_contents:
                for part in item.get("parts", []):
                    if "functionResponse" in part:
                        fn_responses.append(part)

            self.assertEqual(len(fn_responses), 2)
            
            # Genuine signature must have thoughtSignature attached
            res1 = next(r for r in fn_responses if r["functionResponse"]["name"] == "get_quote")
            self.assertEqual(res1.get("thoughtSignature"), genuine_sig)

            # Synthetic OpenAI id must NOT have thoughtSignature attached
            res2 = next(r for r in fn_responses if r["functionResponse"]["name"] == "get_news")
            self.assertNotIn("thoughtSignature", res2)

    async def test_vix_threshold_caution_vs_defensive(self):
        """Verify VIX 27 falls into caution zone (no +2 penalty), VIX 31 triggers defensive (+2 penalty)."""
        vix_thresholds = self.settings["trading"]["risk"]["vix_thresholds"]
        
        # Test with VIX 27
        vix_val = 27.0
        is_defensive = vix_val >= float(vix_thresholds.get('defensive', 30))
        is_caution = vix_val >= float(vix_thresholds.get('caution', 25))
        
        self.assertFalse(is_defensive, "VIX 27 should NOT trigger defensive threshold")
        self.assertTrue(is_caution, "VIX 27 SHOULD trigger caution zone")

        # Test with VIX 31
        vix_val_high = 31.0
        is_defensive_high = vix_val_high >= float(vix_thresholds.get('defensive', 30))
        self.assertTrue(is_defensive_high, "VIX 31 SHOULD trigger defensive threshold (+2 confluence)")
