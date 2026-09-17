"""
Unit tests for Phase 2: Event-Driven Core & Unified Agent Harness (Pi Pattern).
Covers:
1. EventBus typed pub-sub, priority ordering, exception isolation, polymorphic dispatch, and buffered queue.
2. AgentHarness multi-turn ReAct execution, anti-oscillation tool hashing, quota filtering, mandatory nudging, and state preservation.
3. Scheduler integration: FlashCrashDetector, TrailingStopManager, and PositionGuardian on_tick handlers.
4. Main TradingAgent EventBus wiring and tick broadcasting.
"""

import asyncio
import json
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from utils.protocol.event_bus import (
    AppEvent,
    TickPriceEvent,
    BarClosedEvent,
    OrderStateChangedEvent,
    RiskBreachEvent,
    CircuitBreakerEvent,
    EventBus,
    get_event_bus,
    reset_event_bus,
)
from analysis.harness.agent_harness import AgentHarness
from analysis.providers.base_provider import BaseLLMClient, MockBlock, MockResponse
from scheduler.flash_crash_detector import FlashCrashDetector
from scheduler.trailing_stop_manager import TrailingStopManager
from scheduler.position_guardian import PositionGuardian
from scheduler.market_data_scheduler import MarketDataScheduler
from main import TradingAgent
from database.models import Position, SystemConfig


# ==============================================================================
# 1. EventBus Unit Tests
# ==============================================================================

class TestEventBusCore:
    def setup_method(self):
        self.bus = EventBus()

    @pytest.mark.asyncio
    async def test_event_bus_pub_sub_typed(self):
        """Verify typed event subscription receives matching events."""
        received = []

        async def handler(evt: TickPriceEvent):
            received.append(evt)

        self.bus.subscribe(TickPriceEvent, handler)

        tick = TickPriceEvent(symbol="XAUUSD", bid=2000.0, ask=2000.5, last=2000.25)
        await self.bus.publish(tick)

        assert len(received) == 1
        assert received[0].symbol == "XAUUSD"
        assert received[0].bid == 2000.0
        assert received[0].ask == 2000.5

    @pytest.mark.asyncio
    async def test_event_bus_priority_ordering(self):
        """Verify higher priority handlers execute before lower priority handlers."""
        execution_order = []

        async def low_priority_handler(evt: AppEvent):
            execution_order.append("low")

        async def high_priority_handler(evt: AppEvent):
            execution_order.append("high")

        async def critical_handler(evt: AppEvent):
            execution_order.append("critical")

        self.bus.subscribe(TickPriceEvent, low_priority_handler, priority=0)
        self.bus.subscribe(TickPriceEvent, critical_handler, priority=100)
        self.bus.subscribe(TickPriceEvent, high_priority_handler, priority=50)

        tick = TickPriceEvent(symbol="EURUSD", bid=1.0850, ask=1.0852)
        await self.bus.publish(tick)

        assert execution_order == ["critical", "high", "low"]

    @pytest.mark.asyncio
    async def test_event_bus_unsubscribe(self):
        """Verify unsubscription successfully detaches handler."""
        received = []

        async def handler(evt: BarClosedEvent):
            received.append(evt)

        self.bus.subscribe(BarClosedEvent, handler)
        bar1 = BarClosedEvent(symbol="BTCUSD", timeframe="H1", open=60000, high=61000, low=59500, close=60500, volume=120)
        await self.bus.publish(bar1)
        assert len(received) == 1

        unsub_ok = self.bus.unsubscribe(BarClosedEvent, handler)
        assert unsub_ok is True

        bar2 = BarClosedEvent(symbol="BTCUSD", timeframe="H1", open=60500, high=62000, low=60000, close=61500, volume=150)
        await self.bus.publish(bar2)
        assert len(received) == 1  # No additional event received

    @pytest.mark.asyncio
    async def test_event_bus_exception_isolation(self):
        """Verify exception in one subscriber does not crash publisher or block other subscribers."""
        received = []

        async def failing_handler(evt: AppEvent):
            raise RuntimeError("Database connection suddenly dropped in subscriber!")

        async def healthy_handler(evt: AppEvent):
            received.append(evt)

        self.bus.subscribe(RiskBreachEvent, failing_handler, priority=10)
        self.bus.subscribe(RiskBreachEvent, healthy_handler, priority=5)

        breach = RiskBreachEvent(breach_type="max_drawdown", severity="critical", details={"loss": 500})
        results = await self.bus.publish(breach)

        assert len(received) == 1
        assert received[0] == breach
        # Failure is captured and isolated
        assert any(isinstance(r, RuntimeError) for r in results)

    @pytest.mark.asyncio
    async def test_event_bus_polymorphic_dispatch(self):
        """Verify subscriber to base AppEvent receives all subclasses."""
        all_events = []

        async def catch_all(evt: AppEvent):
            all_events.append(evt)

        self.bus.subscribe(AppEvent, catch_all)

        tick = TickPriceEvent(symbol="USDJPY", bid=155.0, ask=155.03)
        cb = CircuitBreakerEvent(component="FlashCrash", reason="Spike 5x ATR")
        order = OrderStateChangedEvent(order_id="ORD-1", symbol="USDJPY", old_state="PENDING", new_state="FILLED")

        await self.bus.publish(tick)
        await self.bus.publish(cb)
        await self.bus.publish(order)

        assert len(all_events) == 3
        assert isinstance(all_events[0], TickPriceEvent)
        assert isinstance(all_events[1], CircuitBreakerEvent)
        assert isinstance(all_events[2], OrderStateChangedEvent)

    @pytest.mark.asyncio
    async def test_event_bus_buffered_queue(self):
        """Verify buffered queue decoupled consumption."""
        received = []

        async def on_tick(evt: TickPriceEvent):
            received.append(evt)

        self.bus.subscribe(TickPriceEvent, on_tick)
        worker_task = self.bus.start_queue_worker("ticks")

        t1 = TickPriceEvent(symbol="GBPUSD", bid=1.2800, ask=1.2802)
        t2 = TickPriceEvent(symbol="GBPUSD", bid=1.2805, ask=1.2807)

        await self.bus.publish_buffered(t1, "ticks")
        await self.bus.publish_buffered(t2, "ticks")

        # Allow worker event loop cycle
        await asyncio.sleep(0.05)

        self.bus.stop_workers()
        assert len(received) == 2
        assert received[0].bid == 1.2800
        assert received[1].bid == 1.2805

    @pytest.mark.asyncio
    async def test_event_bus_publish_nowait(self):
        """Verify non-blocking fire-and-forget publish."""
        received = []

        async def handler(evt: AppEvent):
            received.append(evt)

        self.bus.subscribe(CircuitBreakerEvent, handler)
        task = self.bus.publish_nowait(CircuitBreakerEvent(component="RiskGate", reason="Spread ceiling"))
        assert task is not None
        await task
        assert len(received) == 1

    def test_event_dataclasses_immutability(self):
        """Verify frozen immutability of domain events."""
        tick = TickPriceEvent(symbol="XAUUSD", bid=2000.0, ask=2000.5)
        with pytest.raises(Exception):
            tick.bid = 2005.0  # Cannot mutate frozen dataclass


# ==============================================================================
# 2. AgentHarness (Pi Pattern) Unit Tests
# ==============================================================================

class DummyLLMClient(BaseLLMClient):
    """Mock LLM client for harness testing."""
    def __init__(self, responses: list):
        super().__init__(model="test-llm")
        self.responses = responses
        self.call_count = 0

    async def generate(self, prompt: str, system: str = "", temperature=None, max_tokens=None):
        return "text"

    async def classify_json(self, prompt: str, system_prompt=None, schema=None, temperature=None, max_tokens=None):
        return {}

    async def run_chat_loop(self, system_prompt, conversation_history, new_user_message, tools, tool_executor=None):
        return {}

    async def run_tool_agent(self, messages, tools, system_prompt):
        resp = self.responses[self.call_count]
        self.call_count += 1
        return resp


class TestAgentHarness:
    @pytest.mark.asyncio
    async def test_agent_harness_multi_turn_execution(self):
        """Verify standard 2-turn execution: tool call then final completion."""
        # Turn 1: call tool get_atr_H4
        resp1 = MockResponse(
            content=[
                MockBlock(type="tool_use", id="call_1", name="get_atr_H4", input={"symbol": "XAUUSD"})
            ],
            stop_reason="tool_use",
            input_tokens=100,
            output_tokens=50,
        )
        # Turn 2: conclude with submit_asset_analysis
        resp2 = MockResponse(
            content=[
                MockBlock(type="text", text="Based on ATR, market is steady."),
                MockBlock(type="tool_use", id="call_2", name="submit_asset_analysis", input={"symbol": "XAUUSD", "decision": "wait"})
            ],
            stop_reason="tool_use",
            input_tokens=150,
            output_tokens=60,
        )
        # Turn 3: completed
        resp3 = MockResponse(
            content=[MockBlock(type="text", text="Analysis complete.")],
            stop_reason="end_turn",
            input_tokens=180,
            output_tokens=20,
        )

        client = DummyLLMClient([resp1, resp2, resp3])
        harness = AgentHarness(client, settings={}, max_tool_turns=5)

        mock_executor = AsyncMock()
        mock_executor.execute = AsyncMock(side_effect=[
            {"atr_14": 15.5},
            {"status": "submitted", "decision": "wait"}
        ])

        result = await harness.run_agent(
            session=None,
            system_prompt="You are a trading analyst.",
            user_message="Analyze XAUUSD",
            tools=[{"name": "get_atr_H4"}, {"name": "submit_asset_analysis"}],
            stage_name="per_asset_XAUUSD",
            tool_executor=mock_executor,
        )

        assert result["success"] is True
        assert result["turns"] == 3
        assert result["tool_calls_made"] == 2
        assert result["final_text"] == "Analysis complete."
        assert result["input_tokens"] == 430
        assert result["output_tokens"] == 130
        assert mock_executor.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_agent_harness_anti_oscillation_guard(self):
        """Verify identical consecutive tool calls are suppressed with warning notice."""
        # Turn 1: tool call get_smc_zones
        resp1 = MockResponse(
            content=[
                MockBlock(type="tool_use", id="call_1", name="get_smc_zones", input={"symbol": "EURUSD", "timeframe": "M15"})
            ],
            stop_reason="tool_use",
            input_tokens=100,
            output_tokens=30,
        )
        # Turn 2: exact duplicate tool call get_smc_zones
        resp2 = MockResponse(
            content=[
                MockBlock(type="tool_use", id="call_2", name="get_smc_zones", input={"symbol": "EURUSD", "timeframe": "M15"})
            ],
            stop_reason="tool_use",
            input_tokens=120,
            output_tokens=30,
        )
        # Turn 3: model concludes after receiving suppression notice
        resp3 = MockResponse(
            content=[
                MockBlock(type="text", text="Decision concluded after suppression.")
            ],
            stop_reason="end_turn",
            input_tokens=150,
            output_tokens=40,
        )

        client = DummyLLMClient([resp1, resp2, resp3])
        harness = AgentHarness(client, settings={}, max_tool_turns=5)

        mock_executor = AsyncMock()
        mock_executor.execute = AsyncMock(return_value={"zones": [{"high": 1.0900, "low": 1.0880}]})

        result = await harness.run_agent(
            session=None,
            system_prompt="Trading system",
            user_message="Analyze structure",
            tools=[{"name": "get_smc_zones"}],
            stage_name="test_stage",
            tool_executor=mock_executor,
        )

        assert result["success"] is True
        # The mock executor should ONLY have been invoked ONCE (the second one was suppressed)
        assert mock_executor.execute.await_count == 1
        # Check messages to confirm suppressed notice was injected
        context_msgs = result["context_messages"]
        last_tool_res_msg = context_msgs[-2]  # assistant msg is -1, tool result is -2
        assert last_tool_res_msg["role"] == "user"
        content_json = json.loads(last_tool_res_msg["content"][0]["content"])
        assert content_json.get("status") == "already_executed"
        assert "identical parameters was already executed" in content_json.get("notice", "")

    @pytest.mark.asyncio
    async def test_agent_harness_mandatory_tool_nudging(self):
        """Verify harness nudges model if it tries to conclude per_asset stage without submit_asset_analysis."""
        # Turn 1: Model tries to conclude with plain text
        resp1 = MockResponse(
            content=[MockBlock(type="text", text="I think XAUUSD will go up.")],
            stop_reason="end_turn",
            input_tokens=100,
            output_tokens=20,
        )
        # Turn 2: After being nudged, calls submit_asset_analysis
        resp2 = MockResponse(
            content=[
                MockBlock(type="tool_use", id="submit_call", name="submit_asset_analysis", input={"symbol": "XAUUSD", "decision": "buy"})
            ],
            stop_reason="tool_use",
            input_tokens=150,
            output_tokens=30,
        )
        # Turn 3: Final confirmation
        resp3 = MockResponse(
            content=[MockBlock(type="text", text="Submitted successfully.")],
            stop_reason="end_turn",
            input_tokens=180,
            output_tokens=10,
        )

        client = DummyLLMClient([resp1, resp2, resp3])
        harness = AgentHarness(client, settings={}, max_tool_turns=5)

        mock_executor = AsyncMock()
        mock_executor.execute = AsyncMock(return_value={"status": "accepted"})

        result = await harness.run_agent(
            session=None,
            system_prompt="System",
            user_message="Analyze XAUUSD",
            tools=[{"name": "submit_asset_analysis"}],
            stage_name="per_asset_XAUUSD",
            tool_executor=mock_executor,
        )

        assert result["success"] is True
        assert result["turns"] == 3
        # Check that nudge message was sent in turn 1
        nudge_msg = result["context_messages"][2]
        assert nudge_msg["role"] == "user"
        assert "CRITICAL MANDATORY INSTRUCTION" in nudge_msg["content"]
        assert "submit_asset_analysis" in nudge_msg["content"]

    @pytest.mark.asyncio
    async def test_agent_harness_state_preservation_truncation(self):
        """Verify context truncation preserves state summary of critical facts."""
        harness = AgentHarness(None, settings={}, max_context_chars=100)

        # Create message history with lots of tool results
        messages = [
            {"role": "user", "content": "Initial prompt " * 10},
            {"role": "assistant", "content": [MockBlock(type="tool_use", id="c1", name="t1", input={})]},
            {"role": "user", "content": [
                {"type": "tool_result", "content": json.dumps({"atr_14": 18.25, "trend_5d": "bullish"})}
            ]},
            {"role": "assistant", "content": [MockBlock(type="tool_use", id="c2", name="t2", input={})]},
            {"role": "user", "content": [
                {"type": "tool_result", "content": json.dumps({"risk_sentiment": "risk_on", "latest": {"close": 2040.5, "date": "2026-09-05"}})}
            ]},
            {"role": "assistant", "content": [MockBlock(type="tool_use", id="c3", name="t3", input={})]},
            {"role": "user", "content": [
                {"type": "tool_result", "content": "some intermediate data " * 20}
            ]},
            {"role": "assistant", "content": [MockBlock(type="text", text="Recent turn 1")]},
            {"role": "user", "content": "Recent turn 2"},
            {"role": "assistant", "content": [MockBlock(type="text", text="Recent turn 3")]},
        ]

        trimmed = harness._apply_truncation_guardrail(messages, system_prompt="Sys", stage_name="test_stage")
        assert len(trimmed) < len(messages)
        # Check that state preservation block was inserted
        summary_msg = trimmed[1]
        assert summary_msg["role"] == "user"
        assert "CONTEXT WINDOW STATE SUMMARY" in summary_msg["content"]
        assert "ATR_14=18.25" in summary_msg["content"]
        assert "Trend_5d=bullish" in summary_msg["content"]
        assert "Risk_Sentiment=risk_on" in summary_msg["content"]
        assert "Latest_Close=2040.5 on 2026-09-05" in summary_msg["content"]

    @pytest.mark.asyncio
    async def test_base_llm_client_default_agent_harness(self):
        """Verify BaseLLMClient.run_agent automatically delegates to AgentHarness."""
        resp = MockResponse(
            content=[MockBlock(type="text", text="Direct harness delegation works!")],
            stop_reason="end_turn",
            input_tokens=50,
            output_tokens=15,
        )
        client = DummyLLMClient([resp])
        # Call BaseLLMClient default implementation
        res = await client.run_agent(
            session=None,
            system_prompt="Test",
            user_message="Hello",
            tools=[],
            stage_name="general",
        )
        assert res["success"] is True
        assert res["final_text"] == "Direct harness delegation works!"


# ==============================================================================
# 3. Schedulers & Runtime Integration Tests
# ==============================================================================

class TestSchedulerEventBusIntegration:
    @pytest.mark.asyncio
    async def test_flash_crash_detector_on_tick(self):
        """Verify FlashCrashDetector processes TickPriceEvent and detects extreme moves."""
        settings = {
            "trading": {
                "risk": {
                    "flash_crash": {
                        "enabled": True,
                        "default_atr_multiplier": 3.0,
                        "default_min_pct_move": 1.0,
                        "cooldown_minutes": 15,
                    }
                }
            }
        }
        detector = FlashCrashDetector(settings)
        now = datetime.now(timezone.utc)
        # EURUSD threshold in DEFAULT_SYMBOL_RULES is 1.2%
        tick1 = TickPriceEvent(symbol="EURUSD", bid=1.0900, ask=1.0902, last=1.0901, timestamp=now)
        await detector.on_tick(tick1)

        # Extreme 2.7% drop on tick 2
        tick2 = TickPriceEvent(symbol="EURUSD", bid=1.0600, ask=1.0602, last=1.0601, timestamp=now + timedelta(seconds=10))

        detector.check = AsyncMock(return_value=[{"symbol": "EURUSD", "range_move": 0.0300}])

        bus = reset_event_bus()
        cb_received = []

        async def cb_handler(evt: CircuitBreakerEvent):
            cb_received.append(evt)

        bus.subscribe(CircuitBreakerEvent, cb_handler)

        mock_session = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session

        with patch("database.db.get_session", return_value=mock_ctx):
            await detector.on_tick(tick2)

        detector.check.assert_awaited_once()
        assert len(cb_received) == 1
        assert cb_received[0].component == "FlashCrashDetector"
        assert "EURUSD" in cb_received[0].reason

    @pytest.mark.asyncio
    async def test_trailing_stop_manager_on_tick(self):
        """Verify TrailingStopManager processes TickPriceEvent for open position."""
        settings = {
            "trading": {
                "risk": {
                    "trailing_stop": {"enabled": True},
                    "breakeven_atr_mult": 1.0,
                    "trailing_atr_mult": 1.5,
                }
            }
        }
        manager = TrailingStopManager(settings)

        # Mock position and session
        mock_pos = MagicMock()
        mock_pos.symbol = "XAUUSD"
        mock_pos.status = "open"
        mock_pos.pair_group_id = None
        mock_pos.direction = "BUY"
        mock_pos.mt5_ticket = 12345

        manager._check_position = AsyncMock(return_value={"adjusted": True, "new_sl": 2010.0})

        mock_session = AsyncMock()
        mock_session.execute.return_value = MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[mock_pos])))
        )
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session

        with patch("scheduler.trailing_stop_manager.get_session", return_value=mock_ctx), \
             patch("database.db.get_session", return_value=mock_ctx):
            tick = TickPriceEvent(symbol="XAUUSD", bid=2020.0, ask=2020.5, last=2020.25)
            await manager.on_tick(tick)

            manager._check_position.assert_awaited_once()
            # Ensure tick price was passed as override
            args, kwargs = manager._check_position.call_args
            assert kwargs.get("current_price_override") == 2020.25

    @pytest.mark.asyncio
    async def test_position_guardian_on_tick_emergency_kill(self):
        """Verify PositionGuardian triggers liquidation if kill_switch is active when tick arrives."""
        settings = {"trading": {"position_guardian": {"enabled": True}}}
        mock_exec = AsyncMock()
        guardian = PositionGuardian(settings, execution_service=mock_exec)

        mock_cfg = MagicMock()
        mock_cfg.value = "true"
        mock_session = AsyncMock()
        mock_session.execute.return_value = MagicMock(
            scalar_one_or_none=MagicMock(return_value=mock_cfg)
        )
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session

        with patch("scheduler.position_guardian.get_session", return_value=mock_ctx), \
             patch("database.db.get_session", return_value=mock_ctx):
            tick = TickPriceEvent(symbol="EURUSD", bid=1.0850, ask=1.0852)
            await guardian.on_tick(tick)

            mock_exec.kill_switch.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_position_guardian_on_tick_emergency_kill_debounced(self):
        """Verify PositionGuardian debounces kill_switch across multiple ticks and re-arms on reset."""
        settings = {"trading": {"position_guardian": {"enabled": True}}}
        mock_exec = AsyncMock()
        guardian = PositionGuardian(settings, execution_service=mock_exec)

        mock_cfg = MagicMock()
        mock_cfg.value = "true"
        mock_session = AsyncMock()
        mock_session.execute.return_value = MagicMock(
            scalar_one_or_none=MagicMock(return_value=mock_cfg)
        )
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session

        with patch("scheduler.position_guardian.get_session", return_value=mock_ctx), \
             patch("database.db.get_session", return_value=mock_ctx):
            # 1. Multiple ticks with kill_switch=true
            tick1 = TickPriceEvent(symbol="EURUSD", bid=1.0850, ask=1.0852)
            tick2 = TickPriceEvent(symbol="GBPUSD", bid=1.2850, ask=1.2852)
            tick3 = TickPriceEvent(symbol="XAUUSD", bid=2000.0, ask=2000.5)

            await guardian.on_tick(tick1)
            await guardian.on_tick(tick2)
            await guardian.on_tick(tick3)

            # Assert only 1 kill_switch call occurred
            assert mock_exec.kill_switch.call_count == 1

            # 2. System resumed: kill_switch=false
            mock_cfg.value = "false"
            tick4 = TickPriceEvent(symbol="EURUSD", bid=1.0860, ask=1.0862)
            guardian._last_tick_check["EURUSD"] = 0  # bypass 1s throttle
            await guardian.on_tick(tick4)
            assert mock_exec.kill_switch.call_count == 1
            assert guardian._kill_switch_triggered is False

            # 3. New emergency: kill_switch=true again
            mock_cfg.value = "true"
            tick5 = TickPriceEvent(symbol="EURUSD", bid=1.0870, ask=1.0872)
            guardian._last_tick_check["EURUSD"] = 0
            await guardian.on_tick(tick5)
            assert mock_exec.kill_switch.call_count == 2
            assert guardian._kill_switch_triggered is True

    @pytest.mark.asyncio
    async def test_position_guardian_check_and_protect_debounced(self):
        """Verify check_and_protect only triggers kill_switch once until reset."""
        settings = {"trading": {"position_guardian": {"enabled": True}}}
        mock_exec = AsyncMock()
        guardian = PositionGuardian(settings, execution_service=mock_exec)

        mock_cfg = MagicMock()
        mock_cfg.value = "true"
        mock_session = AsyncMock()
        mock_session.execute.return_value = MagicMock(
            scalar_one_or_none=MagicMock(return_value=mock_cfg)
        )
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session

        with patch("scheduler.position_guardian.get_session", return_value=mock_ctx), \
             patch("database.db.get_session", return_value=mock_ctx):
            res1 = await guardian.check_and_protect()
            assert res1.get("kill_switch_active") is True
            assert mock_exec.kill_switch.call_count == 1

            res2 = await guardian.check_and_protect()
            assert res2.get("kill_switch_active") is True
            assert mock_exec.kill_switch.call_count == 1  # No duplicate execution

    @pytest.mark.asyncio
    async def test_market_data_scheduler_publishes_tick_on_sync(self):
        """Verify MarketDataScheduler publishes TickPriceEvent during market data sync."""
        settings = {
            "trading": {
                "asset_universe": ["XAUUSD"],
                "mt5": {"timeframes": ["H1"]},
            }
        }
        mock_mt5 = AsyncMock()
        mock_mt5.ensure_connected.return_value = True
        mock_mt5.fetch_and_save_all.return_value = {"XAUUSD": 100}
        mock_mt5.get_current_price.return_value = {
            "symbol": "XAUUSD",
            "bid": 2050.0,
            "ask": 2050.5,
            "last": 2050.25,
        }

        bus = reset_event_bus()
        ticks_received = []

        async def tick_collector(evt: TickPriceEvent):
            ticks_received.append(evt)

        bus.subscribe(TickPriceEvent, tick_collector)

        scheduler = MarketDataScheduler(settings, mt5_client=mock_mt5, event_bus=bus)

        mock_calc = MagicMock()
        mock_calc.compute_all_symbols = AsyncMock(return_value={})
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_all = AsyncMock(return_value={})

        mock_session = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session

        with patch("database.db.get_session", return_value=mock_ctx), \
             patch("scheduler.market_data_scheduler.is_forex_market_closed", return_value=False), \
             patch("scheduler.market_data_scheduler.TechnicalIndicatorCalculator", return_value=mock_calc), \
             patch("scheduler.market_data_scheduler.MarketStructureAnalyzer", return_value=mock_analyzer):
            
            res = await scheduler.sync_now()
            assert res["status"] == "success"
            assert len(ticks_received) == 1
            assert ticks_received[0].symbol == "XAUUSD"
            assert ticks_received[0].bid == 2050.0
            assert ticks_received[0].ask == 2050.5

    @pytest.mark.asyncio
    async def test_main_trading_agent_event_bus_wiring(self):
        """Verify TradingAgent sets up EventBus subscriptions and broadcasts live ticks."""
        settings = {
            "trading": {
                "risk": {"flash_crash": {"enabled": True}},
                "position_guardian": {"enabled": True},
                "risk": {"trailing_stop": {"enabled": True}},
                "asset_universe": ["XAUUSD"],
            },
            "execution": {"mt5_common_dir": ""},
        }

        with patch("execution.mt5_client.MT5Client"), \
             patch("execution.execution_service.ExecutionService"), \
             patch("analysis.stages.fundamental_stage.FundamentalStage"), \
             patch("analysis.stages.per_asset_stage.PerAssetStage"), \
             patch("scheduler.graph_cycle_scheduler.GraphCycleScheduler"), \
             patch("telegram_bot.bot.TelegramBot"):

            agent = TradingAgent(settings, dry_run=True)
            agent._init_components()

            assert agent.event_bus is not None

            # Check that on_tick handlers are registered
            subs = agent.event_bus.get_subscribers(TickPriceEvent)
            assert len(subs) >= 3

            handlers = [s.handler for s in subs]
            assert agent.flash_crash_detector.on_tick in handlers
            assert agent.position_guardian.on_tick in handlers
            assert agent.trailing_stop_manager.on_tick in handlers

            # Test publish_tick method
            test_ticks = []

            async def capture(evt: TickPriceEvent):
                test_ticks.append(evt)

            agent.event_bus.subscribe(TickPriceEvent, capture)

            await agent.publish_tick(symbol="XAUUSD", bid=2030.0, ask=2030.6, last=2030.3)

            assert len(test_ticks) == 1
            assert test_ticks[0].symbol == "XAUUSD"
            assert test_ticks[0].bid == 2030.0
            assert test_ticks[0].ask == 2030.6
            assert test_ticks[0].spread == 0.6


# ==============================================================================
# 4. Deep Edge-Case & Robustness Tests
# ==============================================================================

class OpenAIChatCompletionMock:
    """Mock simulating OpenAI / OpenRouter / DeepSeek ChatCompletion response structure."""
    def __init__(self, content=None, tool_calls=None, reasoning_content=None, finish_reason="stop", prompt_tokens=100, completion_tokens=25):
        class FunctionCall:
            def __init__(self, name, arguments):
                self.name = name
                self.arguments = arguments if isinstance(arguments, str) else json.dumps(arguments)

        class ToolCall:
            def __init__(self, id, fn_name, fn_args):
                self.id = id
                self.function = FunctionCall(fn_name, fn_args)

        class Message:
            def __init__(self, content, tool_calls, reasoning):
                self.content = content
                self.tool_calls = tool_calls
                self.reasoning_content = reasoning

        class Choice:
            def __init__(self, msg, finish_reason):
                self.message = msg
                self.finish_reason = finish_reason

        class Usage:
            def __init__(self, p_tok, c_tok):
                self.prompt_tokens = p_tok
                self.completion_tokens = c_tok
                self.input_tokens = p_tok
                self.output_tokens = c_tok

        t_calls = None
        if tool_calls:
            t_calls = [ToolCall(tc.get("id", f"call_{i}"), tc.get("name"), tc.get("args", {})) for i, tc in enumerate(tool_calls)]

        msg = Message(content=content, tool_calls=t_calls, reasoning=reasoning_content)
        self.choices = [Choice(msg, finish_reason)]
        self.usage = Usage(prompt_tokens, completion_tokens)


class TestPhase2EdgeCases:
    @pytest.mark.asyncio
    async def test_agent_harness_openai_chat_completion_compatibility(self):
        """Verify AgentHarness natively unpacks OpenAI ChatCompletion with reasoning_content and tool_calls."""
        turn1_resp = OpenAIChatCompletionMock(
            content="Checking technical indicators and order structure...",
            reasoning_content="The user wants analysis of EURUSD. First step is to check SMC zones.",
            tool_calls=[{"id": "call_abc123", "name": "get_smc_zones", "args": {"symbol": "EURUSD", "timeframe": "M15"}}],
            finish_reason="tool_calls",
        )
        turn2_resp = OpenAIChatCompletionMock(
            content="Analysis complete.",
            tool_calls=[{"id": "call_sub999", "name": "submit_asset_analysis", "args": {"symbol": "EURUSD", "decision": "wait"}}],
            finish_reason="tool_calls",
        )
        turn3_resp = OpenAIChatCompletionMock(
            content="Submitted.",
            tool_calls=None,
            finish_reason="stop",
        )

        mock_client = MagicMock()
        mock_client.model = "gpt-4o"
        mock_client.run_tool_agent = AsyncMock(side_effect=[turn1_resp, turn2_resp, turn3_resp])

        mock_executor = MagicMock()
        mock_executor.execute = AsyncMock(side_effect=[
            {"zones": [{"price": 1.0850}]},
            {"status": "submitted", "decision": "wait"},
        ])

        harness = AgentHarness(mock_client, settings={}, max_tool_turns=5)
        res = await harness.run_agent(
            session=None,
            system_prompt="You are a trading agent.",
            user_message="Analyze EURUSD",
            tools=[{"name": "get_smc_zones"}, {"name": "submit_asset_analysis"}],
            stage_name="per_asset_EURUSD",
            tool_executor=mock_executor,
        )

        assert res["success"] is True
        assert res["tool_calls_made"] == 2
        assert res["turns"] == 3
        # Check that reasoning_content was preserved in the assistant message
        hist = res["context_messages"]
        ast_msgs = [m for m in hist if m.get("role") == "assistant"]
        assert len(ast_msgs) >= 1
        assert ast_msgs[0].get("reasoning_content") == "The user wants analysis of EURUSD. First step is to check SMC zones."

    @pytest.mark.asyncio
    async def test_agent_harness_billing_error_classification(self):
        """Verify AgentHarness flags is_billing_error=True on credit balance exhaustion."""
        mock_client = MagicMock()
        mock_client.model = "claude-3-5-sonnet"
        mock_client.run_tool_agent = AsyncMock(side_effect=Exception("Your credit balance is too low to access the Claude API"))

        harness = AgentHarness(mock_client, settings={})
        res = await harness.run_agent(
            session=None,
            system_prompt="Test",
            user_message="Analyze",
            tools=[],
            stage_name="stage1_fundamental",
        )

        assert res["success"] is False
        assert res["is_billing_error"] is True

    @pytest.mark.asyncio
    async def test_agent_harness_transient_retry(self):
        """Verify AgentHarness retries transient 429 rate limit before succeeding."""
        success_resp = MockResponse(
            content=[MockBlock(type="text", text="Success after transient retry")],
            stop_reason="end_turn",
            input_tokens=10,
            output_tokens=10,
        )

        class RateLimit429(Exception):
            status_code = 429

        mock_client = MagicMock()
        mock_client.model = "gemini-2.5-flash"
        mock_client.run_tool_agent = AsyncMock(side_effect=[RateLimit429("Rate limit exceeded"), success_resp])

        harness = AgentHarness(mock_client, settings={})
        res = await harness.run_agent(
            session=None,
            system_prompt="Test",
            user_message="Hello",
            tools=[],
            stage_name="general",
        )

        assert res["success"] is True
        assert res["final_text"] == "Success after transient retry"
        assert mock_client.run_tool_agent.await_count == 2

    @pytest.mark.asyncio
    async def test_event_bus_buffered_queue_task_done_on_drop(self):
        """Verify dropping oldest items on a full queue calls task_done, allowing queue.join() to resolve."""
        bus = EventBus()
        # Create tiny queue of size 2
        queue = bus.get_or_create_queue("tiny", maxsize=2)

        # Publish 4 items (2 will be dropped)
        for i in range(4):
            evt = TickPriceEvent(symbol="EURUSD", bid=1.0800 + i * 0.001)
            await bus.publish_buffered(evt, "tiny")

        assert queue.qsize() == 2

        # Process the 2 remaining items
        item1 = queue.get_nowait()
        queue.task_done()
        item2 = queue.get_nowait()
        queue.task_done()

        # queue.join() MUST complete without timeout because dropped items had task_done() called
        await asyncio.wait_for(queue.join(), timeout=0.5)

    @pytest.mark.asyncio
    async def test_event_bus_worker_restart_after_stop(self):
        """Verify start_queue_worker can be restarted after stop_workers without being permanently disabled."""
        bus = EventBus()
        received = []

        async def handler(evt: AppEvent):
            received.append(evt)

        bus.subscribe(TickPriceEvent, handler)

        # Start and immediately stop
        bus.start_queue_worker("stream")
        bus.stop_workers()

        # Restart worker
        bus.start_queue_worker("stream")
        evt = TickPriceEvent(symbol="BTCUSD", bid=65000.0)
        await bus.publish_buffered(evt, "stream")

        await asyncio.sleep(0.05)
        bus.stop_workers()

        assert len(received) == 1
        assert received[0].symbol == "BTCUSD"

    @pytest.mark.asyncio
    async def test_event_bus_get_subscribers_deduplication(self):
        """Verify registering the exact same handler for base and derived types only runs once per event."""
        bus = EventBus()
        calls = []

        async def universal_handler(evt: AppEvent):
            calls.append(evt)

        # Subscribe same handler to AppEvent and TickPriceEvent
        bus.subscribe(AppEvent, universal_handler, priority=10)
        bus.subscribe(TickPriceEvent, universal_handler, priority=20)

        subs = bus.get_subscribers(TickPriceEvent)
        assert len(subs) == 1  # Deduplicated to highest priority (20)
        assert subs[0].priority == 20

        await bus.publish(TickPriceEvent(symbol="XAUUSD", bid=2000.0))
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_event_bus_publish_threadsafe(self):
        """Verify publish_threadsafe dispatches coroutine from background thread to asyncio loop."""
        bus = EventBus()
        received = []

        async def handler(evt: TickPriceEvent):
            received.append(evt)

        bus.subscribe(TickPriceEvent, handler)
        loop = asyncio.get_running_loop()

        def background_thread_work():
            evt = TickPriceEvent(symbol="USDJPY", bid=155.20)
            fut = bus.publish_threadsafe(evt, loop=loop)
            fut.result(timeout=2.0)

        await asyncio.to_thread(background_thread_work)
        assert len(received) == 1
        assert received[0].symbol == "USDJPY"

    @pytest.mark.asyncio
    async def test_flash_crash_detector_direct_on_tick_without_db_candles(self):
        """Verify FlashCrashDetector protects open positions on live tick even when DB candles are empty."""
        settings = {
            "trading": {
                "risk": {
                    "flash_crash": {
                        "enabled": True,
                        "default_min_pct_move": 1.0,
                        "cooldown_minutes": 15,
                    }
                }
            }
        }
        detector = FlashCrashDetector(settings)
        # Mock check to return empty (simulating empty PriceOHLCV table during live crash)
        detector.check = AsyncMock(return_value=[])
        detector._protect_open_positions = AsyncMock()

        bus = reset_event_bus()
        cb_events = []

        async def on_cb(evt: CircuitBreakerEvent):
            cb_events.append(evt)

        bus.subscribe(CircuitBreakerEvent, on_cb)

        now = datetime.now(timezone.utc)
        tick1 = TickPriceEvent(symbol="EURUSD", bid=1.1000, ask=1.1002, last=1.1001, timestamp=now)
        await detector.on_tick(tick1)

        # 3% crash on live tick
        tick2 = TickPriceEvent(symbol="EURUSD", bid=1.0670, ask=1.0672, last=1.0671, timestamp=now + timedelta(seconds=5))

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))

        with patch("database.db.get_session", return_value=mock_ctx):
            await detector.on_tick(tick2)

        # Protection MUST have run directly
        detector._protect_open_positions.assert_awaited_once()
        assert detector.is_symbol_blocked("EURUSD") is True
        assert len(cb_events) == 1
        assert cb_events[0].component == "FlashCrashDetector"

    @pytest.mark.asyncio
    async def test_trailing_stop_manager_on_tick_throttling(self):
        """Verify TrailingStopManager throttles high-frequency ticks to avoid DB thrashing."""
        settings = {"trading": {"risk": {"trailing_stop": {"enabled": True}}}}
        manager = TrailingStopManager(settings)
        manager._check_position = AsyncMock(return_value=None)

        now = datetime.now(timezone.utc)
        tick1 = TickPriceEvent(symbol="EURUSD", bid=1.0800, timestamp=now)
        # Tick 2 arrives 0.2s later (within 1.0s throttle window)
        tick2 = TickPriceEvent(symbol="EURUSD", bid=1.0801, timestamp=now + timedelta(milliseconds=200))

        mock_session = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_session.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))))

        with patch("database.db.get_session", return_value=mock_ctx):
            await manager.on_tick(tick1)
            await manager.on_tick(tick2)

        # mock_session should be accessed only ONCE because tick2 was throttled
        assert mock_session.execute.await_count == 1

