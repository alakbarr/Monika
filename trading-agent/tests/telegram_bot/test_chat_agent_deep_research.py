import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from telegram_bot.chat_agent import ChatAgent
from analysis.tools.tools_definitions import PROPOSE_ACTION, SAVE_MARKET_INTELLIGENCE


@pytest.mark.asyncio
async def test_run_tier_deep_research_parallel_workers():
    settings = {}
    with patch("telegram_bot.chat_agent.get_client_for_task") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.model = "test-model"
        mock_client.model_name = "test-model"
        mock_client.run_chat_loop.side_effect = [
            # Worker 1: Macro
            {"reply": "Macro findings: Yields falling, dovish Fed.", "input_tokens": 100, "output_tokens": 50, "tool_calls_made": 2},
            # Worker 2: Tech
            {"reply": "Tech findings: Bullish FVG at 2650.", "input_tokens": 120, "output_tokens": 60, "tool_calls_made": 3},
            # Worker 3: Sentiment
            {"reply": "Sentiment findings: Retail 80% short.", "input_tokens": 90, "output_tokens": 40, "tool_calls_made": 1},
            # Synthesizer
            {"reply": "Executive Brief: Strong bullish confluence on XAUUSD.", "input_tokens": 300, "output_tokens": 150, "tool_calls_made": 0},
        ]
        mock_get_client.return_value = mock_client

        agent = ChatAgent(settings, 12345)
        res = await agent._run_tier_deep_research(
            system_prompt="Base prompt",
            history=[],
            message="Investigasi mendalam prospek XAUUSD",
            tool_executor=None,
        )

        assert "Executive Brief" in res["reply"]
        assert res["input_tokens"] == 100 + 120 + 90 + 300
        assert res["output_tokens"] == 50 + 60 + 40 + 150
        assert res["tool_calls_made"] == 2 + 3 + 1 + 0
        assert mock_client.run_chat_loop.call_count == 4


@pytest.mark.asyncio
async def test_classify_query_complexity_macro_events():
    """Verify macro event probability queries (including contoh_pertanyaan.md) route to deep_research."""
    settings = {}
    with patch("telegram_bot.chat_agent.get_client_for_task") as mock_get_client:
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client
        agent = ChatAgent(settings, 12345)

        # 1. Benchmark query from contoh_pertanyaan.md
        contoh_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "contoh_pertanyaan.md")
        assert os.path.exists(contoh_path), f"contoh_pertanyaan.md not found at {contoh_path}"
        with open(contoh_path, "r", encoding="utf-8") as f:
            full_content = f.read()

        # Extract only the question part or test full content
        res_full = await agent._classify_query_complexity(full_content)
        assert res_full == "deep_research", f"contoh_pertanyaan.md full content should be deep_research, got {res_full}"

        sample_question = (
            "Analisis peluang kemungkinan keputusan suku bunga The Fed 16/17 September 2026 yang akan diumumkan "
            "dalam beberapa jam ke depan. Di CME Fedwatch proyeksinya 89% The Fed akan menaikkan suku bunga (HIKE), "
            "sedangkan sisanya adalah HOLD. Tapi apakah ini (HIKE) sudah pasti? Apakah ada history The Fed tidak searah "
            "dengan harapan pasar? Apa yang akan dinyatakan Kevin Warsh saat press conference, hawkish atau dovish?"
        )
        res_sample = await agent._classify_query_complexity(sample_question)
        assert res_sample == "deep_research", f"Sample question should be deep_research, got {res_sample}"

        # 2. Typical macro event probability queries
        macro_queries = [
            "Bagaimana proyeksi suku bunga FOMC mendatang dan probabilitas CME FedWatch?",
            "Analisis probabilitas rate hike The Fed pada pertemuan 16 September",
            "Apakah ada preseden The Fed mengecoh pasar pada keputusan suku bunga?",
            "Analisis kebijakan moneter bank sentral dan nada press conference Kevin Warsh",
            "Peluang rate cut ECB vs The Fed dan reaksi pasar terhadap dot plot",
            "What is the probability of a rate hike in CME FedWatch for upcoming FOMC meeting?",
        ]
        for mq in macro_queries:
            res = await agent._classify_query_complexity(mq)
            assert res == "deep_research", f"Query '{mq}' should be deep_research, got {res}"

        # 3. Simple non-macro queries should not trigger deep_research
        simple_queries = [
            "halo",
            "status",
            "posisi",
            "berapa pnl hari ini",
            "cek saldo akun",
        ]
        for sq in simple_queries:
            res = await agent._classify_query_complexity(sq)
            assert res == "simple", f"Query '{sq}' should be simple, got {res}"


@pytest.mark.asyncio
async def test_is_macro_event_query_and_inject_macro_playbooks():
    """Verify _is_macro_event_query detection and dynamic playbook injection into system prompt."""
    settings = {}
    with patch("telegram_bot.chat_agent.get_client_for_task") as mock_get_client:
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client
        agent = ChatAgent(settings, 12345)

        # 1. Detection checks
        assert agent._is_macro_event_query("Analisis peluang keputusan suku bunga The Fed") is True
        assert agent._is_macro_event_query("CME Fedwatch 89% hike vs hold") is True
        assert agent._is_macro_event_query("Press conference Jerome Powell hawkish atau dovish?") is True
        assert agent._is_macro_event_query("halo apa kabar") is False
        assert agent._is_macro_event_query("cek status posisi") is False
        assert agent._is_macro_event_query("") is False

        # 2. Injection with string system_prompt
        base_prompt = "You are Monika Trading Agent."
        injected_str = agent._inject_macro_playbooks(base_prompt)
        assert isinstance(injected_str, str)
        assert base_prompt in injected_str
        assert "## AUTHORITATIVE EVENT PROBABILITY PLAYBOOK" in injected_str
        assert "## AUTHORITATIVE MARKET DYNAMICS FRAMEWORK" in injected_str
        # Verify content from R1 playbook is present
        assert "PROTOKOL THINKING FLOW 5 TAHAP" in injected_str or "THINKING FLOW" in injected_str.upper()

        # Idempotency check for string
        double_injected_str = agent._inject_macro_playbooks(injected_str)
        assert double_injected_str.count("## AUTHORITATIVE EVENT PROBABILITY PLAYBOOK") == 1

        # 3. Injection with tuple system_prompt (static_prompt, dynamic_snapshot)
        tuple_prompt = ("Static Anchor Prompt", "Dynamic Session Data: Balance=1000")
        injected_tuple = agent._inject_macro_playbooks(tuple_prompt)
        assert isinstance(injected_tuple, tuple)
        assert len(injected_tuple) == 2
        assert "Static Anchor Prompt" in injected_tuple[0]
        assert "## AUTHORITATIVE EVENT PROBABILITY PLAYBOOK" in injected_tuple[0]
        assert "## AUTHORITATIVE MARKET DYNAMICS FRAMEWORK" in injected_tuple[0]
        assert injected_tuple[1] == "Dynamic Session Data: Balance=1000"

        # Idempotency check for tuple
        double_injected_tuple = agent._inject_macro_playbooks(injected_tuple)
        assert double_injected_tuple[0].count("## AUTHORITATIVE EVENT PROBABILITY PLAYBOOK") == 1


@pytest.mark.asyncio
async def test_run_tier_deep_research_synthesizer_tools_and_trading_plan():
    """Verify _run_tier_deep_research injects playbooks, passes tools to Synthesizer, and mandates 3-scenario plan."""
    settings = {}
    with patch("telegram_bot.chat_agent.get_client_for_task") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.model = "test-model"
        mock_client.model_name = "test-model"

        # Return mock responses for 3 specialists + 1 synthesizer
        mock_client.run_chat_loop.side_effect = [
            # Worker 1: Macro
            {"reply": "Macro findings: FedWatch 89% hike priced-in.", "input_tokens": 150, "output_tokens": 80, "tool_calls_made": 2},
            # Worker 2: Tech
            {"reply": "Tech findings: DXY resistance at 104.50.", "input_tokens": 130, "output_tokens": 70, "tool_calls_made": 2},
            # Worker 3: Sentiment
            {"reply": "Sentiment findings: Extreme hawkish positioning.", "input_tokens": 110, "output_tokens": 60, "tool_calls_made": 1},
            # Synthesizer
            {
                "reply": "Executive Brief: 3-Scenario Trading Plan formulated.",
                "input_tokens": 500,
                "output_tokens": 300,
                "tool_calls_made": 1,
                "proposed_action": {
                    "action_type": "save_market_intelligence",
                    "params": {
                        "title": "FOMC Rate Decision 3-Scenario Plan",
                        "summary": "Base Case Hike 25bps. Directive: favor_buy USDJPY post-presser.",
                        "affected_symbols": ["XAUUSD", "USDJPY", "EURUSD"],
                        "directive": "favor_buy",
                    },
                },
            },
        ]
        mock_get_client.return_value = mock_client

        mock_tool_executor = MagicMock()
        agent = ChatAgent(settings, 12345)

        macro_message = "Analisis peluang kemungkinan keputusan suku bunga The Fed dan probabilitas CME FedWatch"
        res = await agent._run_tier_deep_research(
            system_prompt="Base system prompt",
            history=[],
            message=macro_message,
            tool_executor=mock_tool_executor,
        )

        assert "Executive Brief" in res["reply"]
        assert res["proposed_action"] is not None
        assert res["proposed_action"]["action_type"] == "save_market_intelligence"
        assert res["proposed_action"]["params"]["title"] == "FOMC Rate Decision 3-Scenario Plan"

        # Verify Synthesizer call parameters (4th call to run_chat_loop)
        assert mock_client.run_chat_loop.call_count == 4
        synth_call = mock_client.run_chat_loop.call_args_list[3]
        _, synth_kwargs = synth_call

        # 1. Tools passed to synthesizer
        synth_tools = synth_kwargs.get("tools", [])
        tool_names = [t.get("name") for t in synth_tools]
        assert "propose_action" in tool_names, f"Expected propose_action in {tool_names}"
        assert "save_market_intelligence" in tool_names, f"Expected save_market_intelligence in {tool_names}"
        assert PROPOSE_ACTION in synth_tools
        assert SAVE_MARKET_INTELLIGENCE in synth_tools

        # 2. Tool executor passed
        assert synth_kwargs.get("tool_executor") is mock_tool_executor

        # 3. System prompt contains injected playbooks
        synth_sys = synth_kwargs.get("system_prompt", "")
        assert "AUTHORITATIVE EVENT PROBABILITY PLAYBOOK" in synth_sys
        assert "AUTHORITATIVE MARKET DYNAMICS FRAMEWORK" in synth_sys

        # 4. System prompt contains Macro Transmission and background persistence directive
        assert "6. Ringkasan Transmisi Makro" in synth_sys
        assert "user_market_intel" in synth_sys
        assert "IMPORTANT TRADING PLAN DIRECTIVE" in synth_sys


@pytest.mark.asyncio
async def test_system_prompt_relaxed_character_limit():
    """Verify _build_system_prompt relaxes <= 3000 chars restriction for deep research / macro event investigations."""
    settings = {}
    with patch("telegram_bot.chat_agent.get_client_for_task") as mock_get_client:
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client
        agent = ChatAgent(settings, 12345)

        mock_session = AsyncMock()
        prompt_res = await agent._build_system_prompt(mock_session)
        static_prompt = prompt_res[0] if isinstance(prompt_res, tuple) else prompt_res

        # Verify old rigid restriction is gone
        assert "- Limit response length <= 3000 characters." not in static_prompt

        # Verify relaxed institutional-grade multi-chunk phrasing is present
        assert "For standard conversational turns, keep response length concise (<= 3000 characters)" in static_prompt
        assert "For deep research, comprehensive macro event probability analyses, or complex strategic investigations" in static_prompt
        assert "exhaustive institutional-grade briefs without arbitrary character limits" in static_prompt
        assert "multi-chunk message delivery" in static_prompt
