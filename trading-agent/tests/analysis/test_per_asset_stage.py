import pytest
from datetime import datetime, timezone, date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from analysis.stages.per_asset_stage import PerAssetStage
from database.models import AssetAnalysis, ActivityLog

def get_test_settings():
    from config.settings import load_all_config
    s = load_all_config()
    s.setdefault("analysis", {})["enable_preflight_gate"] = False
    return s

class TestPerAssetStage:

    def test_init(self):
        settings = {
            "llm": {
                "models": {"test-model": {"provider": "anthropic"}},
                "task_roles": {
                    "stage2_per_asset_primary": {
                        "primary": "test-model",
                        "max_tokens": 1000,
                        "max_tool_turns": 10
                    }
                }
            },
            "trading": {
                "asset_universe": ["XAUUSD"],
                "parallel_asset_analysis": True
            }
        }
        stage = PerAssetStage(settings)
        assert stage.primary_client.model == "test-model"
        assert stage.primary_client.max_tokens == 1000
        assert stage.primary_client.max_tool_turns == 10
        assert stage.asset_universe == ["XAUUSD"]
        assert stage.run_parallel is True

    def test_init_defaults(self):
        stage = PerAssetStage(get_test_settings())
        assert stage.primary_client.model is not None
        assert "XAUUSD" in stage.asset_universe

    def test_build_user_message(self):
        stage = PerAssetStage(get_test_settings())
        msg = stage._build_user_message("XAUUSD")
        assert "XAUUSD" in msg
        assert "MANDATORY FIRST STEP" in msg
        
        msg2 = stage._build_user_message("BTCUSD")
        assert "BTCUSD" in msg2
        assert "SPECIAL NOTE FOR BTCUSD" in msg2

    @pytest.mark.asyncio
    @patch('analysis.calculators.adaptive_policy.AdaptiveRiskPolicy.get_effective_threshold', new_callable=AsyncMock, return_value=(7.0, 'default'))
    @patch('analysis.providers.llm_factory.FallbackClientWrapper.run_agent', new_callable=AsyncMock)
    async def test_run_one_success(self, mock_run_agent, mock_threshold):
        stage = PerAssetStage(get_test_settings())
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        stage._check_brief_freshness_and_quality = AsyncMock(return_value=(None, MagicMock(), []))
        stage._compute_ssvp_coherence = AsyncMock(return_value=None)
        stage._fetch_stage2_bundle = AsyncMock(return_value=(None, {}, False, ''))
        stage._fetch_gemini_precomputed = AsyncMock(return_value='')
        stage._check_minimum_data_quality = AsyncMock(return_value=(True, 'ok'))
        stage._verify_data_currency = AsyncMock(return_value=(True, 'ok'))
        stage._check_data_coherence_for_analysis = AsyncMock(return_value=(True, 'ok'))
        stage._run_prescreen = AsyncMock(return_value=(True, 'ok'))
        stage._execute_specialist_debate_pipeline = AsyncMock(return_value=('', {}, {}, {}))
        stage._get_symbol_sl_streak = AsyncMock(return_value=0)
        stage._run_second_opinion_check = AsyncMock(return_value={'agree': True})
        
        mock_run_agent.return_value = {
            "success": True,
            "tool_calls_made": 5,
            "turns": 2,
        }
        
        mock_result = MagicMock()
        mock_analysis = MagicMock()
        mock_analysis.id = 99
        mock_analysis.decision = "buy"
        mock_analysis.confidence = 0.9
        mock_analysis.confluence_score = 10
        mock_analysis.priced_in_score = 0
        mock_analysis.stop_loss = 1900.0
        mock_analysis.take_profit = 2100.0
        mock_analysis.entry_zone = None
        mock_analysis.entry_price = 2000.0
        mock_analysis.rationale = "good buy"
        from datetime import datetime, timezone
        mock_analysis.generated_at = datetime.now(timezone.utc)
        mock_result.scalar_one_or_none.return_value = mock_analysis
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        stage._log = AsyncMock()
        
        res = await stage.run_one(mock_session, "XAUUSD", bypass_prescreen=True)
        
        assert res["success"] is True
        assert res["symbol"] == "XAUUSD"
        assert res["analysis_id"] == 99
        assert res["decision"] == "buy"
        assert res["confidence"] == 0.9
        assert res["tool_calls_made"] == 5
        assert res["turns"] == 2
        
        assert stage._log.call_count == 1
        mock_run_agent.assert_awaited_once()

    @pytest.mark.asyncio
    @patch('analysis.calculators.adaptive_policy.AdaptiveRiskPolicy.get_effective_threshold', new_callable=AsyncMock, return_value=(7.0, 'default'))
    @patch('analysis.providers.llm_factory.FallbackClientWrapper.run_agent', new_callable=AsyncMock)
    async def test_run_one_failure(self, mock_run_agent, mock_threshold):
        stage = PerAssetStage(get_test_settings())
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        stage._check_brief_freshness_and_quality = AsyncMock(return_value=(None, MagicMock(), []))
        stage._compute_ssvp_coherence = AsyncMock(return_value=None)
        stage._fetch_stage2_bundle = AsyncMock(return_value=(None, {}, False, ''))
        stage._fetch_gemini_precomputed = AsyncMock(return_value='')
        stage._check_minimum_data_quality = AsyncMock(return_value=(True, 'ok'))
        stage._verify_data_currency = AsyncMock(return_value=(True, 'ok'))
        stage._check_data_coherence_for_analysis = AsyncMock(return_value=(True, 'ok'))
        stage._run_prescreen = AsyncMock(return_value=(True, 'ok'))
        stage._execute_specialist_debate_pipeline = AsyncMock(return_value=('', {}, {}, {}))
        
        mock_run_agent.return_value = {
            "success": False,
            "error": "API error"
        }
        
        mock_result = MagicMock()
        mock_analysis = MagicMock()
        from datetime import datetime, timezone
        mock_analysis.generated_at = datetime.now(timezone.utc)
        mock_analysis.confidence = 1.0
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        stage._log = AsyncMock()
        
        res = await stage.run_one(mock_session, "XAUUSD", bypass_prescreen=True)
        
        assert res["success"] is False
        assert "error" in res
        assert res["symbol"] == "XAUUSD"
        
        assert stage._log.call_count == 1
        args, kwargs = stage._log.call_args
        assert args[0] == mock_session
        assert "FAILED" in args[1]
        assert kwargs.get("category") == "error"


    @pytest.mark.asyncio
    @patch('utils.clock.now', return_value=datetime(2026, 8, 19, 14, 0, 0, tzinfo=timezone.utc))
    @patch('utils.api.claude_rate_limiter.ClaudeRateLimiter.acquire_session_slot', new_callable=AsyncMock)
    @patch('analysis.prefetch.stage2_prefetcher.Stage2DataBundler.fetch_bundle', new_callable=AsyncMock, return_value=("", {}))
    @patch('analysis.providers.llm_factory.FallbackClientWrapper.run_agent', new_callable=AsyncMock)
    async def test_run_one_success_no_analysis(self, mock_run_agent, mock_fetch_bundle, mock_rate_limit, mock_clock):
        settings = get_test_settings()
        if "specialist_decomposition" in settings:
            settings["specialist_decomposition"]["enabled"] = False
        stage = PerAssetStage(settings)
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        stage._fetch_gemini_precomputed = AsyncMock(return_value='')
        stage._check_minimum_data_quality = AsyncMock(return_value=(True, 'ok'))
        stage._check_data_coherence_for_analysis = AsyncMock(return_value=(True, 'ok'))
        stage._verify_data_currency = AsyncMock(return_value=(True, 'ok'))
        stage._haiku_prescreen = AsyncMock(return_value=(True, 'go'))
        stage._run_prescreen = AsyncMock(return_value=(True, 'go'))
        mock_rec = MagicMock()
        mock_rec.id = 999
        mock_rec.decision = "wait"
        mock_rec.confidence = 0.0
        stage._recover_missing_analysis = AsyncMock(return_value=mock_rec)
        
        mock_run_agent.return_value = {
            "success": True,
            "tool_calls_made": 5,
            "turns": 2,
        }
        
        mock_result = MagicMock()
        # First call gets the brief, subsequent calls get None (analysis lookup, etc.)
        # Use a large count to handle any additional DB queries from new features
        mock_brief = MagicMock()
        from datetime import datetime, timezone
        mock_brief.generated_at = datetime.now(timezone.utc)
        mock_result.scalar_one_or_none.side_effect = [mock_brief] + [None]*80
        
        # Phase 4 update: mock for adaptive threshold
        mock_first = MagicMock()
        mock_first.total_trades = 0
        mock_first.winning_trades = 0
        mock_result.first.return_value = mock_first
        
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        res = await stage.run_one(mock_session, "XAUUSD")
        
        assert res["success"] is True
        assert res["decision"] == "wait"

    @pytest.mark.asyncio
    @patch('analysis.stages.per_asset_stage.asyncio.sleep', new_callable=AsyncMock)
    async def test_run_all_parallel(self, mock_sleep):
        stage = PerAssetStage(get_test_settings())
        stage.run_parallel = True
        
        # mock context manager
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        
        mock_session_factory = MagicMock(return_value=mock_ctx)
        
        stage.run_one = AsyncMock(return_value={"success": True, "symbol": "MOCK"})
        
        res = await stage.run_all(mock_session_factory, ["XAUUSD", "EURUSD"])
        
        assert len(res) == 2
        assert "XAUUSD" in res
        assert "EURUSD" in res
        assert stage.run_one.call_count == 2

    @pytest.mark.asyncio
    @patch('analysis.stages.per_asset_stage.asyncio.sleep', new_callable=AsyncMock)
    async def test_run_all_sequential(self, mock_sleep):
        stage = PerAssetStage(get_test_settings())
        stage.run_parallel = False
        
        # mock context manager
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        
        mock_session_factory = MagicMock(return_value=mock_ctx)
        
        stage.run_one = AsyncMock(return_value={"success": True, "symbol": "MOCK"})
        
        res = await stage.run_all(mock_session_factory, ["XAUUSD", "EURUSD"])
        
        assert len(res) == 2
        assert "XAUUSD" in res
        assert "EURUSD" in res
        
        assert stage.run_one.call_count == 2
        assert mock_sleep.call_count == 2

    @pytest.mark.asyncio
    async def test_log(self):
        stage = PerAssetStage(get_test_settings())
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        
        await stage._log(mock_session, "test desc", "test cat")
        
        mock_session.add.assert_called_once()
        args, kwargs = mock_session.add.call_args
        assert isinstance(args[0], ActivityLog)
        assert args[0].description == "test desc"
        assert args[0].category == "test cat"
        
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_log_exception(self):
        stage = PerAssetStage(get_test_settings())
        mock_session = AsyncMock()
        mock_session.add = MagicMock(side_effect=Exception("DB error"))
        
        await stage._log(mock_session, "test")
        mock_session.add.assert_called_once()

    @pytest.mark.asyncio
    @patch('analysis.stages.per_asset_stage.clock.now', return_value=datetime(2026, 8, 25, 12, 0, 0, tzinfo=timezone.utc))
    @patch('utils.validation.data_validator.check_data_coherence', new_callable=AsyncMock)
    async def test_check_data_coherence_for_analysis_success(self, mock_coherence, mock_clock):
        stage = PerAssetStage(get_test_settings())
        mock_session = AsyncMock()
        mock_coherence.return_value = {'coherent': True, 'issues': []}

        # Mock ATR row
        mock_atr = MagicMock()
        mock_atr.value_json = '{"atr": 15.5}'
        mock_atr.timestamp = datetime(2026, 8, 25, 10, 0, 0, tzinfo=timezone.utc)

        # Mock VIX row (datetime object)
        mock_vix = MagicMock()
        mock_vix.date = datetime(2026, 8, 25, 0, 0, 0, tzinfo=timezone.utc)

        mock_result_atr1 = MagicMock()
        mock_result_atr1.scalar_one_or_none.return_value = mock_atr

        mock_result_atr2 = MagicMock()
        mock_result_atr2.scalar_one_or_none.return_value = mock_atr

        mock_result_vix = MagicMock()
        mock_result_vix.scalar_one_or_none.return_value = mock_vix

        mock_session.execute.side_effect = [mock_result_atr1, mock_result_atr2, mock_result_vix]

        ok, reason = await stage._check_data_coherence_for_analysis(mock_session, "XAUUSD")
        assert ok is True
        assert reason == 'ok'

    @pytest.mark.asyncio
    @patch('analysis.stages.per_asset_stage.clock.now', return_value=datetime(2026, 8, 25, 12, 0, 0, tzinfo=timezone.utc))
    @patch('utils.validation.data_validator.check_data_coherence', new_callable=AsyncMock)
    async def test_check_data_coherence_for_analysis_vix_date_object(self, mock_coherence, mock_clock):
        stage = PerAssetStage(get_test_settings())
        mock_session = AsyncMock()
        mock_coherence.return_value = {'coherent': True, 'issues': []}

        mock_atr = MagicMock()
        mock_atr.value_json = '{"atr": 15.5}'
        mock_atr.timestamp = datetime(2026, 8, 25, 10, 0, 0, tzinfo=timezone.utc)

        # Mock VIX row with datetime.date object (not datetime.datetime)
        mock_vix = MagicMock()
        mock_vix.date = date(2026, 8, 24)

        mock_result_atr1 = MagicMock()
        mock_result_atr1.scalar_one_or_none.return_value = mock_atr

        mock_result_atr2 = MagicMock()
        mock_result_atr2.scalar_one_or_none.return_value = mock_atr

        mock_result_vix = MagicMock()
        mock_result_vix.scalar_one_or_none.return_value = mock_vix

        mock_session.execute.side_effect = [mock_result_atr1, mock_result_atr2, mock_result_vix]

        ok, reason = await stage._check_data_coherence_for_analysis(mock_session, "XAUUSD")
        assert ok is True
        assert reason == 'ok'

    @pytest.mark.asyncio
    @patch('analysis.stages.per_asset_stage.clock.now', return_value=datetime(2026, 8, 25, 12, 0, 0, tzinfo=timezone.utc))
    @patch('utils.validation.data_validator.check_data_coherence', new_callable=AsyncMock)
    async def test_check_data_coherence_for_analysis_vix_stale(self, mock_coherence, mock_clock):
        stage = PerAssetStage(get_test_settings())
        mock_session = AsyncMock()
        mock_coherence.return_value = {'coherent': True, 'issues': []}

        mock_atr = MagicMock()
        mock_atr.value_json = '{"atr": 15.5}'
        mock_atr.timestamp = datetime(2026, 8, 25, 10, 0, 0, tzinfo=timezone.utc)

        # Mock VIX row 7 days old
        mock_vix = MagicMock()
        mock_vix.date = date(2026, 8, 18)

        mock_result_atr1 = MagicMock()
        mock_result_atr1.scalar_one_or_none.return_value = mock_atr

        mock_result_atr2 = MagicMock()
        mock_result_atr2.scalar_one_or_none.return_value = mock_atr

        mock_result_vix = MagicMock()
        mock_result_vix.scalar_one_or_none.return_value = mock_vix

        mock_session.execute.side_effect = [mock_result_atr1, mock_result_atr2, mock_result_vix]

        ok, reason = await stage._check_data_coherence_for_analysis(mock_session, "XAUUSD")
        assert ok is False
        assert "VIX data is 7 days old" in reason

    @pytest.mark.asyncio
    @patch('analysis.stages.per_asset_stage.clock.now', return_value=datetime(2026, 8, 25, 12, 0, 0, tzinfo=timezone.utc))
    @patch('utils.validation.data_validator.check_data_coherence', new_callable=AsyncMock)
    async def test_check_data_coherence_for_analysis_missing_vix(self, mock_coherence, mock_clock):
        stage = PerAssetStage(get_test_settings())
        mock_session = AsyncMock()
        mock_coherence.return_value = {'coherent': True, 'issues': []}

        mock_atr = MagicMock()
        mock_atr.value_json = '{"atr": 15.5}'
        mock_atr.timestamp = datetime(2026, 8, 25, 10, 0, 0, tzinfo=timezone.utc)

        mock_result_atr1 = MagicMock()
        mock_result_atr1.scalar_one_or_none.return_value = mock_atr

        mock_result_atr2 = MagicMock()
        mock_result_atr2.scalar_one_or_none.return_value = mock_atr

        mock_result_vix = MagicMock()
        mock_result_vix.scalar_one_or_none.return_value = None

        mock_session.execute.side_effect = [mock_result_atr1, mock_result_atr2, mock_result_vix]

        ok, reason = await stage._check_data_coherence_for_analysis(mock_session, "XAUUSD")
        assert ok is False
        assert "No VIX data" in reason
