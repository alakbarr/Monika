import pytest
import unittest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timedelta, timezone

from analysis.providers.gemini_provider import GeminiProvider
from analysis.stages.per_asset_stage import SPECIALIST_PROMPTS
from analysis.debate.fact_sheet import build_fact_sheet
from database.models import AssetAnalysis, Position, FundamentalBrief


class TestLLMMemoryCacheEnhancements(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.settings = {
            "llm": {
                "providers": {
                    "gemini": {
                        "api_key": "test-api-key-12345",
                        "streaming": {"enabled": False},
                        "timeout_seconds": 30
                    }
                }
            }
        }

    async def test_gemini_thinking_none_no_inflation(self):
        """Pastikan jika thinking 'none', eff_max_tokens TIDAK di-inflate dengan +2048."""
        provider = GeminiProvider(model="gemini-3.5-flash-lite", settings=self.settings, api_key="test-api-key-12345")
        provider.max_tokens = 1024
        provider.thinking_budget = 0
        provider.thinking_level = "none"

        with patch("analysis.providers.gemini_provider.fetch_with_retry", new_callable=AsyncMock) as mock_fetch, \
             patch("analysis.providers.gemini_provider.get_session"), \
             patch("analysis.providers.gemini_provider.GeminiRateLimiter.try_acquire", return_value=True):
            
            mock_fetch.return_value = {
                "candidates": [{
                    "content": {"parts": [{"text": '{"result": "success"}'}]},
                    "finishReason": "STOP"
                }]
            }

            res = await provider.generate("test prompt", max_tokens=1024)
            self.assertEqual(res, '{"result": "success"}')

            called_payload = mock_fetch.call_args[1]["json"]
            self.assertEqual(called_payload["generationConfig"]["maxOutputTokens"], 1024)

    async def test_chronicle_writer_preserves_structural_events(self):
        """Event struktural (geopolitical, institutional, regime_shift) tidak di-resolve otomatis."""
        from analysis.memory.chronicle_writer import ChronicleWriter
        writer = ChronicleWriter()

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        brief = MagicMock()
        brief.macro_regime = "RISK_ON"
        brief.risk_sentiment = "BULLISH"
        brief.confidence = 0.85
        brief.generated_at = datetime.now(timezone.utc)
        brief.id = 1
        prev_brief = MagicMock()
        prev_brief.macro_regime = "NEUTRAL"
        prev_brief.risk_sentiment = "NEUTRAL"
        prev_brief.confidence = 0.70

        await writer.maybe_record_regime_shift(mock_session, brief, prev_brief)

        call_args = mock_session.execute.call_args_list[0][0][0]
        compiled_query = str(call_args.compile(compile_kwargs={"literal_binds": True}))
        self.assertIn("category IN ('data_shock', 'policy_change')", compiled_query)

    def test_specialist_prompts_symbol_agnostic(self):
        """Pastikan prompt spesialis 100% statis & symbol-agnostic demi KV cache hit."""
        for role, prompt in SPECIALIST_PROMPTS.items():
            self.assertNotIn("{symbol}", prompt, f"Prompt {role} mengandung {{symbol}}, merusak cache hit!")
            self.assertIn("target asset", prompt.lower(), f"Prompt {role} harus menginstruksikan LLM membaca target asset dari user message.")

    async def test_fact_sheet_includes_layer1_core_memory(self):
        """Pastikan fact_sheet memuat ringkasan Layer 1 Core Memory (regime & lessons)."""
        analysis = MagicMock(spec=AssetAnalysis)
        analysis.symbol = "EURUSD"
        analysis.decision = "buy"
        analysis.entry_zone = '{"price": 1.0850}'
        analysis.price_at_analysis = 1.0850
        analysis.stop_loss = 1.0800
        analysis.take_profit = 1.0950
        analysis.confluence_score = 10
        analysis.confluence_factors_json = "[]"
        analysis.rationale = "Test rationale"

        mock_session = AsyncMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_scalars.scalar_one_or_none.return_value = None
        mock_exec_result = MagicMock()
        mock_exec_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_exec_result

        with patch("analysis.memory.layered_memory.LayeredMemoryManager.get_core_memory", new_callable=AsyncMock) as mock_get_core:
            mock_get_core.return_value = "=== REGIME: RISK_ON ===\nLessons: Avoid counter-trend breakout."
            
            sheet = await build_fact_sheet(mock_session, analysis)
            self.assertIn("active_core_regime_and_lessons", sheet)
            self.assertIsNotNone(sheet["active_core_regime_and_lessons"])
            self.assertIn("REGIME: RISK_ON", sheet["active_core_regime_and_lessons"])
            self.assertIn("vix", sheet)
            self.assertIn("active_market_chronicle", sheet)

    async def test_chronicle_writer_bootstrap_seeding(self):
        """Pastikan seed_bootstrap_chronicles_if_empty membuat 5 seed struktural terverifikasi 2026 saat tabel kosong."""
        from analysis.memory.chronicle_writer import ChronicleWriter
        writer = ChronicleWriter()

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 0  # Table is empty
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        seeded = await writer.seed_bootstrap_chronicles_if_empty(mock_session)
        self.assertEqual(seeded, 5)
        self.assertEqual(mock_session.add.call_count, 5)
        mock_session.commit.assert_awaited_once()

    async def test_anthropic_generate_builds_system_blocks_and_adaptive_efforts(self):
        """Pastikan Anthropic generate() memanggil _build_system_blocks dan mendukung level xhigh/max."""
        from analysis.providers.anthropic_provider import AnthropicProvider
        provider = AnthropicProvider(model="claude-sonnet-4-6", settings=self.settings, thinking_level="xhigh")
        provider.client = AsyncMock()
        mock_stream = AsyncMock()
        mock_stream.get_final_message.return_value = MagicMock(content=[MagicMock(text="test output")], usage=None)

        with patch.object(provider, "_consume_anthropic_stream", return_value=mock_stream.get_final_message.return_value), \
             patch("utils.api.claude_rate_limiter.ClaudeRateLimiter.acquire_session_slot", new_callable=AsyncMock):
            
            await provider.generate("hello", system="System instruction for cache")
            call_kwargs = provider._consume_anthropic_stream.call_args[0][0]

            # Pastikan system berbentuk list of dict dengan ephemeral cache control
            self.assertIsInstance(call_kwargs["system"], list)
            self.assertEqual(call_kwargs["system"][0]["cache_control"]["type"], "ephemeral")
            self.assertEqual(call_kwargs["system"][0]["text"], "System instruction for cache")

            # Pastikan output_config effort xhigh tidak di-downgrade ke high
            self.assertEqual(call_kwargs.get("output_config", {}).get("effort"), "xhigh")

    async def test_ollama_generate_appends_human_message(self):
        """Pastikan Ollama generate() menyertakan HumanMessage ke dalam array messages."""
        from analysis.providers.ollama_provider import OllamaProvider
        from langchain_core.messages import HumanMessage, SystemMessage

        provider = OllamaProvider(model_name="qwen2.5-coder:7b", settings=self.settings)
        mock_client = AsyncMock()
        mock_client.ainvoke.return_value = MagicMock(content="model response", response_metadata={})
        provider._get_client = MagicMock(return_value=mock_client)

        result = await provider.generate("Test prompt query", system="System rule")
        self.assertEqual(result, "model response")

        call_messages = mock_client.ainvoke.call_args[0][0]
        self.assertEqual(len(call_messages), 2)
        self.assertIsInstance(call_messages[0], SystemMessage)
        self.assertIsInstance(call_messages[1], HumanMessage)
        self.assertEqual(call_messages[1].content, "Test prompt query")

    def test_openai_dynamic_headroom(self):
        """Pastikan OpenAI provider menerapkan headroom dinamis bertingkat sesuai thinking level."""
        from analysis.providers.openai_provider import OpenAIProvider
        provider = OpenAIProvider(model="o3-mini", max_tokens=4096, thinking_level="high", settings=self.settings)
        kwargs = {"max_tokens": 4096}
        provider._apply_reasoning_params(kwargs)

        # High effort harus menambahkan +8192 headroom token
        self.assertEqual(kwargs["max_completion_tokens"], 4096 + 8192)
        self.assertNotIn("max_tokens", kwargs)

    async def test_debate_analysts_prompt_caching_isolation(self):
        """Pastikan Bull dan Bear analyst tidak membakar symbol ke dalam system prompt."""
        from analysis.debate.bull_analyst import generate_bull_advocacy
        from analysis.debate.bear_analyst import generate_bear_dissent

        mock_client = AsyncMock()
        mock_client.generate_content.return_value = '{"bull_thesis": "Strong support", "strength_score": 8, "evidence_cited": ["ATR=1.5", "DXY=down"]}'

        await generate_bull_advocacy(mock_client, "EURUSD", {"decision": "buy"}, {})
        bull_sys = mock_client.generate_content.call_args[1]["system_prompt"]
        bull_user = mock_client.generate_content.call_args[1]["user_message"]
        self.assertNotIn("for EURUSD", bull_sys)
        self.assertIn("target asset specified in the user message", bull_sys)
        self.assertIn("[TARGET ASSET]: EURUSD", bull_user)

        mock_client.generate_content.return_value = '{"bear_dissent": "Weak resistance", "risk_severity": 6, "evidence_cited": ["ATR=1.5", "VIX=22.0"]}'
        await generate_bear_dissent(mock_client, "GBPUSD", {"decision": "buy"}, {}, {})
        bear_sys = mock_client.generate_content.call_args[1]["system_prompt"]
        bear_user = mock_client.generate_content.call_args[1]["user_message"]
        self.assertNotIn("for GBPUSD", bear_sys)
        self.assertIn("target asset specified in the user message", bear_sys)
        self.assertIn("[TARGET ASSET]: GBPUSD", bear_user)

    def test_cache_breakpoint_manager_skips_short_prompts_and_pads_near_threshold(self):
        """Pastikan CacheBreakpointManager tidak membuang token pada prompt pendek, tapi pad saat dekat threshold."""
        from utils.llm.cache_breakpoint_manager import CacheBreakpointManager
        
        # 1. Prompt pendek (< 10.000 char) tidak boleh dipad
        short_prompt = "You are a classifier."
        res_short = CacheBreakpointManager.pad_system_prompt_to_threshold(short_prompt, model_name="gemini-3.7-flash")
        self.assertEqual(res_short, short_prompt)

        # 2. Prompt panjang (> 10.000 char) di bawah 16.500 char harus dipad hingga >= 16.500 char untuk Gemini 3
        long_prompt = "A" * 12500
        res_long = CacheBreakpointManager.pad_system_prompt_to_threshold(long_prompt, model_name="gemini-3.7-flash")
        self.assertGreaterEqual(len(res_long), 16500)

    async def test_layered_memory_detect_regime_fuses_vix_dxy_macro_brief(self):
        """Pastikan LayeredMemoryManager._detect_regime memadukan VIX, DXY, dan FundamentalBrief."""
        from analysis.memory.layered_memory import LayeredMemoryManager
        from database.models import DXYData, VIXData, FundamentalBrief

        mgr = LayeredMemoryManager(self.settings)
        mock_session = AsyncMock()

        # Mock DXY
        dxy1 = MagicMock(close=104.5)
        dxy2 = MagicMock(close=103.0)
        dxy3 = MagicMock(close=102.5)
        mock_dxy_res = MagicMock()
        mock_dxy_res.scalars.return_value.all.return_value = [dxy1, dxy2, dxy3]

        # Mock VIX
        mock_vix = MagicMock(close=26.5)
        mock_vix_res = MagicMock()
        mock_vix_res.scalar_one_or_none.return_value = mock_vix

        # Mock FundamentalBrief
        mock_brief = MagicMock(macro_regime="HAWKISH_EXPANSION", risk_sentiment="RISK_OFF")
        mock_brief_res = MagicMock()
        mock_brief_res.scalar_one_or_none.return_value = mock_brief

        mock_session.execute.side_effect = [mock_dxy_res, mock_vix_res, mock_brief_res]

        regime = await mgr._detect_regime(mock_session)
        self.assertIn("HAWKISH_EXPANSION", regime)
        self.assertIn("RISK_RISK_OFF", regime)
        self.assertIn("USD_STRENGTHENING", regime)
        self.assertIn("VIX_DEFENSIVE(26.5)", regime)

    async def test_prompt_cache_invariance_and_hit_rate_simulation(self):
        """Simulasikan beberapa query berturut-turut dan ukur cache hit rate prefix invariance."""
        from telegram_bot.chat_agent import ChatAgent
        from utils.llm.cache_breakpoint_manager import CacheBreakpointManager

        agent = ChatAgent(self.settings, user_id=12345)
        mock_session = AsyncMock()
        mock_res = MagicMock()
        mock_res.scalars.return_value.all.return_value = []
        mock_res.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_res

        # Sesi 1: waktu T
        res1 = await agent._build_system_prompt(mock_session)
        self.assertIsInstance(res1, tuple)
        static1, dynamic1 = res1

        # Sesi 2: waktu T + 1 jam
        res2 = await agent._build_system_prompt(mock_session)
        static2, dynamic2 = res2

        # 1. Static prefix harus 100% identik (invarian byte-for-byte)
        self.assertEqual(static1, static2)
        self.assertGreater(len(static1), 1024)
        self.assertTrue(static1.startswith(CacheBreakpointManager.CANONICAL_TIER0_ANCHOR.strip()))

        # 2. Uji preparasi prompt cache invariance
        sys_p1, user_msg1 = agent._prepare_cache_invariant_prompt(res1, "Bagaimana kondisi XAUUSD?")
        sys_p2, user_msg2 = agent._prepare_cache_invariant_prompt(res2, "Berapa floating PnL saat ini?")

        self.assertEqual(sys_p1, sys_p2)
        self.assertIn("<volatile_overlay>", user_msg1)
        self.assertIn("<volatile_overlay>", user_msg2)

        # 3. Hitung prefix cache hit rate simulasi
        # Common prefix ratio = len(common_prefix) / max(len(prompt1), len(prompt2))
        common_len = 0
        for c1, c2 in zip(sys_p1, sys_p2):
            if c1 == c2:
                common_len += 1
            else:
                break
        cache_hit_rate = common_len / max(len(sys_p1), len(sys_p2))
        self.assertGreaterEqual(cache_hit_rate, 0.99, "Prompt cache invariance harus mencapai >99% kestabilan prefix!")


