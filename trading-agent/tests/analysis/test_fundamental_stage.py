import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from analysis.stages.fundamental_stage import FundamentalStage
from database.models import ActivityLog

class TestFundamentalStage:

    def test_init(self):
        settings = {
            "llm": {
                "models": {"test-model": {"provider": "anthropic"}},
                "task_roles": {
                    "stage1_fundamental": {
                        "primary": "test-model",
                        "max_tokens": 1000,
                        "max_tool_turns": 10
                    }
                }
            }
        }
        stage = FundamentalStage(settings)
        assert stage.client.model == "test-model"
        assert stage.client.max_tokens == 1000
        assert stage.client.max_tool_turns == 10

    def test_init_defaults(self):
        from config.settings import load_all_config
        settings = load_all_config()
        stage = FundamentalStage(settings)
        assert stage.client.model == settings["llm"]["task_roles"]["stage1_fundamental"]["primary"]

    @pytest.mark.asyncio
    async def test_run_success(self):
        stage = FundamentalStage({})
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        
        # mock claude client run_agent
        stage.client.run_agent = AsyncMock(return_value={
            "success": True,
            "tool_calls_made": 5,
            "turns": 2,
        })
        
        # mock DB select for FundamentalBrief
        mock_result = MagicMock()
        mock_brief = MagicMock()
        mock_brief.id = 99
        mock_brief.confidence = 0.9
        mock_result.scalar_one_or_none.return_value = mock_brief
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        # mock log
        stage._log = AsyncMock()
        
        res = await stage.run(mock_session)
        
        assert res["success"] is True
        assert res["brief_id"] == 99
        assert res["tool_calls_made"] == 5
        assert res["turns"] == 2
        assert "elapsed_seconds" in res
        
        # should log start and complete
        assert stage._log.call_count >= 2

    @pytest.mark.asyncio
    async def test_run_success_no_brief(self):
        stage = FundamentalStage({})
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        
        stage.client.run_agent = AsyncMock(return_value={
            "success": True,
            "tool_calls_made": 1,
            "turns": 1,
        })
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        res = await stage.run(mock_session)
        assert res["success"] is False
        assert res.get("brief_id") is None
        assert "brief submission missing" in res.get("error", "").lower()

    @pytest.mark.asyncio
    async def test_run_failure(self):
        stage = FundamentalStage({})
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        
        stage.client.run_agent = AsyncMock(return_value={
            "success": False,
            "error": "API error"
        })
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        stage._log = AsyncMock()
        
        res = await stage.run(mock_session)
        
        assert res["success"] is False
        assert "error" in res
        # start log and error log
        assert stage._log.call_count >= 2
        # verify error log category
        args, kwargs = stage._log.call_args
        assert args[0] == mock_session
        assert "FAILED" in args[1]
        assert kwargs.get("category") == "error"

    @pytest.mark.asyncio
    async def test_log(self):
        stage = FundamentalStage({})
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
        stage = FundamentalStage({})
        mock_session = AsyncMock()
        mock_session.add = MagicMock(side_effect=Exception("DB error"))
        
        # Should not raise exception
        await stage._log(mock_session, "test")
        mock_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_weekend_btc_only_mode_no_neutral_escalation(self):
        import json
        settings = {
            "claude": {
                "fundamental_model_escalation": "claude-opus-test",
                "fundamental_escalation_threshold": 0.5
            },
            "trading": {
                "stage1_self_consistency_enabled": False
            }
        }
        stage = FundamentalStage(settings)
        mock_session = AsyncMock()
        mock_session.add = MagicMock()

        stage.client.run_agent = AsyncMock(return_value={
            "success": True,
            "tool_calls_made": 3,
            "turns": 1,
        })

        mock_brief = MagicMock()
        mock_brief.id = 101
        mock_brief.confidence = 0.8
        # 5 neutral currencies out of 6 (typical weekend scenario)
        mock_brief.structured_json = json.dumps({
            "currency_bias": {"USD": "neutral", "EUR": "neutral", "GBP": "neutral", "JPY": "neutral", "AUD": "neutral", "BTC": "bullish"},
            "priced_in_assessment": {"priced_in_score": 5}
        })
        mock_brief.content_markdown = "Weekend brief"

        def mock_exec(stmt, *args, **kwargs):
            res = MagicMock()
            res.scalars.return_value.all.return_value = []
            stmt_str = str(stmt)
            if "fundamental_brief" in stmt_str:
                res.scalar_one_or_none.return_value = mock_brief
            else:
                res.scalar_one_or_none.return_value = None
            return res

        mock_session.execute = AsyncMock(side_effect=mock_exec)
        stage._log = AsyncMock()

        with patch("analysis.stages.fundamental_stage.get_client_for_task") as mock_get_client, \
             patch("analysis.stages.fundamental_stage.verify_fundamental_brief", AsyncMock(return_value={"internally_consistent": True, "counter_thesis_is_substantive": True})):
            mock_esc_client = MagicMock()
            mock_esc_client.run_agent = AsyncMock()
            mock_get_client.return_value = mock_esc_client

            # Run in weekend mode
            res = await stage.run(mock_session, weekend_btc_only_mode=True)

            assert res["success"] is True
            # Escalation client should NOT have been called because weekend mode skips too_many_neutral_biases
            mock_esc_client.run_agent.assert_not_called()

    @pytest.mark.asyncio
    async def test_sticky_bias_and_confidence_ceiling_injected(self):
        settings = {
            "claude": {"fundamental_max_retries": 1, "fundamental_retry_base_delay": 0},
            "trading": {"stage1_self_consistency_enabled": False}
        }
        stage = FundamentalStage(settings)
        mock_session = AsyncMock()

        stage.client.run_agent = AsyncMock(return_value={"success": True, "tool_calls_made": 1, "turns": 1})

        # Mock 4 historical briefs with USD bearish sticky across distinct 6-hour cycles
        from datetime import datetime, timedelta
        base_time = datetime(2026, 8, 25, 12, 0, 0)
        briefs = []
        for i in range(4):
            b = MagicMock()
            b.generated_at = base_time - timedelta(hours=i * 6)
            b.currency_bias = {"USD": "bearish", "JPY": "bullish"}
            b.structured_json = None
            briefs.append(b)

        mock_brief_res = MagicMock()
        mock_brief_res.id = 200
        mock_brief_res.confidence = 0.7
        mock_brief_res.structured_json = json.dumps({"currency_bias": {"USD": "bearish", "JPY": "bullish"}})
        mock_brief_res.content_markdown = "Brief"

        def mock_exec(stmt, *args, **kwargs):
            res = MagicMock()
            stmt_str = str(stmt)
            res.scalars.return_value.all.return_value = briefs
            if "fundamental_brief" in stmt_str:
                res.scalar_one_or_none.return_value = mock_brief_res
            else:
                res.scalar_one_or_none.return_value = None
            return res

        mock_session.execute = AsyncMock(side_effect=mock_exec)
        stage._log = AsyncMock()

        with patch("analysis.prefetch.stage1_prefetcher.Stage1DataBundler.prefetch_all_data", AsyncMock(return_value="{}")), \
             patch("analysis.stages.fundamental_stage.get_currency_confidence_ceiling", AsyncMock(return_value={"JPY": 0.50, "USD": 0.85})):
            res = await stage.run(mock_session)
            assert res["success"] is True
            call_kwargs = stage.client.run_agent.call_args.kwargs
            user_msg = call_kwargs["user_message"]
            assert "[STICKY BIAS CONTEXT & ANCHORING REQUIREMENT]" in user_msg
            assert "USD: 'bearish' (held for 4+ consecutive cycles)" in user_msg
            assert "[CURRENCY CONFIDENCE CEILINGS (Historical Accuracy Bounds)]" in user_msg
            assert "JPY: max 0.50" in user_msg

    @pytest.mark.asyncio
    async def test_run_escalation_triggered_success(self):
        from contextlib import asynccontextmanager
        settings = {
            "claude": {
                "fundamental_model_escalation": "claude-opus-test",
                "fundamental_escalation_threshold": 0.75,
                "fundamental_max_retries": 1,
            },
            "trading": {
                "stage1_self_consistency_enabled": False
            }
        }
        stage = FundamentalStage(settings)
        mock_session = AsyncMock()

        # Initial client run
        stage.client.run_agent = AsyncMock(return_value={"success": True, "tool_calls_made": 2, "turns": 1})

        initial_brief = MagicMock()
        initial_brief.id = 101
        initial_brief.confidence = 0.65
        initial_brief.structured_json = json.dumps({"currency_bias": {"USD": "bullish", "EUR": "bearish"}})
        initial_brief.content_markdown = "Initial brief markdown"

        escalated_brief = MagicMock()
        escalated_brief.id = 102
        escalated_brief.confidence = 0.90
        escalated_brief.structured_json = json.dumps({"currency_bias": {"USD": "bullish", "EUR": "bearish"}})
        escalated_brief.content_markdown = "Escalated brief markdown"

        is_escalated_call = False

        def mock_exec(stmt, *args, **kwargs):
            nonlocal is_escalated_call
            res = MagicMock()
            res.scalars.return_value.all.return_value = []
            stmt_str = str(stmt)
            if "fundamental_brief" in stmt_str:
                if is_escalated_call:
                    res.scalar_one_or_none.return_value = escalated_brief
                else:
                    res.scalar_one_or_none.return_value = initial_brief
            else:
                res.scalar_one_or_none.return_value = None
            return res

        mock_session.execute = AsyncMock(side_effect=mock_exec)
        mock_session.delete = AsyncMock()
        stage._log = AsyncMock()

        @asynccontextmanager
        async def mock_get_session():
            s = AsyncMock()
            s.execute = AsyncMock(side_effect=mock_exec)
            yield s

        mock_esc_client = MagicMock()
        async def mock_esc_run(*args, **kwargs):
            nonlocal is_escalated_call
            is_escalated_call = True
            return {"success": True, "tool_calls_made": 3, "turns": 1}
        mock_esc_client.run_agent = AsyncMock(side_effect=mock_esc_run)

        mock_cross_client = MagicMock()
        mock_cross_client.classify_json = AsyncMock(return_value={"currency_bias": {"USD": "bullish", "EUR": "bearish"}})

        with patch("analysis.stages.fundamental_stage.get_client_for_task", return_value=mock_esc_client) as mock_get_client, \
             patch("analysis.stages.fundamental_stage.create_client", return_value=mock_cross_client), \
             patch("analysis.stages.fundamental_stage.get_session", mock_get_session), \
             patch("utils.analytics.cost_tracker.CostTracker.is_budget_paused", AsyncMock(return_value=False)), \
             patch("analysis.prefetch.stage1_prefetcher.Stage1DataBundler.prefetch_all_data", AsyncMock(return_value="{}")), \
             patch("analysis.stages.fundamental_stage.verify_fundamental_brief", AsyncMock(return_value={"internally_consistent": True, "counter_thesis_is_substantive": True})):
            
            res = await stage.run(mock_session)
            
            assert res["success"] is True
            assert res["brief_id"] == 102
            mock_get_client.assert_any_call("stage1_escalation", settings)
            mock_esc_client.run_agent.assert_awaited_once()
            # Verify pre-escalation draft brief was deleted
            mock_session.delete.assert_awaited_once_with(initial_brief)

    @pytest.mark.asyncio
    async def test_run_shadow_self_consistency_in_memory_no_db_write(self):
        """Test that self-consistency shadow check uses classify_json and does not write new rows to DB."""
        settings = {
            "trading": {
                "stage1_self_consistency_enabled": True
            }
        }
        stage = FundamentalStage(settings)
        mock_session = AsyncMock()
        mock_session.add = MagicMock()

        stage.client.run_agent = AsyncMock(return_value={"success": True, "tool_calls_made": 2, "turns": 1})

        brief = MagicMock()
        brief.id = 301
        brief.confidence = 0.55  # Below 0.60 -> triggers shadow check
        brief.macro_narrative = "Brief narrative"
        brief.structured_json = json.dumps({"currency_bias": {"USD": "bearish", "EUR": "bullish"}})

        def mock_exec(stmt, *args, **kwargs):
            res = MagicMock()
            res.scalars.return_value.all.return_value = []
            stmt_str = str(stmt)
            if "fundamental_brief" in stmt_str:
                res.scalar_one_or_none.return_value = brief
            else:
                res.scalar_one_or_none.return_value = None
            return res

        mock_session.execute = AsyncMock(side_effect=mock_exec)
        stage._log = AsyncMock()

        mock_shadow_client = MagicMock()
        # Disagrees on USD and EUR (diff_count >= 2)
        mock_shadow_client.classify_json = AsyncMock(return_value={
            "currency_bias": {"USD": "bullish", "EUR": "bearish"},
            "confidence": 0.60
        })

        with patch("analysis.stages.fundamental_stage.get_client_for_task", return_value=mock_shadow_client) as mock_get_client, \
             patch("analysis.prefetch.stage1_prefetcher.Stage1DataBundler.prefetch_all_data", AsyncMock(return_value="{}")), \
             patch("analysis.stages.fundamental_stage.verify_fundamental_brief", AsyncMock(return_value={"internally_consistent": True, "counter_thesis_is_substantive": True})):
            
            res = await stage.run(mock_session)
            
            assert res["success"] is True
            assert res["brief_id"] == 301
            # Verify classify_json was called for shadow check (in-memory)
            mock_shadow_client.classify_json.assert_awaited_once()
            # Verify confidence stayed at min(0.55, 0.60) = 0.55
            assert brief.confidence == 0.55
            assert "[SELF-CONSISTENCY NOTE]" in json.loads(brief.structured_json).get("macro_narrative", "")

    @pytest.mark.asyncio
    async def test_run_escalation_budget_paused_skips(self):
        from contextlib import asynccontextmanager
        settings = {
            "claude": {
                "fundamental_model_escalation": "claude-opus-test",
                "fundamental_escalation_threshold": 0.75,
                "fundamental_max_retries": 1,
            },
            "trading": {
                "stage1_self_consistency_enabled": False
            }
        }
        stage = FundamentalStage(settings)
        mock_session = AsyncMock()

        stage.client.run_agent = AsyncMock(return_value={"success": True, "tool_calls_made": 2, "turns": 1})

        initial_brief = MagicMock()
        initial_brief.id = 101
        initial_brief.confidence = 0.50
        initial_brief.structured_json = json.dumps({"currency_bias": {"USD": "bullish"}})
        initial_brief.content_markdown = "Initial brief"

        def mock_exec(stmt, *args, **kwargs):
            res = MagicMock()
            res.scalars.return_value.all.return_value = []
            stmt_str = str(stmt)
            if "fundamental_brief" in stmt_str:
                res.scalar_one_or_none.return_value = initial_brief
            else:
                res.scalar_one_or_none.return_value = None
            return res

        mock_session.execute = AsyncMock(side_effect=mock_exec)
        stage._log = AsyncMock()

        @asynccontextmanager
        async def mock_get_session():
            s = AsyncMock()
            s.execute = AsyncMock(side_effect=mock_exec)
            yield s

        mock_esc_client = MagicMock()
        mock_esc_client.run_agent = AsyncMock()

        with patch("analysis.stages.fundamental_stage.get_client_for_task", return_value=mock_esc_client) as mock_get_client, \
             patch("analysis.stages.fundamental_stage.get_session", mock_get_session), \
             patch("utils.analytics.cost_tracker.CostTracker.is_budget_paused", AsyncMock(return_value=True)), \
             patch("analysis.prefetch.stage1_prefetcher.Stage1DataBundler.prefetch_all_data", AsyncMock(return_value="{}")), \
             patch("analysis.validators.fundamental_verifier.verify_fundamental_brief", AsyncMock(return_value={"internally_consistent": True, "counter_thesis_is_substantive": True})):
            
            res = await stage.run(mock_session)
            
            assert res["success"] is True
            assert res["brief_id"] == 101
            mock_esc_client.run_agent.assert_not_called()

    @pytest.mark.asyncio
    async def test_quality_flag_unbound_fix_confidence_floor_applied(self):
        """Verify _quality_flag is bound when self-consistency is disabled, flooring low confidence to 0.50."""
        settings = {
            "trading": {
                "stage1_self_consistency_enabled": False
            }
        }
        stage = FundamentalStage(settings)
        mock_session = AsyncMock()

        stage.client.run_agent = AsyncMock(return_value={"success": True, "tool_calls_made": 1, "turns": 1})
        stage._log = AsyncMock()

        brief = MagicMock()
        brief.id = 202
        brief.confidence = 0.35  # Below MINIMUM_USABLE_CONFIDENCE (0.50)
        brief.structured_json = json.dumps({"currency_bias": {"USD": "neutral"}})

        def mock_exec(stmt, *args, **kwargs):
            res = MagicMock()
            res.scalars.return_value.all.return_value = []
            stmt_str = str(stmt)
            if "fundamental_brief" in stmt_str:
                res.scalar_one_or_none.return_value = brief
            else:
                res.scalar_one_or_none.return_value = None
            return res

        mock_session.execute = AsyncMock(side_effect=mock_exec)

        with patch("analysis.prefetch.stage1_prefetcher.Stage1DataBundler.prefetch_all_data", AsyncMock(return_value="{}")), \
             patch.object(stage, "_run_macro_debate", AsyncMock(return_value={})):
            res = await stage.run(mock_session)

            assert res["success"] is True
            # Floored to 0.50 because data was not degraded (_quality_flag is False)
            assert brief.confidence == 0.50

    @pytest.mark.asyncio
    async def test_quality_flag_degraded_data_no_confidence_floor(self):
        """Verify _quality_flag is True when _data_quality_degraded is set, preventing confidence floor."""
        settings = {
            "trading": {
                "stage1_self_consistency_enabled": False
            }
        }
        stage = FundamentalStage(settings)
        mock_session = AsyncMock()

        stage.client.run_agent = AsyncMock(return_value={"success": True, "tool_calls_made": 1, "turns": 1})
        stage._log = AsyncMock()

        brief = MagicMock()
        brief.id = 203
        brief.confidence = 0.35  # Below MINIMUM_USABLE_CONFIDENCE (0.50)
        # Data quality degraded is set
        brief.structured_json = json.dumps({"currency_bias": {"USD": "neutral"}, "_data_quality_degraded": True})

        def mock_exec(stmt, *args, **kwargs):
            res = MagicMock()
            res.scalars.return_value.all.return_value = []
            stmt_str = str(stmt)
            if "fundamental_brief" in stmt_str:
                res.scalar_one_or_none.return_value = brief
            else:
                res.scalar_one_or_none.return_value = None
            return res

        mock_session.execute = AsyncMock(side_effect=mock_exec)

        with patch("analysis.prefetch.stage1_prefetcher.Stage1DataBundler.prefetch_all_data", AsyncMock(return_value="{}")), \
             patch.object(stage, "_run_macro_debate", AsyncMock(return_value={})):
            res = await stage.run(mock_session)

            assert res["success"] is True
            # Confidence stays 0.35 because data was degraded (_quality_flag is True)
            assert brief.confidence == 0.35



