"""
Comprehensive Integration Test Suite: Macro Event Probability Flow & Trading Plan Integration.
Verifies the end-to-end pipeline:
1. Benchmark query extraction and complexity classification ('deep_research')
2. Macro event query identification (_is_macro_event_query)
3. Dynamic macro playbook injection (_inject_macro_playbooks)
4. DynamicSubagentPool decomposition: worker_macro with 4 tools & 5-point checklist
5. Deep Research Synthesizer execution: tools, executor, Section 6 3-Scenario prompt
6. PendingAction capture and execution for save_market_intelligence
7. End-to-end multi-turn pipeline verification
"""

import os
import re
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from telegram_bot.chat_agent import ChatAgent, PendingAction
from analysis.subagent_spawner import DynamicSubagentPool
from analysis.tools.tools_definitions import PROPOSE_ACTION, SAVE_MARKET_INTELLIGENCE
from skills.loader import load_skill


def _get_project_root() -> Path:
    """Resolve project root directory containing contoh_pertanyaan.md."""
    # test file is at D:\Monika\trading-agent\tests\test_event_probability_flow.py
    current = Path(__file__).resolve()
    for parent in [current.parent, current.parent.parent, current.parent.parent.parent]:
        if (parent / "contoh_pertanyaan.md").exists():
            return parent
    return current.parent.parent.parent


def _load_benchmark_query() -> tuple[str, str]:
    """
    Load benchmark query from contoh_pertanyaan.md.
    Returns:
        (exact_prompt, full_content)
    """
    root = _get_project_root()
    contoh_file = root / "contoh_pertanyaan.md"
    assert contoh_file.exists(), f"Benchmark query file missing: {contoh_file}"

    full_content = contoh_file.read_text(encoding="utf-8")

    # Extract text from the first fenced block under 'Pertanyaan Chat:'
    match = re.search(r"Pertanyaan Chat:\s*```(?:\w+)?\n(.*?)\n```", full_content, re.DOTALL)
    if match:
        exact_prompt = match.group(1).strip()
    else:
        # Fallback to lines before 'Thinking Flow:'
        parts = full_content.split("Thinking Flow:")
        exact_prompt = parts[0].replace("Pertanyaan Chat:", "").strip()

    assert len(exact_prompt) > 50, "Extracted benchmark prompt is unexpectedly short"
    return exact_prompt, full_content


# ==============================================================================
# 1. Benchmark Query Complexity Classification
# ==============================================================================

class TestBenchmarkQueryClassification:
    """Verify that benchmark query and macro variations are classified as deep_research."""

    @pytest.mark.asyncio
    async def test_exact_benchmark_prompt_classified_as_deep_research(self):
        exact_prompt, _ = _load_benchmark_query()
        with patch("telegram_bot.chat_agent.get_client_for_task") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client
            agent = ChatAgent(settings={}, user_id=99901)

            complexity = await agent._classify_query_complexity(exact_prompt)
            assert complexity == "deep_research", (
                f"Expected 'deep_research' for exact benchmark prompt, got '{complexity}'"
            )

    @pytest.mark.asyncio
    async def test_full_benchmark_file_classified_as_deep_research(self):
        _, full_content = _load_benchmark_query()
        with patch("telegram_bot.chat_agent.get_client_for_task") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client
            agent = ChatAgent(settings={}, user_id=99901)

            complexity = await agent._classify_query_complexity(full_content)
            assert complexity == "deep_research", (
                f"Expected 'deep_research' for full benchmark content, got '{complexity}'"
            )

    @pytest.mark.asyncio
    async def test_benchmark_query_variations_classified_as_deep_research(self):
        variations = [
            "Analisis peluang kemungkinan keputusan suku bunga The Fed 16/17 September yang akan diumumkan.",
            "Di CME Fedwatch proyeksinya 89% The Fed akan menaikkan suku bunga (HIKE), sisanya HOLD.",
            "Apakah ada history The Fed tidak searah dengan harapan pasar dan mengecoh pasar?",
            "Setelah pengumuman suku bunga, apa yang akan dinyatakan Kevin Warsh saat press conference, hawkish atau dovish?",
            "Kumpulkan semua data yang kamu butuhkan. Lakukan analisis keputusan suku bunga FOMC secara komprehensif.",
            "Prospek kebijakan moneter dan probabilitas rate hike CME FedWatch September 2026",
            "What is the probability of a rate hike in CME FedWatch for the upcoming FOMC meeting?",
            "Analisis kebijakan suku bunga bank sentral, dot plot SEP, dan press conference Jerome Powell",
        ]
        with patch("telegram_bot.chat_agent.get_client_for_task") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client
            agent = ChatAgent(settings={}, user_id=99901)

            for query in variations:
                complexity = await agent._classify_query_complexity(query)
                assert complexity == "deep_research", (
                    f"Variation '{query[:45]}...' should be 'deep_research', got '{complexity}'"
                )


# ==============================================================================
# 2. Macro Event Query Detection (_is_macro_event_query)
# ==============================================================================

class TestIsMacroEventQuery:
    """Verify _is_macro_event_query identification on benchmark query, variations & negatives."""

    def test_benchmark_query_returns_true(self):
        exact_prompt, full_content = _load_benchmark_query()
        with patch("telegram_bot.chat_agent.get_client_for_task"):
            agent = ChatAgent(settings={}, user_id=99902)

            assert agent._is_macro_event_query(exact_prompt) is True
            assert agent._is_macro_event_query(full_content) is True

    def test_constituent_sentences_return_true(self):
        sentences = [
            "Analisis peluang kemungkinan keputusan suku bunga The Fed 16/17 September 2016 yang akan diumumkan",
            "Di CME Fedwatch proyeksinya 89% The Fed akan menaikkan suku bunga (HIKE), sedangkan sisanya adalah HOLD.",
            (
                "Tapi apakah ini (HIKE) sudah pasti akan dilakukan oleh The Fed? Apakah ada history The Fed tidak searah "
                "dengan harapan pasar? Jika ada, apa yang menyebabkan itu? Kenapa bisa pasar salah mengartikan arah kebijakan "
                "The Fed atau justru The Fed yang memang sengaja tidak mengikuti arah keinginan pasar/sengaja mengecoh pasar? "
                "Apakah mungkin terjadi lagi saat ini?"
            ),
            "Apakah ada history The Fed tidak searah dengan harapan pasar?",
            "apa yang kira-kira akan dinyatakan oleh Kevin Warsh saat press conference? apakah hawkish atau dovish?",
            "keputusan suku bunga The Fed",
            "CME FedWatch probability analysis",
            "FOMC rate hike odds preview",
            "Jerome Powell press conference monetary policy outlook",
            "Alan Greenspan 1994 bond market surprise",
            "Ben Bernanke 2013 no-taper surprise scenario",
        ]
        with patch("telegram_bot.chat_agent.get_client_for_task"):
            agent = ChatAgent(settings={}, user_id=99902)
            for s in sentences:
                assert agent._is_macro_event_query(s) is True, f"Failed detection for: '{s}'"

    def test_negative_cases_return_false(self):
        negatives = [
            "halo",
            "halo apa kabar",
            "cek saldo akun",
            "tampilkan posisi saat ini",
            "berapa pnl hari ini",
            "order buy 0.1 lot XAUUSD",
            "tutup posisi #12345",
            "/stats",
            "/positions",
            "",
            "   ",
            "\n\t",
            "🔥🔥🔥🚀🚀🚀",
        ]
        with patch("telegram_bot.chat_agent.get_client_for_task"):
            agent = ChatAgent(settings={}, user_id=99902)
            for neg in negatives:
                assert agent._is_macro_event_query(neg) is False, f"False positive for: '{neg}'"
            assert agent._is_macro_event_query(None) is False
            assert agent._is_macro_event_query(12345) is False
            assert agent._is_macro_event_query([]) is False


# ==============================================================================
# 3. Macro Playbook Injection (_inject_macro_playbooks)
# ==============================================================================

class TestInjectMacroPlaybooks:
    """Verify loading and injection of event_probability_playbook and market_dynamics_framework."""

    def test_inject_macro_playbooks_loads_both_skills_string_prompt(self):
        with patch("telegram_bot.chat_agent.get_client_for_task"):
            agent = ChatAgent(settings={}, user_id=99903)
            base_prompt = "System anchor: You are Monika quantitative trading agent."

            injected = agent._inject_macro_playbooks(base_prompt)
            assert isinstance(injected, str)
            assert base_prompt in injected

            # Verify both authoritative headers
            assert "## AUTHORITATIVE EVENT PROBABILITY PLAYBOOK" in injected
            assert "## AUTHORITATIVE MARKET DYNAMICS FRAMEWORK" in injected

            # Verify core sections from event_probability_playbook.md
            assert "PROTOKOL THINKING FLOW 5 TAHAP" in injected
            assert "BAGIAN 2: PUSTAKA PRESEDEN HISTORIS" in injected
            assert "1994 Greenspan Preemptive Strike" in injected
            assert "2013 Bernanke" in injected
            assert "TEMPLATE OUTPUT INSTITUSIONAL" in injected

    def test_inject_macro_playbooks_tuple_format(self):
        with patch("telegram_bot.chat_agent.get_client_for_task"):
            agent = ChatAgent(settings={}, user_id=99903)
            static_prefix = "Static system prompt."
            dynamic_snapshot = "Dynamic session data: equity=10000, margin=500."
            tuple_prompt = (static_prefix, dynamic_snapshot)

            injected_tuple = agent._inject_macro_playbooks(tuple_prompt)
            assert isinstance(injected_tuple, tuple)
            assert len(injected_tuple) == 2

            static_out, dynamic_out = injected_tuple
            assert "## AUTHORITATIVE EVENT PROBABILITY PLAYBOOK" in static_out
            assert "## AUTHORITATIVE MARKET DYNAMICS FRAMEWORK" in static_out
            assert dynamic_out == dynamic_snapshot

    def test_inject_macro_playbooks_idempotent(self):
        with patch("telegram_bot.chat_agent.get_client_for_task"):
            agent = ChatAgent(settings={}, user_id=99903)
            base_prompt = "Base prompt."

            injected_1 = agent._inject_macro_playbooks(base_prompt)
            injected_2 = agent._inject_macro_playbooks(injected_1)

            assert injected_1.count("## AUTHORITATIVE EVENT PROBABILITY PLAYBOOK") == 1
            assert injected_2.count("## AUTHORITATIVE EVENT PROBABILITY PLAYBOOK") == 1


# ==============================================================================
# 4. DynamicSubagentPool Decomposition: worker_macro with Tools & Checklist
# ==============================================================================

class TestDynamicSubagentPoolMacroDecomposition:
    """Verify DynamicSubagentPool spawns worker_macro with required tools and search checklist."""

    def test_worker_macro_spawned_with_required_toolset(self):
        exact_prompt, _ = _load_benchmark_query()
        pool = DynamicSubagentPool(max_concurrency=4, default_timeout=60.0)

        all_tools = [
            {"name": "get_fedwatch_probabilities", "description": "CME FedWatch"},
            {"name": "get_treasury_yields", "description": "US Treasury Yields"},
            {"name": "get_interest_rates", "description": "Global Interest Rates"},
            {"name": "get_eia_oil_inventory", "description": "EIA Petroleum Data"},
            {"name": "get_bond_yield_spreads", "description": "Sovereign Bond Yield Spreads"},
            {"name": "get_economic_calendar", "description": "Macro Calendar"},
            {"name": "get_news_digest", "description": "News Digest"},
            {"name": "get_vix", "description": "VIX Index"},
            {"name": "get_dxy", "description": "US Dollar Index"},
            {"name": "web_search", "description": "Live Web Search"},
            {"name": "get_chart", "description": "Technical Chart"},
            {"name": "get_smc_zones", "description": "SMC Order Blocks"},
            {"name": "get_retail_sentiment", "description": "Retail Positioning"},
        ]

        specs = pool.decompose_research_query(
            query=exact_prompt,
            base_system_prompt="Base Orchestrator System Prompt",
            available_tools=all_tools,
        )

        # 1. worker_macro must exist
        macro_specs = [s for s in specs if s.worker_id == "worker_macro"]
        assert len(macro_specs) == 1, "worker_macro must be spawned by decompose_research_query"

        macro_spec = macro_specs[0]
        assert macro_spec.role == "Macro & Central Bank Specialist"

        # 2. Toolset checks: get_fedwatch_probabilities, get_treasury_yields, get_interest_rates, get_eia_oil_inventory
        tool_names = {t.get("name") for t in macro_spec.tools}
        expected_macro_tools = {
            "get_fedwatch_probabilities",
            "get_treasury_yields",
            "get_interest_rates",
            "get_eia_oil_inventory",
        }
        for expected_tool in expected_macro_tools:
            assert expected_tool in tool_names, (
                f"Required tool '{expected_tool}' missing from worker_macro toolset: {tool_names}"
            )

        # 3. Mandatory Search Checklist checks in system prompt
        sys_prompt = macro_spec.system_prompt
        assert "MANDATORY MACRO SEARCH CHECKLIST:" in sys_prompt
        assert "Rate Probabilities: Call `get_fedwatch_probabilities`" in sys_prompt
        assert "Yield Curve & Spreads: Call `get_treasury_yields`" in sys_prompt
        assert "Central Bank Baseline Rates: Call `get_interest_rates`" in sys_prompt
        assert "Energy / Inventory: Call `get_eia_oil_inventory`" in sys_prompt
        assert "Calendar & Volatility: Call `get_economic_calendar`" in sys_prompt


# ==============================================================================
# 5. Deep Research Synthesizer: Tools, Executor & Section 6 Prompt
# ==============================================================================

class TestDeepResearchSynthesizer:
    """Verify _run_tier_deep_research Synthesizer execution parameters and Section 6 prompt structure."""

    @pytest.mark.asyncio
    async def test_synthesizer_runs_with_tools_and_tool_executor(self):
        exact_prompt, _ = _load_benchmark_query()
        with patch("telegram_bot.chat_agent.get_client_for_task") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.model = "test-model"
            mock_client.model_name = "test-model"

            # 3 subagents + 1 synthesizer
            mock_client.run_chat_loop.side_effect = [
                # Worker 1: Macro
                {"reply": "Macro findings: FedWatch 89% hike.", "input_tokens": 100, "output_tokens": 50, "tool_calls_made": 3},
                # Worker 2: Tech
                {"reply": "Tech findings: DXY near resistance.", "input_tokens": 100, "output_tokens": 50, "tool_calls_made": 2},
                # Worker 3: Sentiment
                {"reply": "Sentiment findings: Retail extreme short.", "input_tokens": 100, "output_tokens": 50, "tool_calls_made": 1},
                # Synthesizer
                {
                    "reply": "Executive Brief: Comprehensive Macro Event Synthesis.",
                    "input_tokens": 400,
                    "output_tokens": 200,
                    "tool_calls_made": 1,
                    "proposed_action": {
                        "action_type": "save_market_intelligence",
                        "params": {
                            "title": "FOMC September 2026 Trading Plan",
                            "summary": "3-Scenario Execution Plan for Fed decision.",
                            "affected_symbols": ["USDJPY", "XAUUSD", "EURUSD"],
                            "directive": "favor_buy",
                        },
                    },
                },
            ]
            mock_get_client.return_value = mock_client

            mock_tool_executor = MagicMock()
            agent = ChatAgent(settings={}, user_id=99904)

            res = await agent._run_tier_deep_research(
                system_prompt="Base system prompt",
                history=[],
                message=exact_prompt,
                tool_executor=mock_tool_executor,
            )

            # Synthesizer is the 4th run_chat_loop call
            assert mock_client.run_chat_loop.call_count == 4
            synth_call = mock_client.run_chat_loop.call_args_list[3]
            synth_kwargs = synth_call[1]

            # 1. Check tools passed: PROPOSE_ACTION and SAVE_MARKET_INTELLIGENCE
            synth_tools = synth_kwargs.get("tools", [])
            tool_names = [t.get("name") for t in synth_tools]
            assert "propose_action" in tool_names
            assert "save_market_intelligence" in tool_names
            assert PROPOSE_ACTION in synth_tools
            assert SAVE_MARKET_INTELLIGENCE in synth_tools

            # 2. Check tool_executor passed
            assert synth_kwargs.get("tool_executor") is mock_tool_executor

            # 3. Check Synthesizer prompt contains Section 6 Macro Transmission & background persistence directive
            synth_sys = synth_kwargs.get("system_prompt", "")
            assert "6. Ringkasan Transmisi Makro" in synth_sys
            assert "user_market_intel" in synth_sys
            assert "IMPORTANT TRADING PLAN DIRECTIVE" in synth_sys


# ==============================================================================
# 6. Synthesizer Proposed Action Capture & PendingAction Creation
# ==============================================================================

class TestSaveMarketIntelligencePendingAction:
    """Verify ChatAgent captures proposed save_market_intelligence and instantiates PendingAction."""

    def test_create_pending_action_from_save_market_intelligence(self):
        with patch("telegram_bot.chat_agent.get_client_for_task"):
            agent = ChatAgent(settings={}, user_id=99905)

            proposed = {
                "action_type": "save_market_intelligence",
                "params": {
                    "title": "FOMC September 2026 Plan",
                    "summary": "Base Case Hike: buy USDJPY. Invalidation below 142.00.",
                    "affected_symbols": ["USDJPY", "XAUUSD"],
                    "directive": "favor_buy",
                },
                "description": "Simpan Market Intelligence: FOMC September 2026 Plan",
            }

            pending = agent._create_pending_action(proposed)
            assert pending is not None
            assert isinstance(pending, PendingAction)
            assert pending.action_type == "save_market_intelligence"
            assert pending.params["title"] == "FOMC September 2026 Plan"
            assert pending.params["directive"] == "favor_buy"
            assert "USDJPY" in pending.params["affected_symbols"]
            assert pending.description == "Simpan Market Intelligence: FOMC September 2026 Plan"

    @pytest.mark.asyncio
    async def test_deep_research_reply_captures_pending_action_in_agent(self):
        """Simulate ChatAgent handle response with proposed save_market_intelligence action."""
        exact_prompt, _ = _load_benchmark_query()
        with patch("telegram_bot.chat_agent.get_client_for_task") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.model = "test-model"
            mock_client.model_name = "test-model"

            mock_client.run_chat_loop.side_effect = [
                {"reply": "Macro findings", "input_tokens": 50, "output_tokens": 20, "tool_calls_made": 1},
                {"reply": "Tech findings", "input_tokens": 50, "output_tokens": 20, "tool_calls_made": 1},
                {"reply": "Sentiment findings", "input_tokens": 50, "output_tokens": 20, "tool_calls_made": 1},
                {
                    "reply": "Executive Brief: Plan formulated.",
                    "input_tokens": 200,
                    "output_tokens": 100,
                    "tool_calls_made": 1,
                    "proposed_action": {
                        "action_type": "save_market_intelligence",
                        "params": {
                            "title": "FOMC 3-Scenario Trading Plan",
                            "summary": "Consensus 89% Hike. Directive: favor_buy USDJPY.",
                            "affected_symbols": ["USDJPY", "XAUUSD"],
                            "directive": "favor_buy",
                        },
                    },
                },
            ]
            mock_get_client.return_value = mock_client

            agent = ChatAgent(settings={}, user_id=99905)
            # Patch DB persistence to isolate unit test
            with patch.object(agent, "_persist_pending_action", new=AsyncMock()):
                res = await agent._run_tier_deep_research(
                    system_prompt="Base prompt",
                    history=[],
                    message=exact_prompt,
                )

                assert res.get("proposed_action") is not None
                proposed_action = res["proposed_action"]

                pending = agent._create_pending_action(proposed_action)
                assert pending is not None
                assert pending.action_type == "save_market_intelligence"
                assert pending.params["title"] == "FOMC 3-Scenario Trading Plan"

                # Store into agent pending actions
                agent._pending_actions[pending.action_id] = pending
                fetched = await agent.get_pending_action(pending.action_id)
                assert fetched is not None
                assert fetched.action_id == pending.action_id
                assert fetched.action_type == "save_market_intelligence"

    @pytest.mark.asyncio
    async def test_execute_action_dispatches_to_tool_save_market_intelligence(self):
        """Verify _execute_action routes save_market_intelligence to tool_executor."""
        with patch("telegram_bot.chat_agent.get_client_for_task"):
            agent = ChatAgent(settings={}, user_id=99905)

            action = PendingAction(
                action_id="intel_123",
                action_type="save_market_intelligence",
                params={
                    "title": "FOMC September 2026 Plan",
                    "summary": "Consensus Hike.",
                    "affected_symbols": ["USDJPY"],
                    "directive": "favor_buy",
                },
                description="Save Market Intelligence",
            )

            mock_tool_res = {
                "status": "success",
                "intel_id": 42,
                "title": "FOMC September 2026 Plan",
                "directive": "favor_buy",
            }

            mock_executor = MagicMock()
            mock_executor._tool_save_market_intelligence = AsyncMock(return_value=mock_tool_res)

            # Mock get_session and ToolExecutor
            with patch("telegram_bot.chat_agent.get_session"), \
                 patch("analysis.tools.tool_executor.ToolExecutor", return_value=mock_executor):
                res_msg = await agent._execute_action(action)
                assert "✅ Market Intelligence berhasil disimpan!" in res_msg
                assert "ID: #42" in res_msg
                assert "Judul: FOMC September 2026 Plan" in res_msg
                assert "Directive: favor_buy" in res_msg


# ==============================================================================
# 7. Comprehensive End-to-End Pipeline Integration
# ==============================================================================

class TestFullEventProbabilityEndToEndIntegration:
    """Verify entire flow from raw benchmark query to PendingAction registration."""

    @pytest.mark.asyncio
    async def test_full_pipeline_flow(self):
        exact_prompt, _ = _load_benchmark_query()

        with patch("telegram_bot.chat_agent.get_client_for_task") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.model = "test-model"
            mock_client.model_name = "test-model"
            mock_client.run_chat_loop.side_effect = [
                # Worker 1: Macro
                {"reply": "Macro findings: Rates & yields", "input_tokens": 100, "output_tokens": 50, "tool_calls_made": 2},
                # Worker 2: Tech
                {"reply": "Tech findings: Structure & levels", "input_tokens": 100, "output_tokens": 50, "tool_calls_made": 2},
                # Worker 3: Sentiment
                {"reply": "Sentiment findings: Skew & funding", "input_tokens": 100, "output_tokens": 50, "tool_calls_made": 1},
                # Synthesizer
                {
                    "reply": "# Analisis Keputusan FOMC & Press Conference\n3-Skenario Plan formulated.",
                    "input_tokens": 500,
                    "output_tokens": 300,
                    "tool_calls_made": 1,
                    "proposed_action": {
                        "action_type": "save_market_intelligence",
                        "params": {
                            "title": "FOMC September 2026 3-Scenario Directive",
                            "summary": "Base Case Hike: buy USDJPY. Bull Dovish: sell USDJPY.",
                            "affected_symbols": ["USDJPY", "XAUUSD", "EURUSD"],
                            "directive": "favor_buy",
                        },
                    },
                },
            ]
            mock_get_client.return_value = mock_client

            agent = ChatAgent(settings={}, user_id=99906)

            # Step 1: Classification check
            complexity = await agent._classify_query_complexity(exact_prompt)
            assert complexity == "deep_research"

            # Step 2: Macro event query check
            is_macro = agent._is_macro_event_query(exact_prompt)
            assert is_macro is True

            # Step 3: Macro playbooks injection check
            base_prompt = "You are Monika quantitative trading agent."
            injected_sys = agent._inject_macro_playbooks(base_prompt)
            assert "AUTHORITATIVE EVENT PROBABILITY PLAYBOOK" in injected_sys
            assert "AUTHORITATIVE MARKET DYNAMICS FRAMEWORK" in injected_sys

            # Step 4: Subagent pool decomposition check
            pool = DynamicSubagentPool(max_concurrency=4)
            specs = pool.decompose_research_query(
                query=exact_prompt,
                base_system_prompt=injected_sys,
                available_tools=[
                    {"name": "get_fedwatch_probabilities"},
                    {"name": "get_treasury_yields"},
                    {"name": "get_interest_rates"},
                    {"name": "get_eia_oil_inventory"},
                ],
            )
            macro_spec = next(s for s in specs if s.worker_id == "worker_macro")
            assert macro_spec is not None
            assert "MANDATORY MACRO SEARCH CHECKLIST" in macro_spec.system_prompt

            # Step 5 & 6: Run Deep Research & capture PendingAction
            with patch.object(agent, "_persist_pending_action", new=AsyncMock()):
                deep_res = await agent._run_tier_deep_research(
                    system_prompt=injected_sys,
                    history=[],
                    message=exact_prompt,
                )

                assert "# Analisis Keputusan FOMC" in deep_res["reply"]
                assert deep_res["proposed_action"] is not None

                pending = agent._create_pending_action(deep_res["proposed_action"])
                assert pending is not None
                assert pending.action_type == "save_market_intelligence"
                assert pending.params["directive"] == "favor_buy"
                assert pending.params["title"] == "FOMC September 2026 3-Scenario Directive"

                agent._pending_actions[pending.action_id] = pending
                assert pending.action_id in agent._pending_actions
