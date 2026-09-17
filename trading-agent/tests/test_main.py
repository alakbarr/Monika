import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import asyncio
from main import run_startup_checks, TradingAgent, _run_with_restart
import sys

class TestMain:
    @pytest.mark.asyncio
    @patch("main.os.getenv")
    @patch("sqlalchemy.ext.asyncio.AsyncEngine.connect")
    @patch("anthropic.AsyncAnthropic")
    @patch("execution.mt5_client.MT5Client")
    @patch("utils.analytics.paper_tracker.PaperTracker")
    async def test_startup_checks_success(self, mock_tracker, mock_mt5, mock_anthropic, mock_connect, mock_getenv):
        mock_tracker_inst = MagicMock()
        mock_tracker_inst.get_statistics = AsyncMock(return_value={"total_trades": 60, "win_rate_pct": 55.0})
        mock_tracker.return_value = mock_tracker_inst
        mock_mt5_inst = AsyncMock()
        mock_mt5_inst.connect = AsyncMock(return_value=True)
        mock_mt5_inst.get_symbol_info = AsyncMock(return_value=True)
        mock_mt5_inst.disconnect = AsyncMock()
        mock_mt5.return_value = mock_mt5_inst
        def mock_getenv_func(key, default=None):
            if key == "MT5_ACCOUNT":
                return "12345"
            if key == "DATABASE_URL":
                return "postgresql+asyncpg://user:pass@localhost/db"
            return "token"
        mock_getenv.side_effect = mock_getenv_func
        
        from database.models import Base
        all_tables = [
            ('news_items',), ('economic_calendar',), ('asset_analysis',), 
            ('fundamental_briefs',), ('paper_trade_records',), ('trade_outcomes',),
            ('positions',), ('risk_state',), ('system_config',),
            ('decision_reflections',), ('prescreen_log',), ('candidate_lessons',)
        ]
        all_cols = []
        for t_name, table in Base.metadata.tables.items():
            for c in table.columns:
                all_cols.append((t_name, c.name))

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(side_effect=[[(1,)], all_tables, all_cols, [], []])
        mock_connect.return_value.__aenter__.return_value = mock_conn
        
        mock_client = AsyncMock()
        mock_anthropic.return_value = mock_client
        mock_client.messages.create = AsyncMock()
        
        assert await run_startup_checks({"paper_trading": {"enabled": True, "tp_detection_method": "close_price"}}) is True

    @pytest.mark.asyncio
    @patch("sqlalchemy.ext.asyncio.AsyncEngine.connect")
    async def test_startup_checks_db_fail(self, mock_connect):
        mock_connect.side_effect = Exception("DB Fail")
        assert await run_startup_checks({"paper_trading": {"enabled": True, "tp_detection_method": "close_price"}}) is False

    @pytest.mark.asyncio
    async def test_run_with_restart(self):
        shutdown = asyncio.Event()
        
        call_count = 0
        async def coro_factory():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("Fail")
            shutdown.set() # Stop after second call
            
        await _run_with_restart("test", coro_factory, shutdown, max_restarts=3, base_delay=0)
        assert call_count == 2
        
    @pytest.mark.asyncio
    async def test_trading_agent_start_and_shutdown(self):
        agent = TradingAgent({"environment": "test"})
        
        async def block_until_shutdown():
            await agent.shutdown_event.wait()

        # Mock methods to prevent actual loops
        agent._run_dashboard = AsyncMock(side_effect=block_until_shutdown)
        agent._run_position_sync_loop = AsyncMock(side_effect=block_until_shutdown)
        agent._send_startup_notification = AsyncMock()
        agent._run_mt5_health_monitor = AsyncMock(side_effect=block_until_shutdown)
        agent._run_friday_close_monitor = AsyncMock(side_effect=block_until_shutdown)
        agent._run_position_guardian_loop = AsyncMock(side_effect=block_until_shutdown)
        agent._run_floating_drawdown_monitor = AsyncMock(side_effect=block_until_shutdown)
        agent._run_paper_trade_monitor = AsyncMock(side_effect=block_until_shutdown)
        agent._run_db_health_check = AsyncMock(side_effect=block_until_shutdown)
        agent._run_scraper_loop = AsyncMock(side_effect=block_until_shutdown)
        agent._run_whatif_resolver = AsyncMock(side_effect=block_until_shutdown)
        agent._post_restart_recovery = AsyncMock()
        
        # Override wait for shutdown to just set the event and exit
        async def trigger_shutdown():
            await asyncio.sleep(0.1)
            agent.shutdown_event.set()
        asyncio.create_task(trigger_shutdown())
        
        # Mock internal components
        agent._init_components = MagicMock()
        
        # Manually create mock components that `start()` expects
        agent.mt5_client = AsyncMock()
        agent.mt5_client.connect.return_value = True
        agent.mt5_client.is_connected.return_value = True
        
        agent.execution_service = MagicMock()
        agent.execution_service.sync_positions = AsyncMock()
        
        agent._activity_log = MagicMock()
        agent._activity_log.system = AsyncMock()
        
        # Mock schedulers to block so they don't spin in a tight loop
        agent.cycle_scheduler = MagicMock()
        agent.cycle_scheduler.start = AsyncMock(side_effect=block_until_shutdown)
        agent.cycle_scheduler.run_scheduled_reports_loop = AsyncMock(side_effect=block_until_shutdown)
        agent.cycle_scheduler.run_session_trigger_loop = AsyncMock(side_effect=block_until_shutdown)
        
        agent.news_watcher = MagicMock()
        agent.news_watcher.start = AsyncMock(side_effect=block_until_shutdown)
        
        agent.trigger_checker = MagicMock()
        agent.trigger_checker.start = AsyncMock(side_effect=block_until_shutdown)
        
        agent.telegram_bot = MagicMock()
        agent.telegram_bot.start = AsyncMock(side_effect=block_until_shutdown)
        agent.telegram_bot.send_notification = AsyncMock()
        
        agent.heartbeat_mgr = MagicMock()
        agent.heartbeat_mgr.run_forever = AsyncMock(side_effect=block_until_shutdown)
        
        agent.trailing_stop_manager = MagicMock()
        agent.trailing_stop_manager.start = AsyncMock(side_effect=block_until_shutdown)
        

        agent.position_exit_reviewer = MagicMock()
        agent.position_exit_reviewer.start = AsyncMock(side_effect=block_until_shutdown)
        
        agent.position_guardian = MagicMock()
        agent.position_guardian.start = AsyncMock(side_effect=block_until_shutdown)
        
        agent.active_calendar_poller = MagicMock()
        agent.active_calendar_poller.start = AsyncMock(side_effect=block_until_shutdown)

        agent.edge_strategy_runner = MagicMock()
        agent.edge_strategy_runner.start = AsyncMock(side_effect=block_until_shutdown)
        
        with patch("main.close_db", new_callable=AsyncMock) as mock_close_db, \
             patch("database.db.get_session") as mock_get_session:
            mock_session = AsyncMock()
            mock_session.execute.return_value.scalars.return_value.all.return_value = []
            mock_get_session.return_value.__aenter__.return_value = mock_session

            await agent.start()
            
            # Ensure shutdown was called
            mock_close_db.assert_called_once()
            assert agent.shutdown_event.is_set()

    @pytest.mark.asyncio
    async def test_trading_agent_shutdown_with_blocking_bot(self):
        """Verify that agent.start() shuts down cleanly even when telegram_bot.start() blocks indefinitely."""
        agent = TradingAgent({"environment": "test"})
        
        async def block_forever():
            await asyncio.get_running_loop().create_future()

        # Mock methods to block until cancelled
        agent._run_dashboard = AsyncMock(side_effect=block_forever)
        agent._run_position_sync_loop = AsyncMock(side_effect=block_forever)
        agent._send_startup_notification = AsyncMock()
        agent._run_mt5_health_monitor = AsyncMock(side_effect=block_forever)
        agent._run_friday_close_monitor = AsyncMock(side_effect=block_forever)
        agent._run_position_guardian_loop = AsyncMock(side_effect=block_forever)
        agent._run_floating_drawdown_monitor = AsyncMock(side_effect=block_forever)
        agent._run_paper_trade_monitor = AsyncMock(side_effect=block_forever)
        agent._run_db_health_check = AsyncMock(side_effect=block_forever)
        agent._run_scraper_loop = AsyncMock(side_effect=block_forever)
        agent._run_whatif_resolver = AsyncMock(side_effect=block_forever)
        agent._post_restart_recovery = AsyncMock()

        # Mock internal components
        agent._init_components = MagicMock()
        agent.mt5_client = AsyncMock()
        agent.mt5_client.connect.return_value = True
        agent.execution_service = MagicMock()
        agent._activity_log = MagicMock()
        agent._activity_log.system = AsyncMock()

        agent.cycle_scheduler = MagicMock()
        agent.cycle_scheduler.start = AsyncMock(side_effect=block_forever)
        agent.cycle_scheduler.run_scheduled_reports_loop = AsyncMock(side_effect=block_forever)
        agent.cycle_scheduler.run_session_trigger_loop = AsyncMock(side_effect=block_forever)
        agent.news_watcher = MagicMock()
        agent.news_watcher.start = AsyncMock(side_effect=block_forever)
        agent.trigger_checker = MagicMock()
        agent.trigger_checker.start = AsyncMock(side_effect=block_forever)
        agent.heartbeat_mgr = MagicMock()
        agent.heartbeat_mgr.run_forever = AsyncMock(side_effect=block_forever)
        agent.trailing_stop_manager = MagicMock()
        agent.trailing_stop_manager.start = AsyncMock(side_effect=block_forever)
        agent.position_exit_reviewer = MagicMock()
        agent.position_exit_reviewer.start = AsyncMock(side_effect=block_forever)
        agent.position_guardian = MagicMock()
        agent.position_guardian.start = AsyncMock(side_effect=block_forever)
        agent.active_calendar_poller = MagicMock()
        agent.active_calendar_poller.start = AsyncMock(side_effect=block_forever)
        agent.edge_strategy_runner = MagicMock()
        agent.edge_strategy_runner.start = AsyncMock(side_effect=block_forever)

        # Telegram bot blocks on future (simulating real telegram_bot.start)
        agent.telegram_bot = MagicMock()
        agent.telegram_bot.start = AsyncMock(side_effect=block_forever)
        agent.telegram_bot.send_notification = AsyncMock()

        # Trigger shutdown after a short delay
        async def trigger_shutdown():
            await asyncio.sleep(0.05)
            agent.shutdown_event.set()
        asyncio.create_task(trigger_shutdown())

        with patch("main.close_db", new_callable=AsyncMock) as mock_close_db, \
             patch("database.db.get_session") as mock_get_session:
            mock_session = AsyncMock()
            mock_session.execute.return_value.scalars.return_value.all.return_value = []
            mock_get_session.return_value.__aenter__.return_value = mock_session

            # Must complete within 2 seconds without hanging
            await asyncio.wait_for(agent.start(), timeout=30.0)

            mock_close_db.assert_called_once()
            assert agent.shutdown_event.is_set()
            assert agent._tg_task.done()

    @pytest.mark.asyncio
    async def test_post_restart_recovery_at_0300_no_false_cycle(self):
        from database.models import CyclePerformance, FundamentalBrief
        from datetime import datetime, timezone, timedelta
        
        agent = TradingAgent({
            "trading": {
                "schedule": {
                    "timezone": "Asia/Jakarta",
                    "cycle_times_local": ["07:00", "15:00", "20:00"],
                    "catch_up_missed_cycles": True,
                }
            },
            "data_quality": {
                "max_brief_age_analysis_hours": 12.0
            }
        })
        agent.execution_service = None
        agent.mt5_client = None
        agent.position_guardian = None
        agent.market_data_scheduler = None
        agent.cycle_scheduler = MagicMock()
        agent.cycle_scheduler.run_once = AsyncMock()

        # Local time: 03:00 WIB on 2026-09-04 -> UTC 2026-09-03 20:00:00
        simulated_now = datetime(2026, 9, 3, 20, 0, 0, tzinfo=timezone.utc)
        
        # Last cycle: 20:02 WIB on 2026-09-03 -> UTC 2026-09-03 13:02:00
        last_cycle = CyclePerformance(cycle_at=datetime(2026, 9, 3, 13, 2, 0, tzinfo=timezone.utc))
        brief = FundamentalBrief(
            generated_at=datetime(2026, 9, 3, 13, 2, 0, tzinfo=timezone.utc),
            valid_until=datetime(2026, 9, 4, 1, 2, 0, tzinfo=timezone.utc)
        )

        mock_session = AsyncMock()
        mock_session.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=last_cycle)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=brief)),
        ]
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session

        with patch("main.datetime") as mock_dt, \
             patch("database.db.get_session", return_value=mock_ctx):
            mock_dt.now.return_value = simulated_now
            mock_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
            with patch("main.asyncio.sleep", new=AsyncMock()):
                await agent._post_restart_recovery()
            await asyncio.sleep(0.01)

        agent.cycle_scheduler.run_once.assert_not_called()

    @pytest.mark.asyncio
    async def test_post_restart_recovery_at_0300_missed_2000_cycle(self):
        from database.models import CyclePerformance, FundamentalBrief
        from datetime import datetime, timezone, timedelta

        agent = TradingAgent({
            "trading": {
                "schedule": {
                    "timezone": "Asia/Jakarta",
                    "cycle_times_local": ["07:00", "15:00", "20:00"],
                    "catch_up_missed_cycles": True,
                }
            },
            "data_quality": {
                "max_brief_age_analysis_hours": 12.0
            }
        })
        agent.execution_service = None
        agent.mt5_client = None
        agent.position_guardian = None
        agent.market_data_scheduler = None
        agent.cycle_scheduler = MagicMock()
        agent.cycle_scheduler.run_once = AsyncMock()

        # Local time: 03:00 WIB on 2026-09-04 -> UTC 2026-09-03 20:00:00
        simulated_now = datetime(2026, 9, 3, 20, 0, 0, tzinfo=timezone.utc)
        
        # Last cycle: 15:02 WIB on 2026-09-03 -> UTC 2026-09-03 08:02:00 (20:00 cycle was missed!)
        last_cycle = CyclePerformance(cycle_at=datetime(2026, 9, 3, 8, 2, 0, tzinfo=timezone.utc))
        brief = FundamentalBrief(
            generated_at=datetime(2026, 9, 3, 8, 2, 0, tzinfo=timezone.utc),
            valid_until=datetime(2026, 9, 3, 20, 2, 0, tzinfo=timezone.utc)
        )

        mock_session = AsyncMock()
        mock_session.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=last_cycle)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=brief)),
        ]
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session

        with patch("main.datetime") as mock_dt, \
             patch("database.db.get_session", return_value=mock_ctx):
            mock_dt.now.return_value = simulated_now
            mock_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
            with patch("main.asyncio.sleep", new=AsyncMock()):
                await agent._post_restart_recovery()
            await asyncio.sleep(0.01)

        agent.cycle_scheduler.run_once.assert_called_once_with(forced=True)

    @pytest.mark.asyncio
    async def test_post_restart_recovery_at_0715_missed_0700_cycle(self):
        from database.models import CyclePerformance, FundamentalBrief
        from datetime import datetime, timezone, timedelta

        agent = TradingAgent({
            "trading": {
                "schedule": {
                    "timezone": "Asia/Jakarta",
                    "cycle_times_local": ["07:00", "15:00", "20:00"],
                    "catch_up_missed_cycles": True,
                }
            },
            "data_quality": {
                "max_brief_age_analysis_hours": 12.0
            }
        })
        agent.execution_service = None
        agent.mt5_client = None
        agent.position_guardian = None
        agent.market_data_scheduler = None
        agent.cycle_scheduler = MagicMock()
        agent.cycle_scheduler.run_once = AsyncMock()

        # Local time: 07:15 WIB on 2026-09-04 -> UTC 2026-09-04 00:15:00
        simulated_now = datetime(2026, 9, 4, 0, 15, 0, tzinfo=timezone.utc)
        
        # Last cycle: 20:02 WIB on 2026-09-03 -> UTC 2026-09-03 13:02:00 (07:00 cycle was missed!)
        last_cycle = CyclePerformance(cycle_at=datetime(2026, 9, 3, 13, 2, 0, tzinfo=timezone.utc))
        brief = FundamentalBrief(
            generated_at=datetime(2026, 9, 3, 13, 2, 0, tzinfo=timezone.utc),
            valid_until=datetime(2026, 9, 4, 1, 2, 0, tzinfo=timezone.utc)
        )

        mock_session = AsyncMock()
        mock_session.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=last_cycle)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=brief)),
        ]
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session

        with patch("main.datetime") as mock_dt, \
             patch("database.db.get_session", return_value=mock_ctx):
            mock_dt.now.return_value = simulated_now
            mock_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
            with patch("main.asyncio.sleep", new=AsyncMock()):
                await agent._post_restart_recovery()
            await asyncio.sleep(0.01)

        agent.cycle_scheduler.run_once.assert_called_once_with(forced=True)

    @pytest.mark.asyncio
    async def test_post_restart_recovery_at_0645_upcoming_0700_cycle(self):
        from database.models import CyclePerformance, FundamentalBrief
        from datetime import datetime, timezone, timedelta

        agent = TradingAgent({
            "trading": {
                "schedule": {
                    "timezone": "Asia/Jakarta",
                    "cycle_times_local": ["07:00", "15:00", "20:00"],
                    "catch_up_missed_cycles": True,
                }
            },
            "data_quality": {
                "max_brief_age_analysis_hours": 12.0
            }
        })
        agent.execution_service = None
        agent.mt5_client = None
        agent.position_guardian = None
        agent.market_data_scheduler = None
        agent.cycle_scheduler = MagicMock()
        agent.cycle_scheduler.run_once = AsyncMock()

        # Local time: 06:45 WIB on 2026-09-04 -> UTC 2026-09-03 23:45:00
        simulated_now = datetime(2026, 9, 3, 23, 45, 0, tzinfo=timezone.utc)
        
        # Last cycle: 20:02 WIB on 2026-09-03 -> UTC 2026-09-03 13:02:00 (covered 20:00 target, 07:00 is next)
        last_cycle = CyclePerformance(cycle_at=datetime(2026, 9, 3, 13, 2, 0, tzinfo=timezone.utc))
        brief = FundamentalBrief(
            generated_at=datetime(2026, 9, 3, 13, 2, 0, tzinfo=timezone.utc),
            valid_until=datetime(2026, 9, 4, 1, 2, 0, tzinfo=timezone.utc)
        )

        mock_session = AsyncMock()
        mock_session.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=last_cycle)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=brief)),
        ]
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session

        with patch("main.datetime") as mock_dt, \
             patch("database.db.get_session", return_value=mock_ctx):
            mock_dt.now.return_value = simulated_now
            mock_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
            with patch("main.asyncio.sleep", new=AsyncMock()):
                await agent._post_restart_recovery()
            await asyncio.sleep(0.01)

        # At 06:45 WIB, 07:00 WIB is 15 minutes away, previous 20:00 target was covered, no false recovery
        agent.cycle_scheduler.run_once.assert_not_called()

    @pytest.mark.asyncio
    async def test_post_restart_recovery_missing_brief_with_last_cycle(self):
        """Verify recovery is triggered without TypeError when last_cycle exists but brief is None."""
        from database.models import CyclePerformance
        from datetime import datetime, timezone

        agent = TradingAgent({
            "trading": {
                "schedule": {
                    "timezone": "Asia/Jakarta",
                    "cycle_times_local": ["07:00", "15:00", "20:00"],
                    "catch_up_missed_cycles": True,
                }
            },
            "data_quality": {
                "max_brief_age_analysis_hours": 12.0
            }
        })
        agent.execution_service = None
        agent.mt5_client = None
        agent.position_guardian = None
        agent.market_data_scheduler = None
        agent.cycle_scheduler = MagicMock()
        agent.cycle_scheduler.run_once = AsyncMock()

        # Local time: 03:00 WIB -> UTC 20:00
        simulated_now = datetime(2026, 9, 3, 20, 0, 0, tzinfo=timezone.utc)
        # Cycle ran at 20:02 yesterday, but brief is missing from database
        last_cycle = CyclePerformance(cycle_at=datetime(2026, 9, 3, 13, 2, 0, tzinfo=timezone.utc))

        mock_session = AsyncMock()
        mock_session.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=last_cycle)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # brief is None
        ]
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session

        with patch("main.datetime") as mock_dt, \
             patch("database.db.get_session", return_value=mock_ctx):
            mock_dt.now.return_value = simulated_now
            mock_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
            with patch("main.asyncio.sleep", new=AsyncMock()):
                await agent._post_restart_recovery()
            await asyncio.sleep(0.01)

        # Must dispatch recovery because brief is missing, without TypeError crash!
        agent.cycle_scheduler.run_once.assert_called_once_with(forced=True)

    @pytest.mark.asyncio
    async def test_post_restart_recovery_brief_null_generated_at(self):
        """Verify recovery is triggered when brief exists but has null generated_at."""
        from database.models import CyclePerformance, FundamentalBrief
        from datetime import datetime, timezone

        agent = TradingAgent({
            "trading": {
                "schedule": {
                    "timezone": "Asia/Jakarta",
                    "cycle_times_local": ["07:00", "15:00", "20:00"],
                    "catch_up_missed_cycles": True,
                }
            },
            "data_quality": {
                "max_brief_age_analysis_hours": 12.0
            }
        })
        agent.execution_service = None
        agent.mt5_client = None
        agent.position_guardian = None
        agent.market_data_scheduler = None
        agent.cycle_scheduler = MagicMock()
        agent.cycle_scheduler.run_once = AsyncMock()

        simulated_now = datetime(2026, 9, 3, 20, 0, 0, tzinfo=timezone.utc)
        last_cycle = CyclePerformance(cycle_at=datetime(2026, 9, 3, 13, 2, 0, tzinfo=timezone.utc))
        brief_null_gen = FundamentalBrief(generated_at=None, valid_until=None)

        mock_session = AsyncMock()
        mock_session.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=last_cycle)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=brief_null_gen)),
        ]
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session

        with patch("main.datetime") as mock_dt, \
             patch("database.db.get_session", return_value=mock_ctx):
            mock_dt.now.return_value = simulated_now
            mock_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
            with patch("main.asyncio.sleep", new=AsyncMock()):
                await agent._post_restart_recovery()
            await asyncio.sleep(0.01)

        agent.cycle_scheduler.run_once.assert_called_once_with(forced=True)

    @pytest.mark.asyncio
    async def test_register_signals_sighup_reload(self):
        import signal
        agent = TradingAgent({"test_key": "initial_val"})

        # Mock signal.SIGHUP if not present (e.g. on Windows)
        fake_sighup = getattr(signal, "SIGHUP", 1)
        mock_loop = MagicMock()
        registered_handlers = {}

        def fake_add_signal_handler(sig, callback):
            registered_handlers[sig] = callback

        mock_loop.add_signal_handler.side_effect = fake_add_signal_handler

        with patch("main.asyncio.get_running_loop", return_value=mock_loop), \
             patch("main.signal.SIGHUP", fake_sighup, create=True), \
             patch("config.settings.load_all_config", return_value={"test_key": "reloaded_val"}):
            agent._register_signals()

            assert fake_sighup in registered_handlers
            # Invoke the SIGHUP callback
            registered_handlers[fake_sighup]()
            assert agent.settings["test_key"] == "reloaded_val"
            # Crucial: SIGHUP must NOT trigger shutdown!
            assert not agent.shutdown_event.is_set()



