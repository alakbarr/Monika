import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from scheduler.cycle_scheduler import CycleScheduler

class TestCycleScheduler:
    @pytest.fixture
    def settings(self):
        return {
            "trading": {
                "schedule": {
                    "analysis_cycle_hours": 6
                },
                "asset_universe": ["XAUUSD", "EURUSD"],
                "mt5": {
                    "timeframes": ["H1", "H4"]
                }
            },
            "gemini": {
                "api_key": "test"
            }
        }

    @pytest.fixture
    def mock_mt5(self):
        mt5 = MagicMock()
        mt5.fetch_and_save_all = AsyncMock(return_value={"fetched": 200})
        return mt5

    @pytest.fixture
    def mock_fundamental(self):
        stage = MagicMock()
        stage.run = AsyncMock(return_value={"success": True, "brief_id": 123})
        return stage

    @pytest.fixture
    def mock_per_asset(self):
        stage = MagicMock()
        stage.run_all = AsyncMock(return_value={"XAUUSD": {"decision": "buy"}})
        return stage

    @pytest.mark.asyncio
    async def test_cycle_scheduler_run_once_raises_not_implemented(self, settings):
        """Memastikan base class CycleScheduler.run_once() melempar NotImplementedError sesuai rancangan."""
        scheduler = CycleScheduler(settings)
        with pytest.raises(NotImplementedError, match="Use GraphCycleScheduler.run_once()"):
            await scheduler.run_once()

    @pytest.mark.asyncio
    @patch("scheduler.graph_cycle_scheduler.build_trading_graph")
    @patch("database.db.get_session")
    @patch("scheduler.cycle_scheduler.get_session")
    async def test_run_once_success(
        self,
        mock_cycle_get_session,
        mock_db_get_session,
        mock_build_graph,
        settings, mock_mt5, mock_fundamental, mock_per_asset
    ):
        from scheduler.graph_cycle_scheduler import GraphCycleScheduler
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.execute = AsyncMock(return_value=MagicMock())
        nested_cm = AsyncMock()
        nested_cm.__aenter__ = AsyncMock(return_value=None)
        nested_cm.__aexit__ = AsyncMock(return_value=None)
        mock_session.begin_nested = MagicMock(return_value=nested_cm)
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_cycle_get_session.return_value = mock_ctx
        mock_db_get_session.return_value = mock_ctx

        mock_graph = MagicMock()
        mock_build_graph.return_value = mock_graph

        scheduler = GraphCycleScheduler(settings, mock_mt5, mock_fundamental, mock_per_asset)
        scheduler._ensure_checkpointer_setup = AsyncMock()
        scheduler._pre_cycle_setup = AsyncMock(return_value={
            "should_skip": False,
            "effective_auto_execute": False,
            "weekend_symbols_override": None,
            "skip_reason": None,
        })
        scheduler._handle_weekend_positions = AsyncMock()
        scheduler._update_analysis_ground_truth = AsyncMock()

        async def fake_astream(state, config):
            yield {
                "data_gathering": {
                    "summary": {
                        "price_fetch": {"fetched": 200},
                        "indicators": {"XAUUSD": True},
                        "structure": {"XAUUSD": 10},
                    }
                }
            }
            yield {"fundamental_analysis": {"summary": {"fundamental": {"success": True}}}}
            yield {
                "per_asset_analysis": {
                    "summary": {"per_asset": {"XAUUSD": {"decision": "buy"}}},
                    "actionable_trades": [{"symbol": "XAUUSD"}],
                }
            }

        mock_graph.astream = fake_astream

        summary = await scheduler.run_once(forced=True)

        assert summary["price_fetch"]["fetched"] == 200
        assert summary["indicators"]["XAUUSD"] is True
        assert summary["structure"]["XAUUSD"] == 10
        assert summary["fundamental"]["success"] is True
        assert summary["per_asset"]["XAUUSD"]["decision"] == "buy"

    @pytest.mark.asyncio
    @patch("scheduler.graph_cycle_scheduler.build_trading_graph")
    @patch("database.db.get_session")
    @patch("scheduler.cycle_scheduler.get_session")
    async def test_run_once_fundamental_failure(
        self,
        mock_cycle_get_session,
        mock_db_get_session,
        mock_build_graph,
        settings, mock_mt5, mock_fundamental, mock_per_asset
    ):
        from scheduler.graph_cycle_scheduler import GraphCycleScheduler
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.execute = AsyncMock(return_value=MagicMock())
        nested_cm = AsyncMock()
        nested_cm.__aenter__ = AsyncMock(return_value=None)
        nested_cm.__aexit__ = AsyncMock(return_value=None)
        mock_session.begin_nested = MagicMock(return_value=nested_cm)
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_cycle_get_session.return_value = mock_ctx
        mock_db_get_session.return_value = mock_ctx

        mock_graph = MagicMock()
        mock_build_graph.return_value = mock_graph

        scheduler = GraphCycleScheduler(settings, mock_mt5, mock_fundamental, mock_per_asset)
        scheduler._ensure_checkpointer_setup = AsyncMock()
        scheduler._pre_cycle_setup = AsyncMock(return_value={
            "should_skip": False,
            "effective_auto_execute": False,
            "weekend_symbols_override": None,
            "skip_reason": None,
        })
        scheduler._handle_weekend_positions = AsyncMock()
        scheduler._update_analysis_ground_truth = AsyncMock()

        async def fake_astream(state, config):
            yield {
                "fundamental_analysis": {
                    "summary": {"fundamental": {"success": False}},
                    "should_pause": True,
                }
            }

        mock_graph.astream = fake_astream

        summary = await scheduler.run_once(forced=True)
        assert summary["fundamental"]["success"] is False

    @pytest.mark.asyncio
    @patch("database.db.get_session")
    @patch("scheduler.macro_data_scheduler.get_session")
    @patch("scheduler.cycle_scheduler.get_session")
    @patch("data_sources.coinglass_funding.CoinglasFundingFetcher")
    @patch("scrapers.sentiment.binance_sentiment.BinanceSentimentFetcher")
    @patch("scrapers.sentiment.myfxbook_sentiment.MyFxBookSentimentFetcher")
    @patch("scrapers.sentiment.fxssi_sentiment.FXSSISentimentFetcher")
    @patch("data_sources.fear_greed.FearGreedFetcher")
    @patch("data_sources.eia_oil_inventory.EIAInventoryFetcher")
    @patch("data_sources.vix_yfinance.VIXFetcher")
    @patch("data_sources.fred_treasury_yield.FREDDataFetcher")
    @patch("data_sources.cftc_cot.CFTCCOTFetcher")
    @patch("data_sources.dxy_yfinance.DXYFetcher")
    @patch("utils.analytics.paper_tracker.PaperTracker")
    async def test_refresh_data_sources(
        self,
        mock_paper_tracker,
        mock_dxy,
        mock_cftc,
        mock_fred,
        mock_vix,
        mock_eia,
        mock_fear,
        mock_fxssi,
        mock_myfxbook,
        mock_binance,
        mock_coinglass,
        mock_cycle_get_session,
        mock_macro_get_session,
        mock_db_get_session,
        settings
    ):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.execute = AsyncMock(return_value=MagicMock())
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_cycle_get_session.return_value = mock_ctx
        mock_macro_get_session.return_value = mock_ctx
        mock_db_get_session.return_value = mock_ctx
        
        vix_instance = mock_vix.return_value
        vix_instance.fetch = AsyncMock(return_value=5)
        
        fred_instance = mock_fred.return_value
        fred_instance.fetch_all = AsyncMock(return_value={"10Y": 1})
        
        cftc_instance = mock_cftc.return_value
        cftc_instance.fetch_all = AsyncMock(return_value=2)
        
        dxy_instance = mock_dxy.return_value
        dxy_instance.fetch = AsyncMock(side_effect=Exception("API Error"))
        
        scheduler = CycleScheduler(settings)
        res = await scheduler._refresh_data_sources()
        
        assert res["vix"]["saved"] == 5
        assert res["fred"]["10Y"] == 1
        assert res["cftc"]["saved"] == 2
        assert "error" in res["dxy"]
        assert "API Error" in res["dxy"]["error"]

    @pytest.mark.asyncio
    @patch("scheduler.graph_cycle_scheduler.build_trading_graph")
    @patch("database.db.get_session")
    @patch("scheduler.cycle_scheduler.get_session")
    async def test_run_once_data_stale(
        self,
        mock_cycle_get_session,
        mock_db_get_session,
        mock_build_graph,
        settings, mock_mt5, mock_fundamental, mock_per_asset
    ):
        from scheduler.graph_cycle_scheduler import GraphCycleScheduler
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_cycle_get_session.return_value = mock_ctx
        mock_db_get_session.return_value = mock_ctx

        mock_graph = MagicMock()
        mock_build_graph.return_value = mock_graph

        scheduler = GraphCycleScheduler(settings, mock_mt5, mock_fundamental, mock_per_asset)
        scheduler._ensure_checkpointer_setup = AsyncMock()
        scheduler._pre_cycle_setup = AsyncMock(return_value={
            "should_skip": True,
            "skip_reason": "stale_data",
            "effective_auto_execute": False,
            "weekend_symbols_override": None,
        })

        summary = await scheduler.run_once(forced=False)
        assert summary["status"] == "skipped"
        assert summary["reason"] == "stale_data"

    @pytest.mark.asyncio
    @patch("database.db.get_session")
    @patch("utils.analytics.strategy_edge_tracker.apply_disable_flags", side_effect=Exception("Strategy DB Error"))
    @patch("utils.calibration.cds_threshold_calibrator.run_calibration_if_due", return_value={"status": "calibrated", "recommendations": ["tighten"]})
    @patch("utils.analytics.adversarial_outcome_tracker.compute_adversarial_check_correlation", side_effect=ImportError("Mock import error"))
    @patch("utils.analytics.news_classification_tracker.compute_news_classification_calibration", return_value={"over_classification_suspected": False})
    @patch("utils.calibration.confidence_calibrator.apply_calibration_correction", return_value=None)
    @patch("analysis.memory.lesson_consolidator.consolidate_lessons_to_playbook", return_value=None)
    async def test_run_daily_calibrations_fault_tolerance(
        self,
        mock_consolidate,
        mock_confidence,
        mock_news,
        mock_adv,
        mock_cds,
        mock_strategy,
        mock_db_session,
        settings
    ):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_db_session.return_value = mock_ctx

        scheduler = CycleScheduler(settings)
        # Verify that an error in one calibration step (e.g. strategy error / adversarial import error)
        # does not crash _run_daily_calibrations or prevent subsequent steps from running
        await scheduler._run_daily_calibrations()

        mock_cds.assert_called_once()
        mock_news.assert_called_once()
        mock_confidence.assert_called_once()

    def test_analysis_cycle_hours_default_is_8(self):
        scheduler = CycleScheduler({})
        assert scheduler.cycle_hours == 8.0
        assert CycleScheduler._default_times_from_interval(0) == ["07:00", "15:00", "20:00"]
        assert CycleScheduler._default_times_from_interval(8.0) == ["07:00", "15:00", "20:00"]
        assert CycleScheduler._default_times_from_interval(6.0) == ["00:00", "06:00", "12:00", "18:00"]

    @pytest.mark.asyncio
    async def test_get_symbol_paper_stats_rolling_window_20(self, settings):
        scheduler = CycleScheduler(settings)
        mock_session = AsyncMock()
        mock_result = MagicMock()

        # Mock 20 records: 15 wins (tp_hit), 5 losses (sl_hit)
        from database.models import PaperTradeRecord
        records = [
            PaperTradeRecord(symbol="XAUUSD", status="closed", exit_reason="tp_hit" if i < 15 else "sl_hit")
            for i in range(20)
        ]
        mock_result.scalars.return_value.all.return_value = records
        mock_session.execute = AsyncMock(return_value=mock_result)

        stats = await scheduler._get_symbol_paper_stats(mock_session, "XAUUSD")
        assert stats["sufficient"] is True
        assert stats["trades"] == 20
        assert stats["win_rate"] == 75.0
        assert stats["blocked"] is False

        # Verify the executed SQL statement has limit 20
        stmt = mock_session.execute.call_args[0][0]
        compiled = str(stmt)
        assert "paper_trades.closed_at DESC" in compiled or "ORDER BY" in compiled.upper()
        assert "LIMIT" in compiled.upper()



