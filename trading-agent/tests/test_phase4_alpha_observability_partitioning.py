"""
Unit tests for Phase 4: Microstructure Alpha, Observability Live Feed & DB Partitioning.
"""

import asyncio
from datetime import datetime, timezone
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from analysis.calculators.timesfm_alpha import TimesFMAlphaCalculator
from database.cleanup import drop_expired_partitions
from logging_observability.dashboard.api import app, broadcast_live_event, _active_websockets
from fastapi.testclient import TestClient


# ==============================================================================
# 1. TimesFM Quantile Asymmetry Skew Alpha Tests
# ==============================================================================

class TestTimesFMAlphaCalculator:
    def test_skew_ratio_bullish_expansion(self):
        """Upper tail expansion (Q90 - Q50) significantly exceeds lower tail (Q50 - Q10)."""
        quantiles = {
            "q10": [100.0, 100.0, 100.0],
            "q50": [102.0, 102.0, 102.0],  # lower expansion = 2.0
            "q90": [108.0, 108.0, 108.0],  # upper expansion = 6.0 -> skew = 3.0
        }
        res = TimesFMAlphaCalculator.calculate_skew_from_quantiles(quantiles, current_price=101.0)
        assert res["valid"] is True
        assert res["skew_ratio"] == 3.0
        assert res["bias"] == "BULLISH_EXPANSION"
        assert res["confidence"] > 0.50
        assert res["upper_expansion"] == 6.0
        assert res["lower_expansion"] == 2.0
        assert round(res["drift_pct"], 2) == round(((102.0 - 101.0) / 101.0) * 100.0, 2)

    def test_skew_ratio_bearish_expansion(self):
        """Lower tail expansion (Q50 - Q10) significantly exceeds upper tail (Q90 - Q50)."""
        quantiles = {
            "q10": 90.0,
            "q50": 98.0,  # lower expansion = 8.0
            "q90": 100.0, # upper expansion = 2.0 -> skew = 2.0 / 8.0 = 0.25
        }
        res = TimesFMAlphaCalculator.calculate_skew_from_quantiles(quantiles, current_price=99.0)
        assert res["valid"] is True
        assert res["skew_ratio"] == 0.25
        assert res["bias"] == "BEARISH_EXPANSION"
        assert res["confidence"] > 0.50

    def test_skew_ratio_symmetric_neutral(self):
        """Evenly distributed tails yield symmetric neutral bias."""
        quantiles = {
            "q10": 100.0,
            "q50": 105.0,  # lower = 5.0
            "q90": 110.0,  # upper = 5.0 -> skew = 1.0
        }
        res = TimesFMAlphaCalculator.calculate_skew_from_quantiles(quantiles, current_price=105.0)
        assert res["valid"] is True
        assert res["skew_ratio"] == 1.0
        assert res["bias"] == "SYMMETRIC_NEUTRAL"
        assert res["confidence"] == 0.50

    def test_sizing_multipliers(self):
        """Test directional sizing multiplier against tail skew."""
        bull_res = {"valid": True, "bias": "BULLISH_EXPANSION"}
        bear_res = {"valid": True, "bias": "BEARISH_EXPANSION"}
        neut_res = {"valid": True, "bias": "SYMMETRIC_NEUTRAL"}

        # Buy direction
        assert TimesFMAlphaCalculator.get_sizing_multiplier(bull_res, "BUY") == 1.15
        assert TimesFMAlphaCalculator.get_sizing_multiplier(bear_res, "BUY") == 0.80
        assert TimesFMAlphaCalculator.get_sizing_multiplier(neut_res, "BUY") == 1.0

        # Sell direction
        assert TimesFMAlphaCalculator.get_sizing_multiplier(bear_res, "SELL") == 1.15
        assert TimesFMAlphaCalculator.get_sizing_multiplier(bull_res, "SELL") == 0.80
        assert TimesFMAlphaCalculator.get_sizing_multiplier(neut_res, "SELL") == 1.0

        # Invalid or empty
        assert TimesFMAlphaCalculator.get_sizing_multiplier({}, "BUY") == 1.0

    def test_format_for_prompt(self):
        """Formatting produces clean prompt block with relevant statistics."""
        sample_res = {
            "valid": True,
            "skew_ratio": 1.75,
            "bias": "BULLISH_EXPANSION",
            "confidence": 0.72,
            "q10": 2340.5,
            "q50": 2355.0,
            "q90": 2380.0,
            "drift_pct": 0.65,
        }
        formatted = TimesFMAlphaCalculator.format_for_prompt(sample_res)
        assert "TIMESFM 3.0 PROBABILISTIC SKEW ALPHA" in formatted
        assert "1.75" in formatted
        assert "BULLISH_EXPANSION" in formatted
        assert "2355.0" in formatted

    def test_empty_or_invalid_quantiles_fail_safe(self):
        """Non-monotonic or missing quantiles return fail-safe dict without raising."""
        assert TimesFMAlphaCalculator.calculate_skew_from_quantiles({})["valid"] is False
        assert TimesFMAlphaCalculator.calculate_skew_from_quantiles({"q10": 100})["valid"] is False
        # Inverted quantiles (Q10 > Q50)
        assert TimesFMAlphaCalculator.calculate_skew_from_quantiles({"q10": 110, "q50": 100, "q90": 120})["valid"] is False


# ==============================================================================
# 2. Dashboard WebSocket Live Feed Tests
# ==============================================================================

class TestDashboardWebSocketLiveFeed:
    def test_websocket_connect_and_ping_pong(self):
        """Verify client connects to /ws/live-feed, receives greeting, and answers ping."""
        client = TestClient(app)
        with client.websocket_connect("/ws/live-feed") as websocket:
            init_msg = websocket.receive_json()
            assert init_msg["type"] == "connection_established"
            assert init_msg["status"] == "connected"

            # Ping-pong test
            websocket.send_text("ping")
            pong = websocket.receive_text()
            assert pong == "pong"

    @pytest.mark.asyncio
    async def test_broadcast_live_event_pushes_to_clients(self):
        """Verify broadcast_live_event pushes JSON to active WebSocket connections."""
        mock_ws = AsyncMock()
        mock_ws.send_json = AsyncMock()
        _active_websockets.add(mock_ws)

        try:
            await broadcast_live_event("test_tick", {"symbol": "EURUSD", "bid": 1.0850})
            mock_ws.send_json.assert_called_once()
            called_args = mock_ws.send_json.call_args[0][0]
            assert called_args["type"] == "test_tick"
            assert called_args["payload"]["symbol"] == "EURUSD"
        finally:
            _active_websockets.discard(mock_ws)


# ==============================================================================
# 3. Database Table Partition Pruning Tests
# ==============================================================================

class TestDatabasePartitionPruning:
    @pytest.mark.asyncio
    async def test_drop_expired_partitions_sqlite_noop(self):
        """On non-PostgreSQL (SQLite), drop_expired_partitions safely returns 0."""
        mock_session = AsyncMock()
        mock_bind = MagicMock()
        mock_bind.dialect.name = "sqlite"
        mock_session.bind = mock_bind

        res = await drop_expired_partitions(mock_session, older_than_days=180)
        assert res == 0

    @pytest.mark.asyncio
    async def test_drop_expired_partitions_postgresql_drops_old_tables(self):
        """On PostgreSQL, drops partitions matching expired year/month."""
        mock_session = AsyncMock()
        mock_bind = MagicMock()
        mock_bind.dialect.name = "postgresql"
        mock_session.bind = mock_bind

        # Return 2 partitions: 1 very old (2024-01), 1 current (2026-09)
        mock_session.execute = AsyncMock(return_value=MagicMock(
            fetchall=lambda: [("price_ohlcv_y2024_m01",), ("price_ohlcv_y2026_m09",)]
        ))

        dropped = await drop_expired_partitions(mock_session, older_than_days=180)
        assert dropped == 1
        # Verify DROP TABLE was executed for the 2024 partition
        calls = [str(c[0][0]) for c in mock_session.execute.call_args_list if len(c[0]) > 0]
        assert any("DROP TABLE IF EXISTS price_ohlcv_y2024_m01" in s for s in calls)


# ==============================================================================
# 4. Telegram Deep Research Progress Streaming Tests
# ==============================================================================

class TestTelegramDeepResearchProgress:
    @pytest.mark.asyncio
    async def test_deep_research_calls_status_callback(self):
        """Verify _run_tier_deep_research invokes status_callback across its workflow."""
        from telegram_bot.chat_agent import ChatAgent

        settings = {
            "telegram": {"admin_chat_id": 123},
            "analysis": {},
            "llm": {"task_roles": {}}
        }
        agent = ChatAgent(settings, user_id=123)

        mock_client = AsyncMock()
        mock_client.run_chat_loop = AsyncMock(return_value={"reply": "Report content", "tool_calls_made": 1})
        agent._client_research = mock_client
        agent._client_deep = mock_client

        progress_calls = []
        async def mock_callback(msg: str):
            progress_calls.append(msg)

        res = await agent._run_tier_deep_research(
            system_prompt="Test sys",
            history=[],
            message="Analisis Gold",
            tool_executor=MagicMock(),
            status_callback=mock_callback,
        )

        assert res is not None
        assert len(progress_calls) >= 4  # Initial + 3 workers + synthesis
        assert any("Menjalankan riset paralel" in p for p in progress_calls)
        assert any("Mensintesis Ringkasan Eksekutif" in p for p in progress_calls)


# ==============================================================================
# 5. TimesFM Alpha & Observability End-to-End Wiring Tests
# ==============================================================================

class TestTimesFMAlphaIntegration:

    @pytest.mark.asyncio
    async def test_position_sizer_applies_timesfm_skew_multiplier(self):
        """Verify PositionSizer fetches TimesFM forecast and applies directional skew multiplier."""
        from risk.position_sizing import PositionSizer
        from unittest.mock import patch, MagicMock, AsyncMock

        sizer = PositionSizer({"trading": {"risk": {"risk_percent_per_trade": 1.0}}})
        mock_session = AsyncMock()

        # Mock instrument spec
        mock_spec = MagicMock()
        mock_spec.digits = 5
        mock_spec.stops_level_pips = 0.0
        mock_spec.pip_size = 0.0001
        mock_spec.pip_value_per_lot = 10.0
        mock_spec.min_lot = 0.01
        mock_spec.max_lot = 100.0
        mock_spec.lot_step = 0.01
        mock_spec.contract_size = 100000.0

        mock_regime_mult = 1.0

        # Bullish skew forecast: upper expansion is much larger
        mock_fc = {
            "volatility_expansion_ratio": 1.1,
            "quantiles": {
                "q10": 1.0800,
                "q50": 1.0820, # lower = 0.0020
                "q90": 1.0880, # upper = 0.0060 -> skew = 3.0 (BULLISH_EXPANSION)
            }
        }

        with patch.object(sizer, "_get_instrument_spec_dynamic", new=AsyncMock(return_value=mock_spec)), \
             patch.object(sizer, "_get_regime_size_multiplier", new=AsyncMock(return_value=1.0)), \
             patch("indicators.timesfm_engine.TimesFMEngine.get_latest_forecast", new=AsyncMock(return_value=mock_fc)):

            # BUY order should receive 1.15x multiplier
            res_buy = await sizer.calculate_with_session(
                session=mock_session,
                symbol="EURUSD",
                direction="BUY",
                entry_price=1.0820,
                stop_loss=1.0800,
                take_profit=1.0900,
                account_equity=10000.0,
                risk_percent=1.0,
                vix_level=12.0,
            )
            assert res_buy.is_valid is True
            # Base risk 1.0% ($100) -> with 1.15x = $115
            # SL distance = 20 pips ($200/lot) -> 115 / 200 = 0.57 lots
            assert res_buy.recommended_lots == 0.57 or res_buy.recommended_lots == 0.58

            # SELL order should receive 0.80x multiplier penalty
            res_sell = await sizer.calculate_with_session(
                session=mock_session,
                symbol="EURUSD",
                direction="SELL",
                entry_price=1.0820,
                stop_loss=1.0840,
                take_profit=1.0740,
                account_equity=10000.0,
                risk_percent=1.0,
                vix_level=12.0,
            )
            assert res_sell.is_valid is True
            # Base risk 1.0% ($100) -> with 0.80x = $80
            # SL distance = 20 pips -> 80 / 200 = 0.40 lots
            assert res_sell.recommended_lots == 0.40

    @pytest.mark.asyncio
    async def test_tool_executor_timesfm_forecast_returns_alpha(self):
        """Verify _tool_get_timesfm_forecast enriches return dict with alpha_analysis."""
        from analysis.tools.tool_executor import ToolExecutor
        from unittest.mock import patch, MagicMock, AsyncMock

        mock_session = AsyncMock()
        executor = ToolExecutor(mock_session, settings={})

        mock_fc = {
            "status": "success",
            "current_price": 1.0850,
            "quantiles": {
                "q10": [1.0800],
                "q50": [1.0850],
                "q90": [1.0950], # upper = 0.0100, lower = 0.0050 -> skew = 2.0 (BULLISH_EXPANSION)
            },
            "expected_range": 0.0150,
            "quantile_skew": 2.0,
            "volatility_expansion_ratio": 1.0,
        }

        with patch("indicators.timesfm_engine.TimesFMEngine.get_or_generate_forecast", new=AsyncMock(return_value=mock_fc)):
            res = await executor._tool_get_timesfm_forecast(symbol="EURUSD")
            assert res["status"] == "success"
            assert "alpha_analysis" in res
            assert res["alpha_analysis"] is not None
            assert res["alpha_analysis"]["valid"] is True
            assert res["alpha_analysis"]["bias"] == "BULLISH_EXPANSION"
            assert res["alpha_analysis"]["skew_ratio"] == 2.0

    @pytest.mark.asyncio
    async def test_event_bus_live_feed_forwarder_wiring(self):
        """Verify EventBus ticks and orders are cleanly forwarded to broadcast_live_event."""
        from utils.protocol.event_bus import get_event_bus, reset_event_bus, TickPriceEvent, OrderStateChangedEvent
        import logging_observability.dashboard.api as api

        reset_event_bus()
        bus = get_event_bus()

        broadcasted = []
        async def mock_broadcast(evt_type, payload):
            broadcasted.append((evt_type, payload))

        with patch.object(api, "broadcast_live_event", side_effect=mock_broadcast):
            # Wire listeners as in main.py
            async def _on_live_tick(evt: TickPriceEvent):
                await api.broadcast_live_event("tick", {
                    "symbol": evt.symbol,
                    "bid": evt.bid,
                    "ask": evt.ask,
                    "spread": evt.spread,
                    "timestamp": str(evt.timestamp),
                })

            async def _on_live_order(evt: OrderStateChangedEvent):
                await api.broadcast_live_event("order_state_change", {
                    "order_id": evt.order_id,
                    "symbol": evt.symbol,
                    "old_state": evt.old_state,
                    "new_state": evt.new_state,
                    "details": evt.details,
                    "timestamp": str(evt.timestamp),
                })

            bus.subscribe(TickPriceEvent, _on_live_tick, priority=1)
            bus.subscribe(OrderStateChangedEvent, _on_live_order, priority=1)

            # Publish a TickPriceEvent
            tick = TickPriceEvent(symbol="EURUSD", bid=1.0850, ask=1.0852, spread=0.0002)
            await bus.publish(tick)

            # Publish an OrderStateChangedEvent
            order_ev = OrderStateChangedEvent(
                order_id="ORD-001", symbol="EURUSD", old_state="submitted", new_state="filled", details={"price": 1.0852}
            )
            await bus.publish(order_ev)

            # Verify both were broadcasted
            assert len(broadcasted) == 2
            assert broadcasted[0][0] == "tick"
            assert broadcasted[0][1]["symbol"] == "EURUSD"
            assert broadcasted[0][1]["bid"] == 1.0850

            assert broadcasted[1][0] == "order_state_change"
            assert broadcasted[1][1]["order_id"] == "ORD-001"
            assert broadcasted[1][1]["new_state"] == "filled"

        reset_event_bus()

