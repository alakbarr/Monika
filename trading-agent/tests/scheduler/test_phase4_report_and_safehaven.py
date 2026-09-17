import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from scheduler.cycle_scheduler import CycleScheduler
from analysis.tools.tool_executor import ToolExecutor


class TestPhase4ReportAndSafeHaven:

    @pytest.mark.asyncio
    @patch("analysis.providers.llm_factory.get_client_for_task")
    @patch("utils.infra.notifier.AgentNotifier.send_markdown")
    @patch("database.db.get_session")
    async def test_weekly_edge_assessment_synthesizer(self, mock_get_session, mock_send_markdown, mock_get_client):
        """Test that _send_weekly_edge_assessment invokes report_synthesizer LLM role."""
        mock_client = MagicMock()
        mock_client.generate_text = AsyncMock(return_value="Solid edge across macro and SMC.")
        mock_get_client.return_value = mock_client
        mock_send_markdown.return_value = True

        mock_session = AsyncMock()
        mock_get_session.return_value.__aenter__.return_value = mock_session

        settings = {
            "trading": {
                "schedule": {"analysis_cycle_hours": 8},
                "asset_universe": ["XAUUSD", "EURUSD"],
                "mt5": {"timeframes": ["H1", "H4"]}
            }
        }

        scheduler = CycleScheduler(settings=settings)
        scheduler._paper_tracker = MagicMock()
        scheduler._paper_tracker.get_statistics = AsyncMock(return_value={"win_rate_pct": 60.0, "total_trades": 15})

        with patch("utils.analytics.analysis_tracker.get_direction_accuracy_report", AsyncMock(return_value={"direction_accuracy_4h": 65.0})), \
             patch("utils.analytics.analysis_tracker.compute_factor_effectiveness", AsyncMock(return_value={"yields": {"win_rate": 70}})), \
             patch("utils.analytics.edge_tracker.compute_edge_status", AsyncMock(return_value={"status": "positive_edge", "z_score": 1.8, "ci_lower": 52, "ci_upper": 68, "action": "Scale size"})), \
             patch("utils.analytics.analysis_tracker.analyze_debate_impact", AsyncMock(return_value={"judge_alignment_pct": 75})), \
             patch("utils.protocol.coherence_flag_tracker.compute_coherence_override_impact", AsyncMock(return_value={"insufficient_data": True})), \
             patch("utils.llm.memory_compressor.compress_agent_memory", AsyncMock()), \
             patch("utils.analytics.specialist_tracker.check_specialist_model_quality", AsyncMock(return_value={"alerts": []})):

            await scheduler._send_weekly_edge_assessment()

        mock_get_client.assert_called_with("report_synthesizer", settings)
        mock_client.generate_text.assert_called_once()
        sent_text = mock_send_markdown.call_args[0][0]
        assert "Solid edge across macro and SMC." in sent_text
        assert "Executive Synthesis:" in sent_text

    @pytest.mark.asyncio
    @patch("analysis.providers.llm_factory.get_client_for_task")
    @patch("utils.infra.notifier.AgentNotifier.send_info")
    @patch("database.db.get_session")
    async def test_daily_report_synthesizer(self, mock_get_session, mock_send_info, mock_get_client):
        """Test that _send_daily_report invokes report_synthesizer LLM role."""
        mock_client = MagicMock()
        mock_client.generate_text = AsyncMock(return_value="Portfolio resilient. 0 drawdowns today.")
        mock_get_client.return_value = mock_client
        mock_send_info.return_value = True

        mock_session = AsyncMock()
        mock_exec_res = MagicMock()
        mock_exec_res.scalars.return_value.all.return_value = []
        mock_exec_res.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_exec_res)
        mock_get_session.return_value.__aenter__.return_value = mock_session

        settings = {
            "trading": {
                "schedule": {"analysis_cycle_hours": 8},
                "asset_universe": ["XAUUSD", "EURUSD"],
                "mt5": {"timeframes": ["H1", "H4"]}
            }
        }

        scheduler = CycleScheduler(settings=settings)
        scheduler._paper_tracker = MagicMock()
        scheduler._paper_tracker.get_statistics = AsyncMock(return_value={"win_rate_pct": 60.0, "total_trades": 15})

        await scheduler._send_daily_report()

        mock_get_client.assert_called_with("report_synthesizer", settings)
        mock_client.generate_text.assert_called_once()
        sent_text = mock_send_info.call_args[0][0]
        assert "Portfolio resilient. 0 drawdowns today." in sent_text
        assert "Executive Summary:" in sent_text

    @pytest.mark.asyncio
    async def test_vix_safe_haven_exemption(self):
        """Test that VIX >= 35 skips normal symbols but exempts safe-haven symbols (XAUUSD, USDJPY) with normalization."""
        from analysis.stages.per_asset_stage import PerAssetStage

        stage = PerAssetStage(settings={"trading": {"asset_universe": ["EURUSD", "XAUUSD", "USDJPY"]}})
        mock_session = AsyncMock()

        # Mock VIX row with close = 38 (exceeding 35)
        mock_vix = MagicMock()
        mock_vix.close = 38.0

        async def mock_execute_fn(query, *args, **kwargs):
            query_str = str(query).lower()
            res = MagicMock()
            if "vix" in query_str:
                res.scalar_one_or_none.return_value = mock_vix
            else:
                res.scalar_one_or_none.return_value = None
            return res

        mock_session.execute.side_effect = mock_execute_fn

        with patch("utils.calibration.prescreen_calibrator.compute_prescreen_skip_quality", AsyncMock(return_value={"local_heuristic": {"false_skip_rate_pct": 10.0}})):
            # EURUSD and EUR/USD should be skipped due to non-safe-haven pause
            should_run_eur, reason_eur = await stage._run_prescreen(session=mock_session, symbol="EURUSD")
            assert should_run_eur is False
            assert "non-safe-haven pause" in reason_eur

            should_run_eur_slash, _ = await stage._run_prescreen(session=mock_session, symbol="EUR/USD")
            assert should_run_eur_slash is False

            # XAUUSD and XAU/USD (and lowercase) are safe-haven -> proceed past VIX check
            stage._haiku_client = None
            should_run_xau, reason_xau = await stage._run_prescreen(session=mock_session, symbol="XAUUSD")
            assert should_run_xau is True

            should_run_xau_slash, _ = await stage._run_prescreen(session=mock_session, symbol="XAU/USD")
            assert should_run_xau_slash is True

            # USDJPY is safe-haven as well
            should_run_jpy, reason_jpy = await stage._run_prescreen(session=mock_session, symbol="USDJPY")
            assert should_run_jpy is True

    @pytest.mark.asyncio
    async def test_tool_executor_domain_delegation(self):
        """Test ToolExecutor falls back to domain handler for registered domain tools."""
        mock_session = AsyncMock()
        executor = ToolExecutor(session=mock_session, settings={})

        # Mock calculate_position_size on execution_handlers
        executor.execution_handlers.calculate_position_size = AsyncMock(return_value={
            "symbol": "EURUSD",
            "recommended_lots": 0.5,
            "pip_value": 10.0,
            "sl_pips": 50.0,
            "is_valid": True
        })

        # Calling calculate_position_size directly through execute()
        res = await executor.execute("calculate_position_size", {
            "symbol": "EURUSD",
            "entry_price": 1.0800,
            "stop_loss": 1.0750
        })

        assert res.get("is_valid") is True
        assert res.get("recommended_lots") == 0.5
        assert res.get("pip_value") == 10.0
        executor.execution_handlers.calculate_position_size.assert_called_once()
