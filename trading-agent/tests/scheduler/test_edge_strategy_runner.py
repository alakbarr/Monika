import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch
from scheduler.edge_strategy_runner import EdgeStrategyRunner
from analysis.strategies.base_strategy import EdgeSignal


class TestEdgeStrategyRunner:

    @pytest.fixture
    def settings(self):
        return {
            "trading": {
                "asset_universe": ["GBPUSD"],
                "edge_strategy": {
                    "signal_cooldown_seconds": 3600,
                    "macro_gate_exempt_strategies": ["gap_fade", "tsm_momentum"]
                }
            }
        }

    @pytest.mark.asyncio
    async def test_skip_signal_when_position_already_open(self, settings):
        runner = EdgeStrategyRunner(settings=settings, execution_service=MagicMock())
        
        signal = EdgeSignal(
            strategy_id="tsm_momentum",
            symbol="GBPUSD",
            direction="buy",
            valid=True,
            confidence=0.8,
            entry_price=1.2500,
            stop_loss=1.2400,
            take_profit=1.2700,
            rationale="Test signal"
        )

        mock_session = AsyncMock()
        
        # Mock validate_data_freshness -> ready: True
        with patch("scheduler.edge_strategy_runner.validate_data_freshness", AsyncMock(return_value={"ready": True})), \
             patch("scheduler.edge_strategy_runner.StrategyRegistry.evaluate_all", AsyncMock(return_value=[signal])), \
             patch("scheduler.edge_strategy_runner.get_session") as mock_get_session:
            
            mock_get_session.return_value.__aenter__.return_value = mock_session
            
            # Mock open position check returning an open position ID (e.g., id=1)
            mock_res = MagicMock()
            mock_res.scalar_one_or_none.return_value = 1  # open position exists!
            mock_session.execute.return_value = mock_res

            with patch.object(runner, "_materialize_and_route", AsyncMock()) as mock_route:
                await runner.run_once()
                mock_route.assert_not_called()

    @pytest.mark.asyncio
    async def test_signal_cooldown_prevents_re_evaluation(self, settings):
        runner = EdgeStrategyRunner(settings=settings, execution_service=MagicMock())
        runner.cooldown_seconds = 3600
        
        # Pre-populate cooldown timestamp
        runner._signal_cooldowns[("tsm_momentum", "GBPUSD")] = time.time() - 300  # 5 min ago (< 1 hour)
        
        signal = EdgeSignal(
            strategy_id="tsm_momentum",
            symbol="GBPUSD",
            direction="buy",
            valid=True,
            confidence=0.8,
            entry_price=1.2500,
            stop_loss=1.2400,
            take_profit=1.2700,
            rationale="Test signal"
        )

        mock_session = AsyncMock()
        
        with patch("scheduler.edge_strategy_runner.validate_data_freshness", AsyncMock(return_value={"ready": True})), \
             patch("scheduler.edge_strategy_runner.StrategyRegistry.evaluate_all", AsyncMock(return_value=[signal])), \
             patch("scheduler.edge_strategy_runner.get_session") as mock_get_session:
            
            mock_get_session.return_value.__aenter__.return_value = mock_session
            
            # No open position
            mock_res = MagicMock()
            mock_res.scalar_one_or_none.return_value = None
            mock_session.execute.return_value = mock_res

            with patch.object(runner, "_materialize_and_route", AsyncMock()) as mock_route:
                await runner.run_once()
                mock_route.assert_not_called()

    @pytest.mark.asyncio
    async def test_materialize_and_route_updates_execution_status(self, settings):
        mock_exec_svc = MagicMock()
        mock_exec_res = MagicMock()
        mock_exec_res.executed = False
        mock_exec_res.risk_approved = False
        mock_exec_res.summary.return_value = "BLOCKED [GBPUSD] BUY - RiskGate rejected"
        mock_exec_svc.execute_analysis = AsyncMock(return_value=mock_exec_res)

        runner = EdgeStrategyRunner(settings=settings, execution_service=mock_exec_svc)

        signal = EdgeSignal(
            strategy_id="tsm_momentum",
            symbol="GBPUSD",
            direction="buy",
            valid=True,
            confidence=0.8,
            entry_price=1.2500,
            stop_loss=1.2400,
            take_profit=1.2700,
            rationale="Test signal"
        )

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        mock_graph = MagicMock()
        async def mock_ainvoke(state, config=None):
            for a in state.get("event_data", {}).get("analyses", []):
                await mock_exec_svc.execute_analysis(a, mock_session)
        mock_graph.ainvoke = AsyncMock(side_effect=mock_ainvoke)

        with patch("graph.reactive_graph.get_reactive_graph", return_value=mock_graph):
            await runner._materialize_and_route(mock_session, signal)
        
        # Verify execute_analysis was called
        mock_exec_svc.execute_analysis.assert_called_once()

    @pytest.mark.asyncio
    async def test_skip_signal_when_paper_trade_already_open(self, settings):
        runner = EdgeStrategyRunner(settings=settings, execution_service=MagicMock())
        
        signal = EdgeSignal(
            strategy_id="tsm_momentum",
            symbol="GBPUSD",
            direction="buy",
            valid=True,
            confidence=0.8,
            entry_price=1.2500,
            stop_loss=1.2400,
            take_profit=1.2700,
            rationale="Test signal"
        )

        mock_session = AsyncMock()
        
        with patch("scheduler.edge_strategy_runner.validate_data_freshness", AsyncMock(return_value={"ready": True})), \
             patch("scheduler.edge_strategy_runner.StrategyRegistry.evaluate_all", AsyncMock(return_value=[signal])), \
             patch("scheduler.edge_strategy_runner.get_session") as mock_get_session:
            
            mock_get_session.return_value.__aenter__.return_value = mock_session
            
            # First execute: Position.id -> None (no live position)
            # Second execute: PaperTradeRecord.id -> 42 (paper trade open!)
            mock_res_pos = MagicMock()
            mock_res_pos.scalar_one_or_none.return_value = None
            mock_res_paper = MagicMock()
            mock_res_paper.scalar_one_or_none.return_value = 42

            mock_session.execute.side_effect = [mock_res_pos, mock_res_paper]

            with patch.object(runner, "_materialize_and_route", AsyncMock()) as mock_route:
                await runner.run_once()
                mock_route.assert_not_called()

    @pytest.mark.asyncio
    async def test_persistent_cooldown_from_database(self, settings):
        runner = EdgeStrategyRunner(settings=settings, execution_service=MagicMock())
        runner.cooldown_seconds = 3600
        # In-memory is empty (e.g. freshly restarted)
        assert len(runner._signal_cooldowns) == 0

        from datetime import datetime, timezone, timedelta
        from utils import clock
        recent_dt = clock.now() - timedelta(minutes=10)

        mock_session = AsyncMock()
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = recent_dt
        mock_session.execute.return_value = mock_res

        in_cd = await runner._is_in_cooldown(mock_session, "tsm_momentum", "GBPUSD", time.time())
        assert in_cd is True
        # In-memory cache should now be populated from DB
        assert ("tsm_momentum", "GBPUSD") in runner._signal_cooldowns

    @pytest.mark.asyncio
    async def test_pretrade_gate_rejection_throttling(self, settings):
        runner = EdgeStrategyRunner(settings=settings, execution_service=MagicMock())
        runner.cooldown_seconds = 3600

        signal = EdgeSignal(
            strategy_id="tsm_momentum",
            symbol="GBPUSD",
            direction="buy",
            valid=True,
            confidence=0.8,
            rationale="Test",
            tags=["trend"]
        )

        mock_session = AsyncMock()
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_res

        gate_reason = "balanced volume regime blocks pure trend-following"
        with patch("scheduler.edge_strategy_runner.get_session") as mock_get_session, \
             patch("scheduler.edge_strategy_runner.validate_data_freshness", AsyncMock(return_value={"ready": True})), \
             patch("scheduler.edge_strategy_runner.StrategyRegistry.evaluate_all", AsyncMock(return_value=[signal])), \
             patch("scheduler.edge_strategy_runner.evaluate_pretrade_gate", AsyncMock(return_value=(False, gate_reason))), \
             patch("scheduler.edge_strategy_runner.logger") as mock_logger:

            mock_get_session.return_value.__aenter__.return_value = mock_session

            # First run: should log at INFO and record in _gate_rejection_log_time
            await runner.run_once()
            gate_key = ("tsm_momentum", "GBPUSD", gate_reason)
            assert gate_key in runner._gate_rejection_log_time
            mock_logger.info.assert_called()
            info_calls = [call for call in mock_logger.info.call_args_list if "throttled" in str(call)]
            assert len(info_calls) >= 1

            # Second run immediately after:
            mock_logger.reset_mock()
            await runner.run_once()
            # Should log at DEBUG, not INFO
            mock_logger.debug.assert_called()
            info_calls = [call for call in mock_logger.info.call_args_list if "throttled" in str(call)]
            assert len(info_calls) == 0

    @pytest.mark.asyncio
    async def test_materialize_and_route_suppresses_low_rr_signal(self, settings):
        mock_exec_svc = MagicMock()
        mock_exec_svc.execute_analysis = AsyncMock()
        runner = EdgeStrategyRunner(settings=settings, execution_service=mock_exec_svc)

        # RR = (1.2550 - 1.2500) / (1.2500 - 1.2400) = 0.0050 / 0.0100 = 0.50 < 1.3
        signal = EdgeSignal(
            strategy_id="tsm_momentum",
            symbol="GBPUSD",
            direction="buy",
            valid=True,
            confidence=0.8,
            entry_price=1.2500,
            stop_loss=1.2400,
            take_profit=1.2550,
            rationale="Sub-optimal RR signal"
        )

        mock_session = AsyncMock()
        await runner._materialize_and_route(mock_session, signal)

        # Should be suppressed by upstream R:R pre-filter before materialization
        mock_session.add.assert_not_called()
        mock_exec_svc.execute_analysis.assert_not_called()


