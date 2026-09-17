"""
Unit tests verifying Round 2 audit remediations across all system modules:
- Broker adapter & emergency manager
- Order execution tranche lot rounding
- Risk gate weekend gap & ETHUSD exemption
- Sentiment tool canonical alias
- Trigger checker cycle lock coordination
- Position guardian Friday auto-close strategy logic
- Schedulers stop_event graceful shutdown
- Database model nullability & domain_models exports
- Settings bidirectional sync & schema validation
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from execution.broker_adapter import SimulatedBrokerAdapter, BrokerAdapter, MT5RemoteGatewayAdapter, _get_contract_size
from execution.service.emergency_manager import EmergencyManagerMixin
from risk.position_sizing import PositionSizer
from risk.risk_gate import RiskGate
from analysis.tools.domain.sentiment_handlers import SentimentToolHandlers
from scheduler.trigger_checker import TriggerChecker
from scheduler.position_guardian import PositionGuardian
from scheduler.alpha_discovery_scheduler import AlphaDiscoveryScheduler
from scheduler.strategy_synthesis_scheduler import StrategySynthesisScheduler
from scheduler.digest_slice_scheduler import DigestSliceScheduler
from scheduler.macro_data_scheduler import MacroDataScheduler
from scheduler.position_exit_reviewer import PositionExitReviewer
from scheduler.market_data_scheduler import MarketDataScheduler
from scheduler.news_watcher import NewsWatcher
from scheduler.post_release_analyzer import PostReleaseAnalyzer
from scheduler.trailing_stop_manager import TrailingStopManager
from database.models import DecisionReflection, Position
from config.settings import load_settings
from config.schemas import PaperTradingConfig


class DummyExecutionService(EmergencyManagerMixin):
    def __init__(self, broker_adapter=None, gate=None):
        self.broker_adapter = broker_adapter
        self.gate = gate or MagicMock()
        self.gate.pause_trading = AsyncMock()
        self.settings = {"trading": {"auto_execute": True}}


class TestBrokerAdapterRemediation:
    def test_xti_contract_size_distinction(self):
        """XTIUSD (WTI Crude) must have 100 contract size, distinct from Brent (1000)."""
        assert _get_contract_size("XTIUSD") == 100.0
        assert _get_contract_size("WTI") == 100.0
        assert _get_contract_size("XBRUSD") == 1000.0
        assert _get_contract_size("BRENT") == 1000.0

    @pytest.mark.asyncio
    async def test_simulated_adapter_close_all_positions(self):
        """SimulatedBrokerAdapter.close_all_positions should close all simulated positions."""
        adapter = SimulatedBrokerAdapter()
        adapter.positions = {
            101: {"ticket": 101, "symbol": "EURUSD", "volume": 0.1},
            102: {"ticket": 102, "symbol": "XAUUSD", "volume": 0.05},
        }
        res = await adapter.close_all_positions()
        assert res["closed"] == 2
        assert len(adapter.positions) == 0

    @pytest.mark.asyncio
    async def test_emergency_manager_kill_switch_uses_broker_adapter(self):
        """EmergencyManagerMixin.kill_switch delegates to broker_adapter.close_all_positions."""
        mock_adapter = MagicMock()
        mock_adapter.close_all_positions = AsyncMock(return_value={"closed": 3, "failed": 0, "errors": []})
        mock_adapter.get_open_positions = AsyncMock(return_value=[])

        manager = DummyExecutionService(broker_adapter=mock_adapter)

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        with patch("execution.service.emergency_manager.get_session") as mock_get_sess:
            mock_get_sess.return_value.__aenter__.return_value = mock_session
            res = await manager.kill_switch(reason="Test kill switch")

        assert res.get("closed") == 3
        mock_adapter.close_all_positions.assert_awaited_once()


class TestRiskGateRemediation:
    @pytest.mark.asyncio
    async def test_ethusd_exempt_from_weekend_gap_and_alias_present(self):
        """ETHUSD must be exempted from weekend gap alongside BTCUSD, and alias exists."""
        gate = RiskGate(settings={"trading": {"weekend_management": {"exempted_symbols": ["BTCUSD", "ETHUSD"]}}})
        # Check method alias
        assert hasattr(gate, "_check_weekend_gap_risk")
        assert gate._check_weekend_gap_risk == gate.assess_weekend_gap_risk

        mock_session = AsyncMock()
        # ETHUSD gap risk should be allowed (empty/low risk)
        allowed_btc, _ = await gate.assess_weekend_gap_risk(mock_session, "BTCUSD")
        allowed_eth, _ = await gate.assess_weekend_gap_risk(mock_session, "ETHUSD")
        assert allowed_btc is True
        assert allowed_eth is True


class TestSentimentHandlersAlias:
    def test_get_fear_greed_index_alias(self):
        """get_fear_greed_index should be a direct alias to get_fear_greed on SentimentToolHandlers."""
        handlers = SentimentToolHandlers()
        assert hasattr(handlers, "get_fear_greed_index")
        assert handlers.get_fear_greed_index == handlers.get_fear_greed


class TestTriggerCheckerCycleLock:
    @pytest.mark.asyncio
    async def test_trigger_checker_respects_cycle_lock(self):
        """TriggerChecker acquires cycle_lock from cycle_scheduler when running background reanalysis."""
        mock_cycle_sched = MagicMock()
        mock_lock = asyncio.Lock()
        mock_cycle_sched._cycle_lock = mock_lock

        mock_stage = MagicMock()
        mock_stage.run_one = AsyncMock(return_value={"decision": "hold"})

        checker = TriggerChecker(
            settings={"trading": {"trigger_checker": {"max_trigger_age_hours": 18}}},
            per_asset_stage=mock_stage,
            cycle_scheduler=mock_cycle_sched,
        )

        # Acquire lock beforehand to simulate running graph cycle
        await mock_lock.acquire()

        task = asyncio.create_task(checker._background_reanalysis("EURUSD"))
        # Give event loop a cycle; task should wait on lock
        await asyncio.sleep(0.01)
        assert not task.done()
        assert mock_stage.run_one.call_count == 0

        # Release lock; task should finish
        mock_lock.release()
        await task
        assert mock_stage.run_one.call_count == 1


class TestPositionGuardianFridayClose:
    @pytest.mark.asyncio
    async def test_friday_close_if_profitable_skips_losing_position(self):
        """Friday close_if_profitable strategy must only close positions with unrealized_pnl > 0."""
        mock_exec = MagicMock()
        mock_exec.close_position_by_ticket = AsyncMock()

        pos_win = MagicMock(spec=Position)
        pos_win.symbol = "EURUSD"
        pos_win.mt5_ticket = 1111
        pos_win.unrealized_pnl = 50.0

        pos_loss = MagicMock(spec=Position)
        pos_loss.symbol = "GBPUSD"
        pos_loss.mt5_ticket = 2222
        pos_loss.unrealized_pnl = -30.0

        guardian = PositionGuardian(
            settings={
                "trading": {
                    "weekend_management": {
                        "strategy": "close_if_profitable",
                        "auto_close_friday_positions": True,
                    }
                }
            },
            execution_service=mock_exec,
        )

        # Mock clock/time to Friday 20:30 UTC
        with patch("scheduler.position_guardian.clock.now") as mock_clock_now, \
             patch("scheduler.position_guardian.get_session") as mock_sess:
            mock_now = MagicMock()
            mock_now.weekday.return_value = 4  # Friday
            mock_now.hour = 20
            mock_clock_now.return_value = mock_now

            sess = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [pos_win, pos_loss]
            sess.execute.return_value = mock_result
            mock_sess.return_value.__aenter__.return_value = sess

            await guardian.check_friday_close_protection()

            # pos_win should be closed
            mock_exec.close_position_by_ticket.assert_any_await(
                1111,
                requested_by="position_guardian_friday",
                reason="Friday auto-close (close_if_profitable): weekend gap protection",
            )
            # pos_loss (ticket 2222) should NOT be closed
            tickets_called = [call.args[0] for call in mock_exec.close_position_by_ticket.await_args_list]
            assert 1111 in tickets_called
            assert 2222 not in tickets_called


class TestSchedulersStopEvent:
    def test_all_schedulers_have_stop_event_and_stop_method(self):
        """All 9 refactored schedulers must instantiate _stop_event and set it on stop()."""
        schedulers = [
            AlphaDiscoveryScheduler(settings={}),
            StrategySynthesisScheduler(settings={}),
            DigestSliceScheduler(settings={}),
            MacroDataScheduler(settings={}),
            PositionExitReviewer(settings={}),
            MarketDataScheduler(settings={}),
            NewsWatcher(settings={}),
            PostReleaseAnalyzer(settings={}),
            TrailingStopManager(settings={}),
        ]

        for s in schedulers:
            assert hasattr(s, "_stop_event"), f"{type(s).__name__} missing _stop_event"
            assert isinstance(s._stop_event, asyncio.Event)
            assert not s._stop_event.is_set()

            # Calling stop() should set _stop_event
            s.stop()
            assert s._stop_event.is_set(), f"{type(s).__name__} stop() did not set _stop_event"


class TestDatabaseAndConfigRemediation:
    def test_decision_reflection_analysis_id_nullable(self):
        """DecisionReflection.analysis_id column must be nullable=True."""
        col = DecisionReflection.__table__.columns["analysis_id"]
        assert col.nullable is True

    def test_paper_trading_config_schema(self):
        """PaperTradingConfig must validate initial_balance and simulation params."""
        cfg = PaperTradingConfig(
            enabled=True,
            initial_balance=25000.0,
            tp_detection_method="tick_high_low",
            realistic_sl_tp_conflict="sl_wins",
            max_paper_trade_holding_hours=72.0,
            spread_realistic_multiplier=2.5,
            spread_multipliers={"XAUUSD": 3.0},
        )
        assert cfg.initial_balance == 25000.0
        assert cfg.tp_detection_method == "tick_high_low"
        assert cfg.spread_multipliers["XAUUSD"] == 3.0

    def test_settings_schedule_bidirectional_sync(self):
        """Settings loader should synchronize trading.schedule and root scheduler."""
        raw_settings = {
            "trading": {
                "schedule": {
                    "analysis_cycle_hours": 6.0,
                },
                "paper_trading": {
                    "enabled": True,
                },
            },
        }
        loaded = load_settings(raw_settings, validate=False)
        assert loaded["scheduler"]["cycle_interval_hours"] == 6.0
        assert loaded["trading"]["schedule"]["analysis_cycle_hours"] == 6.0

    def test_domain_models_exports(self):
        """database.domain_models should export BacktestRun, BacktestTrade, TradePlanLeg, etc."""
        import database.domain_models as dm
        assert hasattr(dm, "BacktestRun")
        assert hasattr(dm, "BacktestTrade")
        assert hasattr(dm, "TradePlanLeg")
        assert hasattr(dm, "CentralBankRateExpectation")
        assert hasattr(dm, "TimesFMForecast")
