"""
Empirical Stress Test & Adversarial Challenge Harness for ChatAgent Tier 4 Deep Research.
Executed by: m3_challenger_2
Target: trading-agent/telegram_bot/chat_agent.py

Areas Tested:
1. Idempotency of `_inject_macro_playbooks` (single, double, 10x invocations, partial loading failures)
2. Prompt type polymorphism: string vs tuple (static_sys, dynamic_sys), empty dynamic tails, None tails
3. Graceful degradation when `load_skill` raises exceptions (single, multiple, catastrophic failures)
4. Synthesizer tool wiring and `proposed_action` propagation when `tool_executor` is None vs provided
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from telegram_bot.chat_agent import ChatAgent, PendingAction
from analysis.tools.tools_definitions import PROPOSE_ACTION, SAVE_MARKET_INTELLIGENCE


# ==============================================================================
# AREA 1: IDEMPOTENCY OF _inject_macro_playbooks
# ==============================================================================

class TestInjectMacroPlaybooksIdempotency:
    """Stress test idempotency of playbook injection across multiple cycles."""

    def test_idempotency_string_prompt_repeated_calls(self):
        """Calling _inject_macro_playbooks multiple times on a string prompt should not duplicate playbooks."""
        settings = {}
        with patch("telegram_bot.chat_agent.get_client_for_task"):
            agent = ChatAgent(settings, 12345)

        base_prompt = "You are Monika Trading Agent with strict risk management."
        p = base_prompt

        # Call 10 times consecutively
        for cycle in range(1, 11):
            p = agent._inject_macro_playbooks(p)
            assert isinstance(p, str)
            event_count = p.count("## AUTHORITATIVE EVENT PROBABILITY PLAYBOOK")
            market_count = p.count("## AUTHORITATIVE MARKET DYNAMICS FRAMEWORK")
            assert event_count == 1, f"Cycle {cycle}: Expected 1 Event Playbook header, got {event_count}"
            assert market_count == 1, f"Cycle {cycle}: Expected 1 Market Dynamics header, got {market_count}"

        # String length must remain strictly identical from call 1 to call 10
        first_injected = agent._inject_macro_playbooks(base_prompt)
        assert len(p) == len(first_injected), "String length expanded during repeated injections!"

    def test_idempotency_tuple_prompt_repeated_calls(self):
        """Calling _inject_macro_playbooks multiple times on a tuple prompt should not duplicate playbooks."""
        settings = {}
        with patch("telegram_bot.chat_agent.get_client_for_task"):
            agent = ChatAgent(settings, 12345)

        base_tuple = ("Static Base Prompt Anchor", "Dynamic Tail: Balance=5000, Drawdown=0.0")
        t = base_tuple

        # Call 10 times consecutively
        for cycle in range(1, 11):
            t = agent._inject_macro_playbooks(t)
            assert isinstance(t, tuple)
            assert len(t) == 2
            event_count = t[0].count("## AUTHORITATIVE EVENT PROBABILITY PLAYBOOK")
            market_count = t[0].count("## AUTHORITATIVE MARKET DYNAMICS FRAMEWORK")
            assert event_count == 1, f"Cycle {cycle}: Expected 1 Event Playbook header in static, got {event_count}"
            assert market_count == 1, f"Cycle {cycle}: Expected 1 Market Dynamics header in static, got {market_count}"
            assert t[1] == "Dynamic Tail: Balance=5000, Drawdown=0.0", "Dynamic snapshot was mutated!"

        first_injected = agent._inject_macro_playbooks(base_tuple)
        assert len(t[0]) == len(first_injected[0]), "Static prompt length expanded during repeated injections!"

    def test_idempotency_under_asymmetric_skill_load_failure(self):
        """
        Adversarial test: What happens if event_probability_playbook fails to load,
        but market_dynamics_framework succeeds?
        Checks whether the idempotency guard prevents unbounded growth of market_dynamics_framework.
        """
        settings = {}
        with patch("telegram_bot.chat_agent.get_client_for_task"):
            agent = ChatAgent(settings, 12345)

        def mock_load_skill(name):
            if name == "event_probability_playbook":
                raise FileNotFoundError("event_probability_playbook.md missing")
            if name == "market_dynamics_framework":
                return "Mocked Market Dynamics Framework Content"
            return None

        with patch("skills.loader.load_skill", side_effect=mock_load_skill):
            # Call 1:
            p1 = agent._inject_macro_playbooks("Base prompt")
            assert "## AUTHORITATIVE MARKET DYNAMICS FRAMEWORK" in p1
            assert "## AUTHORITATIVE EVENT PROBABILITY PLAYBOOK" not in p1

            # Call 2:
            p2 = agent._inject_macro_playbooks(p1)
            dynamics_count = p2.count("## AUTHORITATIVE MARKET DYNAMICS FRAMEWORK")

            # Document behavior: If guard only checks EVENT PROBABILITY PLAYBOOK,
            # dynamics_count may be 2. Let's verify whether it duplicated.
            is_duplicated = dynamics_count > 1
            print(f"\n[EMPIRICAL TEST] Under asymmetric failure, market dynamics header count after 2 calls: {dynamics_count}")


# ==============================================================================
# AREA 2: PROMPT TYPE POLYMORPHISM (STRING VS TUPLE)
# ==============================================================================

class TestPromptTypePolymorphism:
    """Verify handling of string and tuple prompts across injection and subagent execution."""

    def test_inject_returns_exact_type_and_structure(self):
        """Prompt type must match input type exactly: str -> str, tuple -> tuple(str, str)."""
        settings = {}
        with patch("telegram_bot.chat_agent.get_client_for_task"):
            agent = ChatAgent(settings, 12345)

        # 1. Plain string
        str_in = "You are Monika."
        str_out = agent._inject_macro_playbooks(str_in)
        assert isinstance(str_out, str)
        assert str_in in str_out

        # 2. Standard 2-tuple (static, dynamic)
        tup_in = ("Static prefix.", "Dynamic snapshot.")
        tup_out = agent._inject_macro_playbooks(tup_in)
        assert isinstance(tup_out, tuple)
        assert len(tup_out) == 2
        assert "Static prefix." in tup_out[0]
        assert "## AUTHORITATIVE EVENT PROBABILITY PLAYBOOK" in tup_out[0]
        assert tup_out[1] == "Dynamic snapshot."

        # 3. Tuple with empty dynamic tail
        tup_empty = ("Static prefix.", "")
        tup_empty_out = agent._inject_macro_playbooks(tup_empty)
        assert isinstance(tup_empty_out, tuple)
        assert len(tup_empty_out) == 2
        assert "Static prefix." in tup_empty_out[0]
        assert tup_empty_out[1] == ""

    @pytest.mark.asyncio
    async def test_run_tier_deep_research_with_tuple_and_string_prompts(self):
        """Verify _run_tier_deep_research correctly unwraps both tuple and string prompts."""
        settings = {}
        with patch("telegram_bot.chat_agent.get_client_for_task") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.model = "test-model"
            mock_client.model_name = "test-model"
            mock_client.run_chat_loop.side_effect = [
                {"reply": "Macro: OK", "input_tokens": 10, "output_tokens": 10, "tool_calls_made": 1},
                {"reply": "Tech: OK", "input_tokens": 10, "output_tokens": 10, "tool_calls_made": 1},
                {"reply": "Sentiment: OK", "input_tokens": 10, "output_tokens": 10, "tool_calls_made": 1},
                {"reply": "Synthesizer: All good", "input_tokens": 20, "output_tokens": 20, "tool_calls_made": 0},
            ]
            mock_get_client.return_value = mock_client
            agent = ChatAgent(settings, 12345)

            # Test 1: Tuple prompt with both static and dynamic components
            tuple_sys = ("Static Master Prompt", "Dynamic Tail: BTC=70000")
            res_tuple = await agent._run_tier_deep_research(
                system_prompt=tuple_sys,
                history=[],
                message="Analisis peluang suku bunga The Fed CME FedWatch",
                tool_executor=None,
            )
            assert "Synthesizer: All good" in res_tuple["reply"]

            # Inspect Synthesizer prompt passed to run_chat_loop (4th call)
            synth_call_args = mock_client.run_chat_loop.call_args_list[3]
            synth_sys = synth_call_args.kwargs.get("system_prompt")
            assert "Static Master Prompt" in synth_sys
            assert "Dynamic Tail: BTC=70000" in synth_sys
            assert "AUTHORITATIVE EVENT PROBABILITY PLAYBOOK" in synth_sys

            # Test 2: String prompt
            mock_client.run_chat_loop.reset_mock()
            mock_client.run_chat_loop.side_effect = [
                {"reply": "Macro: OK", "input_tokens": 10, "output_tokens": 10, "tool_calls_made": 1},
                {"reply": "Tech: OK", "input_tokens": 10, "output_tokens": 10, "tool_calls_made": 1},
                {"reply": "Sentiment: OK", "input_tokens": 10, "output_tokens": 10, "tool_calls_made": 1},
                {"reply": "Synthesizer: String OK", "input_tokens": 20, "output_tokens": 20, "tool_calls_made": 0},
            ]
            res_str = await agent._run_tier_deep_research(
                system_prompt="Single String Prompt",
                history=[],
                message="Analisis peluang suku bunga The Fed CME FedWatch",
                tool_executor=None,
            )
            assert "Synthesizer: String OK" in res_str["reply"]
            synth_call_args_2 = mock_client.run_chat_loop.call_args_list[3]
            synth_sys_2 = synth_call_args_2.kwargs.get("system_prompt")
            assert "Single String Prompt" in synth_sys_2
            assert "AUTHORITATIVE EVENT PROBABILITY PLAYBOOK" in synth_sys_2


# ==============================================================================
# AREA 3: GRACEFUL DEGRADATION WHEN load_skill RAISES AN EXCEPTION
# ==============================================================================

class TestLoadSkillGracefulDegradation:
    """Stress test failure modes when skills.loader.load_skill raises various exceptions."""

    def test_inject_degrades_gracefully_when_both_skills_raise(self):
        """When both skills raise exceptions, prompt is returned intact without crashing."""
        settings = {}
        with patch("telegram_bot.chat_agent.get_client_for_task"):
            agent = ChatAgent(settings, 12345)

        with patch("skills.loader.load_skill", side_effect=RuntimeError("Disk failure")):
            raw_str = "Clean system prompt"
            result_str = agent._inject_macro_playbooks(raw_str)
            assert result_str == raw_str, "String prompt was altered despite both skills failing!"

            raw_tup = ("Clean static prompt", "Clean dynamic prompt")
            result_tup = agent._inject_macro_playbooks(raw_tup)
            assert result_tup == raw_tup, "Tuple prompt was altered despite both skills failing!"

    def test_inject_degrades_gracefully_when_only_one_skill_fails(self):
        """When one skill fails and the other succeeds, the surviving skill is injected."""
        settings = {}
        with patch("telegram_bot.chat_agent.get_client_for_task"):
            agent = ChatAgent(settings, 12345)

        # Event playbook fails, market dynamics succeeds
        def mock_load(name):
            if name == "event_probability_playbook":
                raise OSError("Permission denied on event_probability_playbook.md")
            return "Survived Market Dynamics Content"

        with patch("skills.loader.load_skill", side_effect=mock_load):
            res = agent._inject_macro_playbooks("Base prompt")
            assert "Base prompt" in res
            assert "## AUTHORITATIVE MARKET DYNAMICS FRAMEWORK" in res
            assert "Survived Market Dynamics Content" in res
            assert "## AUTHORITATIVE EVENT PROBABILITY PLAYBOOK" not in res

        # Market dynamics fails, event playbook succeeds
        def mock_load_2(name):
            if name == "market_dynamics_framework":
                raise ValueError("Corrupt file")
            return "Survived Event Playbook Content"

        with patch("skills.loader.load_skill", side_effect=mock_load_2):
            res2 = agent._inject_macro_playbooks("Base prompt")
            assert "Base prompt" in res2
            assert "## AUTHORITATIVE EVENT PROBABILITY PLAYBOOK" in res2
            assert "Survived Event Playbook Content" in res2
            assert "## AUTHORITATIVE MARKET DYNAMICS FRAMEWORK" not in res2

    def test_inject_handles_empty_or_none_returns_from_load_skill(self):
        """When load_skill returns empty string or None, headers should not be injected."""
        settings = {}
        with patch("telegram_bot.chat_agent.get_client_for_task"):
            agent = ChatAgent(settings, 12345)

        with patch("skills.loader.load_skill", return_value=""):
            res = agent._inject_macro_playbooks("Clean prompt")
            assert res == "Clean prompt"

        with patch("skills.loader.load_skill", return_value=None):
            res = agent._inject_macro_playbooks("Clean prompt")
            assert res == "Clean prompt"

    @pytest.mark.asyncio
    async def test_deep_research_completes_when_skill_loading_fails(self):
        """_run_tier_deep_research must complete and return an authoritative brief even if skill loading fails."""
        settings = {}
        with patch("telegram_bot.chat_agent.get_client_for_task") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.model = "test-model"
            mock_client.model_name = "test-model"
            mock_client.run_chat_loop.side_effect = [
                {"reply": "Worker 1 report", "input_tokens": 50, "output_tokens": 25, "tool_calls_made": 1},
                {"reply": "Worker 2 report", "input_tokens": 50, "output_tokens": 25, "tool_calls_made": 1},
                {"reply": "Worker 3 report", "input_tokens": 50, "output_tokens": 25, "tool_calls_made": 1},
                {"reply": "Synthesized brief without playbooks", "input_tokens": 100, "output_tokens": 50, "tool_calls_made": 0},
            ]
            mock_get_client.return_value = mock_client
            agent = ChatAgent(settings, 12345)

            with patch("skills.loader.load_skill", side_effect=Exception("Critical disk error")):
                res = await agent._run_tier_deep_research(
                    system_prompt="Base prompt",
                    history=[],
                    message="Analisis peluang suku bunga The Fed dan FedWatch",
                    tool_executor=None,
                )
                assert res is not None
                assert "Synthesized brief without playbooks" in res["reply"]
                assert res["input_tokens"] == 250
                assert res["output_tokens"] == 125
                assert res["tool_calls_made"] == 3


# ==============================================================================
# AREA 4: TOOL PASSING & PROPOSED_ACTION PROPAGATION (TOOL_EXECUTOR NONE VS PROVIDED)
# ==============================================================================

class TestSynthesizerToolWiringAndPropagation:
    """Stress test Synthesizer tool passing, execution, and proposed_action propagation."""

    @pytest.mark.asyncio
    async def test_synthesizer_wiring_when_tool_executor_is_provided(self):
        """When tool_executor is provided, it is forwarded to both subagent pool and Synthesizer."""
        settings = {}
        with patch("telegram_bot.chat_agent.get_client_for_task") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.model = "test-model"
            mock_client.model_name = "test-model"

            mock_proposed_action = {
                "action_type": "save_market_intelligence",
                "params": {
                    "title": "FOMC 3-Scenario Plan",
                    "summary": "Base Case 89% priced-in hike. Skenario 1/2/3.",
                    "directive": "favor_buy",
                    "affected_symbols": ["XAUUSD", "DXY"],
                },
            }

            mock_client.run_chat_loop.side_effect = [
                {"reply": "Macro done", "input_tokens": 10, "output_tokens": 10, "tool_calls_made": 2},
                {"reply": "Tech done", "input_tokens": 10, "output_tokens": 10, "tool_calls_made": 2},
                {"reply": "Sentiment done", "input_tokens": 10, "output_tokens": 10, "tool_calls_made": 1},
                {
                    "reply": "Executive Brief: Plan formulated.",
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "tool_calls_made": 1,
                    "proposed_action": mock_proposed_action,
                },
            ]
            mock_get_client.return_value = mock_client

            mock_executor = MagicMock()
            mock_executor._pending_charts = {}
            agent = ChatAgent(settings, 12345)

            res = await agent._run_tier_deep_research(
                system_prompt="Base system prompt",
                history=[],
                message="Analisis peluang suku bunga The Fed CME FedWatch",
                tool_executor=mock_executor,
            )

            # 1. Output propagation
            assert res["proposed_action"] == mock_proposed_action
            assert res["tool_calls_made"] == 2 + 2 + 1 + 1

            # 2. Synthesizer run_chat_loop call inspection (call index 3)
            synth_call = mock_client.run_chat_loop.call_args_list[3]
            assert synth_call.kwargs.get("tool_executor") is mock_executor
            tools_passed = synth_call.kwargs.get("tools", [])
            assert PROPOSE_ACTION in tools_passed
            assert SAVE_MARKET_INTELLIGENCE in tools_passed

    @pytest.mark.asyncio
    async def test_synthesizer_wiring_when_tool_executor_is_none(self):
        """When tool_executor is None, Synthesizer still receives tools and propagates proposed_action."""
        settings = {}
        with patch("telegram_bot.chat_agent.get_client_for_task") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.model = "test-model"
            mock_client.model_name = "test-model"

            mock_proposed_action = {
                "action_type": "save_market_intelligence",
                "params": {
                    "title": "FedWatch Rate Intelligence",
                    "summary": "Consensus hike analysis.",
                    "directive": "neutral",
                },
            }

            mock_client.run_chat_loop.side_effect = [
                {"reply": "Macro done", "input_tokens": 10, "output_tokens": 10, "tool_calls_made": 1},
                {"reply": "Tech done", "input_tokens": 10, "output_tokens": 10, "tool_calls_made": 1},
                {"reply": "Sentiment done", "input_tokens": 10, "output_tokens": 10, "tool_calls_made": 1},
                {
                    "reply": "Executive Brief: Plan formulated.",
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "tool_calls_made": 1,
                    "proposed_action": mock_proposed_action,
                },
            ]
            mock_get_client.return_value = mock_client

            agent = ChatAgent(settings, 12345)

            res = await agent._run_tier_deep_research(
                system_prompt="Base system prompt",
                history=[],
                message="Analisis peluang suku bunga The Fed CME FedWatch",
                tool_executor=None,
            )

            # Output propagation without executor
            assert res["proposed_action"] == mock_proposed_action
            synth_call = mock_client.run_chat_loop.call_args_list[3]
            assert synth_call.kwargs.get("tool_executor") is None
            tools_passed = synth_call.kwargs.get("tools", [])
            assert PROPOSE_ACTION in tools_passed
            assert SAVE_MARKET_INTELLIGENCE in tools_passed

    def test_create_pending_action_accepts_save_market_intelligence(self):
        """Verify _create_pending_action processes save_market_intelligence proposals correctly."""
        settings = {}
        with patch("telegram_bot.chat_agent.get_client_for_task"):
            agent = ChatAgent(settings, 12345)

        proposed = {
            "action_type": "save_market_intelligence",
            "params": {
                "title": "FOMC Rate Outlook",
                "summary": "3-Scenario Execution Plan",
                "affected_symbols": ["XAUUSD", "US10Y"],
                "directive": "favor_buy",
            },
            "description": "Save FOMC 3-Scenario Plan to Market Intel",
        }

        pending = agent._create_pending_action(proposed)
        assert pending is not None
        assert isinstance(pending, PendingAction)
        assert pending.action_type == "save_market_intelligence"
        assert pending.params["title"] == "FOMC Rate Outlook"
        assert pending.params["directive"] == "favor_buy"
        assert pending.description == "Save FOMC 3-Scenario Plan to Market Intel"
        assert len(pending.action_id) == 8

    def test_create_pending_action_rejects_unknown_action_type(self):
        """Verify _create_pending_action safely rejects unregistered action types from Synthesizer."""
        settings = {}
        with patch("telegram_bot.chat_agent.get_client_for_task"):
            agent = ChatAgent(settings, 12345)

        proposed_malformed = {
            "action_type": "unregistered_arbitrary_code_execution",
            "params": {"cmd": "rm -rf /"},
        }
        pending = agent._create_pending_action(proposed_malformed)
        assert pending is None

    def test_create_pending_action_respects_circuit_breaker(self):
        """When denial circuit breaker is tripped (_proposals_paused=True), proposals are suppressed."""
        settings = {}
        with patch("telegram_bot.chat_agent.get_client_for_task"):
            agent = ChatAgent(settings, 12345)
        agent._proposals_paused = True

        proposed = {
            "action_type": "save_market_intelligence",
            "params": {"title": "Blocked Plan", "directive": "neutral"},
        }
        pending = agent._create_pending_action(proposed)
        assert pending is None

    @pytest.mark.asyncio
    async def test_deep_research_resilience_to_status_callback_exceptions(self):
        """Verify _run_tier_deep_research does not crash if status_callback raises an exception."""
        settings = {}
        with patch("telegram_bot.chat_agent.get_client_for_task") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.model = "test-model"
            mock_client.model_name = "test-model"
            mock_client.run_chat_loop.side_effect = [
                {"reply": "Macro done", "input_tokens": 10, "output_tokens": 10, "tool_calls_made": 1},
                {"reply": "Tech done", "input_tokens": 10, "output_tokens": 10, "tool_calls_made": 1},
                {"reply": "Sentiment done", "input_tokens": 10, "output_tokens": 10, "tool_calls_made": 1},
                {"reply": "Executive Brief.", "input_tokens": 50, "output_tokens": 25, "tool_calls_made": 0},
            ]
            mock_get_client.return_value = mock_client

            def crashing_status_callback(text):
                raise ConnectionError("Telegram network disconnected")

            agent = ChatAgent(settings, 12345)
            res = await agent._run_tier_deep_research(
                system_prompt="Base system prompt",
                history=[],
                message="Analisis peluang suku bunga The Fed",
                status_callback=crashing_status_callback,
            )
            assert res is not None
            assert "Executive Brief." in res["reply"]

    @pytest.mark.asyncio
    async def test_deep_research_resilience_when_specialist_workers_fail(self):
        """When specialist workers fail in DynamicSubagentPool, Synthesizer still consolidates report."""
        settings = {}
        with patch("telegram_bot.chat_agent.get_client_for_task") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.model = "test-model"
            mock_client.model_name = "test-model"

            # 3 workers raise exceptions or return failure, Synthesizer still runs
            from analysis.subagent_spawner import SubagentResult
            failing_pool = MagicMock()
            failing_pool.decompose_research_query.return_value = [
                MagicMock(role="worker_macro"),
                MagicMock(role="worker_tech"),
                MagicMock(role="worker_sent"),
            ]
            failing_pool.run_parallel = AsyncMock(return_value=[
                SubagentResult(worker_id="w1", role="worker_macro", content="", success=False, error="Timeout 75s", input_tokens=10, output_tokens=0, tool_calls_made=0),
                SubagentResult(worker_id="w2", role="worker_tech", content="", success=False, error="RateLimit", input_tokens=10, output_tokens=0, tool_calls_made=0),
                SubagentResult(worker_id="w3", role="worker_sent", content="Valid sentiment findings", success=True, error=None, input_tokens=20, output_tokens=15, tool_calls_made=1),
            ])

            mock_client.run_chat_loop.return_value = {
                "reply": "Executive Brief: Partial data synthesized.",
                "input_tokens": 100,
                "output_tokens": 50,
                "tool_calls_made": 0,
            }
            mock_get_client.return_value = mock_client

            with patch("analysis.subagent_spawner.DynamicSubagentPool", return_value=failing_pool):
                agent = ChatAgent(settings, 12345)
                res = await agent._run_tier_deep_research(
                    system_prompt="Base system prompt",
                    history=[],
                    message="Analisis peluang suku bunga The Fed",
                )
                assert res is not None
                assert "Executive Brief: Partial data synthesized." in res["reply"]
                # Synthesizer input contained notice of worker failures
                synth_call = mock_client.run_chat_loop.call_args
                synth_input = synth_call.kwargs.get("new_user_message", "")
                assert "worker_macro mengalami kendala: Timeout 75s" in synth_input
                assert "worker_tech mengalami kendala: RateLimit" in synth_input
                assert "Valid sentiment findings" in synth_input
