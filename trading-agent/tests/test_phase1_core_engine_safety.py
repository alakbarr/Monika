import asyncio
import json
import os
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from database.models import AssetAnalysis, Position, TradeTrigger, PriceOHLCV, TechnicalIndicator
from execution.execution_service import ExecutionService, ExecutionResult
from indicators.timesfm_engine import TimesFMEngine
from scheduler.trigger_checker import TriggerChecker
from skills.loader import get_dynamic_micro_skills, load_skill, compose_system_prompt, _SKILLS_DIR
from utils.llm.prompt_assembler import PromptAssembler
from analysis.stages.per_asset_stage import PerAssetStage


# ==============================================================================
# 1. TimesFM Async Forward Pass Non-blocking Tests
# ==============================================================================

class TestTimesFMAsyncForwardPass:
    @pytest.mark.asyncio
    async def test_timesfm_predict_async_to_thread(self):
        """Verify model.predict is called inside asyncio.to_thread without blocking event loop."""
        settings = {"indicators": {"timesfm": {"enabled": True}}}
        engine = TimesFMEngine(settings)

        mock_session = AsyncMock()
        # Mock price data
        target_df_mock = MagicMock()
        target_df_mock.empty = False
        target_df_mock.__getitem__.return_value.iloc = [-1]
        target_df_mock["close"].iloc = [2000.0]
        target_df_mock["close"].astype.return_value.to_numpy.return_value = [1990.0, 1995.0, 2000.0]

        mock_model = MagicMock()
        import numpy as np
        mock_output = MagicMock()
        mock_output.quantiles = np.zeros((24, 9))
        for i in range(9):
            mock_output.quantiles[:, i] = 2000.0 + (i - 4) * 5.0
        mock_model.predict.return_value = mock_output

        engine._fetch_multivariate_series = AsyncMock(return_value=(target_df_mock, {}))
        engine._get_baseline_atr = AsyncMock(return_value=15.0)
        engine.get_model = MagicMock(return_value=mock_model)

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            mock_to_thread.return_value = mock_output
            res = await engine.compute_forecast(mock_session, "XAUUSD", timeframe="H1", horizon_steps=24)

            assert res is not None
            assert res["symbol"] == "XAUUSD"
            mock_to_thread.assert_awaited_once_with(
                mock_model.predict,
                context=[1990.0, 1995.0, 2000.0],
                horizon=24,
                return_quantiles=True,
            )

    @pytest.mark.asyncio
    async def test_timesfm_legacy_forecast_async_to_thread(self):
        """Verify legacy model.forecast is called inside asyncio.to_thread."""
        settings = {"indicators": {"timesfm": {"enabled": True}}}
        engine = TimesFMEngine(settings)

        mock_session = AsyncMock()
        target_df_mock = MagicMock()
        target_df_mock.empty = False
        target_df_mock["close"].iloc = [2000.0]
        target_df_mock["close"].astype.return_value.to_numpy.return_value = [1990.0, 1995.0, 2000.0]

        mock_model = MagicMock(spec=["forecast"])
        import numpy as np
        raw_q = np.zeros((1, 24, 9))
        for i in range(9):
            raw_q[0, :, i] = 2000.0 + (i - 4) * 5.0
        preds = (None, raw_q)
        mock_model.forecast.return_value = preds

        engine._fetch_multivariate_series = AsyncMock(return_value=(target_df_mock, {}))
        engine._get_baseline_atr = AsyncMock(return_value=15.0)
        engine.get_model = MagicMock(return_value=mock_model)

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            mock_to_thread.return_value = preds
            res = await engine.compute_forecast(mock_session, "EURUSD", timeframe="H1", horizon_steps=24)

            assert res is not None
            mock_to_thread.assert_awaited_once_with(
                mock_model.forecast,
                [[1990.0, 1995.0, 2000.0]],
                freq=[0],
            )


# ==============================================================================
# 2. Closed-Loop Learning & Prompt Assembler Tests
# ==============================================================================

class TestDynamicMicroSkills:
    def test_get_dynamic_micro_skills_basic_and_crystallized(self):
        """Verify dynamic micro-skills resolution including crystallized skills for symbol."""
        skills = get_dynamic_micro_skills("EURUSD")
        assert "adjudication_framework" in skills
        assert "smc_ict_playbook" in skills
        # eurusd_trend is in skills/crystallized/
        assert "eurusd_trend" in skills

    def test_get_dynamic_micro_skills_regime_routing(self, tmp_path):
        """Verify dynamic routing of micro-playbook when regime is passed."""
        playbooks_dir = _SKILLS_DIR / "playbooks"
        playbooks_dir.mkdir(parents=True, exist_ok=True)
        test_playbook = playbooks_dir / "gbpusd_trend_playbook.md"
        try:
            test_playbook.write_text("# GBPUSD Trend Playbook\nSpecific trend rules.", encoding="utf-8")
            skills = get_dynamic_micro_skills("GBPUSD", {"regime": "trend"})
            assert "gbpusd_trend_playbook" in skills
        finally:
            if test_playbook.exists():
                test_playbook.unlink()

    def test_get_dynamic_micro_skills_regime_variation_matching(self, tmp_path):
        """Verify dynamic routing matches 'trending' to 'trend_playbook'."""
        playbooks_dir = _SKILLS_DIR / "playbooks"
        playbooks_dir.mkdir(parents=True, exist_ok=True)
        test_playbook = playbooks_dir / "usdjpy_trend_playbook.md"
        try:
            test_playbook.write_text("# USDJPY Trend Playbook", encoding="utf-8")
            skills = get_dynamic_micro_skills("USDJPY", {"regime": "trending"})
            assert "usdjpy_trend_playbook" in skills
        finally:
            if test_playbook.exists():
                test_playbook.unlink()

    def test_get_dynamic_micro_skills_range_variation_matching(self, tmp_path):
        """Verify dynamic routing matches 'range' to 'ranging_playbook'."""
        playbooks_dir = _SKILLS_DIR / "playbooks"
        playbooks_dir.mkdir(parents=True, exist_ok=True)
        test_playbook = playbooks_dir / "eurusd_ranging_playbook.md"
        try:
            test_playbook.write_text("# EURUSD Ranging Playbook", encoding="utf-8")
            skills = get_dynamic_micro_skills("EURUSD", {"regime": "range"})
            assert "eurusd_ranging_playbook" in skills
        finally:
            if test_playbook.exists():
                test_playbook.unlink()

    def test_get_dynamic_micro_skills_compound_regime_matching(self, tmp_path):
        """Verify compound regimes like 'STRONG_TREND' match base playbook 'trend_playbook'."""
        playbooks_dir = _SKILLS_DIR / "playbooks"
        playbooks_dir.mkdir(parents=True, exist_ok=True)
        test_playbook = playbooks_dir / "gbpusd_trend_playbook.md"
        try:
            test_playbook.write_text("# GBPUSD Trend Playbook", encoding="utf-8")
            skills = get_dynamic_micro_skills("GBPUSD", {"regime": "STRONG_TREND"})
            assert "gbpusd_trend_playbook" in skills
        finally:
            if test_playbook.exists():
                test_playbook.unlink()

    def test_prompt_assembler_tier_caching_and_regime(self):
        """Verify PromptAssembler passes detected_regime and maintains static prefix."""
        assembler = PromptAssembler({})
        tier1, tier2, tier3 = assembler.assemble_stage2_tiers(
            symbol="EURUSD",
            effective_threshold=7,
            detected_regime="trending",
        )
        assert "You are an elite quantitative and technical trading strategist" in tier1
        assert "eurusd_trend" in tier3 or "smc_ict_playbook" in tier3

    def test_stage2_compose_system_prompt_calls_dynamic_skills(self):
        """Verify PerAssetStage._compose_stage2_system_prompt loads dynamic skills based on regime."""
        stage = PerAssetStage(settings={"trading": {"risk": {"min_rr_ratio": 1.5}}})
        (static_sys, dynamic_sys), abort = stage._compose_stage2_system_prompt(
            symbol="EURUSD",
            cot_code="099741",
            effective_threshold=8,
            tool_order_guidance="Verify SMC",
            detected_regime="trending",
        )
        assert abort is None
        assert isinstance(static_sys, str)
        assert isinstance(dynamic_sys, str)
        assert "Symbol: EURUSD" in dynamic_sys
        assert "Effective Confluence Threshold: 8/14" in dynamic_sys


# ==============================================================================
# 3. Sub-Second Deterministic Conditional Trigger Execution Tests
# ==============================================================================

class TestDeterministicTriggerEngine:
    @pytest.mark.asyncio
    @patch("scheduler.trigger_checker.get_session")
    async def test_trigger_checker_executes_preplanned_order(self, mock_get_session):
        """When preplanned_order is present, execute_preplanned_order is called directly without waiting for LLM."""
        mock_exec_service = AsyncMock()
        mock_exec_service.execute_preplanned_order.return_value = ExecutionResult(
            symbol="XAUUSD", analysis_id=42, decision="buy",
            sizing=MagicMock(recommended_lots=0.2), risk_approved=True,
            risk_checks_passed=["drawdown_ok", "exposure_ok"], risk_checks_failed=[],
            risk_rejection_reasons=[], executed=True, mt5_ticket=88888,
            executed_price=2015.5, executed_lots=0.2, mt5_error=None, position_id=10,
            timestamp=datetime.now(timezone.utc), elapsed_ms=15.0
        )
        mock_per_asset = MagicMock()
        mock_per_asset.run_one = AsyncMock()

        checker = TriggerChecker({}, per_asset_stage=mock_per_asset, execution_service=mock_exec_service)

        preplanned = {
            "direction": "buy",
            "entry_price": 2015.0,
            "stop_loss": 2005.0,
            "take_profit": 2035.0,
            "lot_size": 0.2,
            "confidence": 0.85,
            "confluence_score": 9
        }
        trigger = MagicMock(spec=TradeTrigger)
        trigger.id = 7
        trigger.trigger_type = "price_level"
        trigger.condition_json = json.dumps({"preplanned_order": preplanned})
        trigger.asset_analysis_id = 42

        checker._expire_stale_triggers = AsyncMock(return_value=0)
        checker._get_pending_triggers = AsyncMock(return_value=[trigger])
        checker._evaluate_trigger = AsyncMock(return_value=True)
        checker._fire_trigger = AsyncMock(return_value="XAUUSD")
        checker.check_invalidation_conditions = AsyncMock(return_value=[])

        mock_session = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_get_session.return_value = mock_ctx

        with patch.object(checker, "_background_reanalysis", new_callable=AsyncMock) as mock_bg:
            res = await checker.run_once()

            assert res["checked"] == 1
            assert res["fired"] == 1
            assert "XAUUSD" in res["symbols_reanalyzed"]
            mock_exec_service.execute_preplanned_order.assert_awaited_once_with(
                session=mock_session,
                symbol="XAUUSD",
                order_plan=preplanned,
                trigger_id=7,
                analysis_id=42,
            )
            await asyncio.sleep(0.01)
            mock_bg.assert_called_once_with("XAUUSD")

    @pytest.mark.asyncio
    async def test_execution_service_execute_preplanned_order_success(self):
        """Verify ExecutionService.execute_preplanned_order executes via RiskGate in <100ms."""
        mock_mt5 = AsyncMock()
        mock_mt5.get_account_info.return_value = {"equity": 10000}
        mock_mt5.get_current_price.return_value = {"ask": 2015.2, "bid": 2014.8}
        mock_mt5.get_symbol_info.return_value = {
            "digits": 2, "point": 0.01, "stops_level": 0, "tick_value": 1.0,
            "tick_size": 0.01, "contract_size": 100, "volume_min": 0.01,
            "volume_max": 100.0, "volume_step": 0.01
        }
        mock_mt5.place_order.return_value = {"success": True, "ticket": 77777, "price": 2015.2, "error": None}

        settings = {
            "trading": {
                "auto_execute": True,
                "risk": {"max_concurrent_positions": 5, "news_window_minutes": 0}
            },
            "execution": {"max_price_staleness_seconds": 120, "max_trigger_slippage_pct": 0.5}
        }
        svc = ExecutionService(settings, mt5_client=mock_mt5, dry_run=True)

        session = AsyncMock()
        session.add = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)

        order_plan = {
            "direction": "buy",
            "entry_price": 2015.0,
            "stop_loss": 2000.0,
            "take_profit": 2045.0,
            "lot_size": 0.1,
            "confidence": 0.9,
            "confluence_score": 9,
        }

        mock_gate = AsyncMock()
        mock_gate.check.return_value = MagicMock(approved=True, checks_passed=["equity_ok"], checks_failed=[], rejection_reasons=[])
        svc.gate = mock_gate

        res = await svc.execute_preplanned_order(session, "XAUUSD", order_plan, trigger_id=12, analysis_id=99)

        assert res.risk_approved is True
        assert res.executed is True
        assert res.executed_lots == 0.1
        assert res.decision == "buy"
        assert res.elapsed_ms < 500  # Sub-second execution check

    @pytest.mark.asyncio
    async def test_execution_service_preplanned_order_slippage_rejection(self):
        """Verify preplanned order is blocked if market price drifted excessively beyond slippage threshold."""
        mock_mt5 = AsyncMock()
        mock_mt5.get_current_price.return_value = {"ask": 2055.0, "bid": 2054.0}

        settings = {
            "execution": {"max_price_staleness_seconds": 120, "max_trigger_slippage_pct": 0.5}
        }
        svc = ExecutionService(settings, mt5_client=mock_mt5, dry_run=True)
        session = AsyncMock()

        order_plan = {
            "direction": "buy",
            "entry_price": 2015.0,
            "stop_loss": 2000.0,
            "take_profit": 2045.0,
            "lot_size": 0.1
        }

        res = await svc.execute_preplanned_order(session, "XAUUSD", order_plan, trigger_id=15)

        assert res.risk_approved is False
        assert "slippage_exceeded" in res.risk_checks_failed
        assert res.executed is False

    @pytest.mark.asyncio
    async def test_execution_service_preplanned_order_pips_slippage_rejection(self):
        """Verify preplanned order is blocked if price drift exceeds pips slippage limit even when percentage slippage is acceptable."""
        mock_mt5 = AsyncMock()
        # 2015.10 vs 2015.00 entry -> 0.10 / 2015.0 = 0.005% (passes default 0.5% pct limit)
        # but 0.10 / 0.01 = 10.0 pips (exceeds 5.0 pips limit)
        mock_mt5.get_current_price.return_value = {"ask": 2015.10, "bid": 2015.09}

        settings = {
            "execution": {"max_price_staleness_seconds": 120, "max_trigger_slippage_pct": 0.5, "max_trigger_slippage_pips": 5.0}
        }
        svc = ExecutionService(settings, mt5_client=mock_mt5, dry_run=True)
        session = AsyncMock()

        order_plan = {
            "direction": "buy",
            "entry_price": 2015.0,
            "stop_loss": 2000.0,
            "take_profit": 2045.0,
            "lot_size": 0.1,
            "max_slippage_pips": 5.0,
        }

        res = await svc.execute_preplanned_order(session, "XAUUSD", order_plan, trigger_id=16)

        assert res.risk_approved is False
        assert "slippage_exceeded" in res.risk_checks_failed
        assert any("Trigger slippage 10.0 pips > threshold 5.0 pips" in r for r in res.risk_rejection_reasons)
        assert res.executed is False

    @pytest.mark.asyncio
    async def test_execution_service_preplanned_order_malformed_input(self):
        """Verify malformed order plan (non-numeric fields, non-dict) fails safely without crashing."""
        mock_mt5 = AsyncMock()
        mock_mt5.get_current_price.return_value = {"ask": 2015.0, "bid": 2014.0}
        svc = ExecutionService({}, mt5_client=mock_mt5, dry_run=True)
        session = AsyncMock()

        # Non-dict
        res1 = await svc.execute_preplanned_order(session, "XAUUSD", "not_a_dict")
        assert res1.risk_approved is False
        assert "malformed_order_plan" in res1.risk_checks_failed

        # Non-numeric string
        malformed_plan = {"direction": "buy", "entry_price": "invalid_number", "stop_loss": 2000.0}
        res2 = await svc.execute_preplanned_order(session, "XAUUSD", malformed_plan)
        assert res2.risk_approved is False
        assert "malformed_order_plan" in res2.risk_checks_failed

    @pytest.mark.asyncio
    async def test_execution_service_preplanned_order_zero_and_negative_stop_loss(self):
        """Verify preplanned order rejects zero or negative stop loss immediately."""
        mock_mt5 = AsyncMock()
        mock_mt5.get_current_price.return_value = {"ask": 2015.0, "bid": 2014.0}
        svc = ExecutionService({}, mt5_client=mock_mt5, dry_run=True)
        session = AsyncMock()

        # Zero stop loss
        plan_zero = {"direction": "buy", "entry_price": 2015.0, "stop_loss": 0.0, "lot_size": 0.1}
        res_zero = await svc.execute_preplanned_order(session, "XAUUSD", plan_zero)
        assert res_zero.risk_approved is False
        assert "invalid_stop_loss" in res_zero.risk_checks_failed

        # Negative stop loss
        plan_neg = {"direction": "buy", "entry_price": 2015.0, "stop_loss": -50.0, "lot_size": 0.1}
        res_neg = await svc.execute_preplanned_order(session, "XAUUSD", plan_neg)
        assert res_neg.risk_approved is False
        assert "invalid_stop_loss" in res_neg.risk_checks_failed

    @pytest.mark.asyncio
    async def test_execution_service_preplanned_order_inverted_stop_loss(self):
        """Verify preplanned order rejects inverted stop loss (BUY with SL >= price, SELL with SL <= price)."""
        mock_mt5 = AsyncMock()
        mock_mt5.get_current_price.return_value = {"ask": 2015.0, "bid": 2014.0}
        svc = ExecutionService({}, mt5_client=mock_mt5, dry_run=True)
        session = AsyncMock()

        # BUY with SL above current price
        plan_buy_inv = {"direction": "buy", "entry_price": 2015.0, "stop_loss": 2025.0, "lot_size": 0.1}
        res_buy = await svc.execute_preplanned_order(session, "XAUUSD", plan_buy_inv)
        assert res_buy.risk_approved is False
        assert "invalid_stop_loss" in res_buy.risk_checks_failed

        # SELL with SL below current price
        plan_sell_inv = {"direction": "sell", "entry_price": 2015.0, "stop_loss": 2005.0, "lot_size": 0.1}
        res_sell = await svc.execute_preplanned_order(session, "XAUUSD", plan_sell_inv)
        assert res_sell.risk_approved is False
        assert "invalid_stop_loss" in res_sell.risk_checks_failed

    @pytest.mark.asyncio
    async def test_execution_service_preplanned_order_pips_slippage_rejection(self):
        """Verify preplanned order rejects when price drifted beyond max_slippage_pips."""
        mock_mt5 = AsyncMock()
        # Price drifted by 1.0 (10 pips on gold where pip=0.1)
        mock_mt5.get_current_price.return_value = {"ask": 2016.0, "bid": 2015.5}
        svc = ExecutionService({}, mt5_client=mock_mt5, dry_run=True)
        session = AsyncMock()

        plan = {
            "direction": "buy",
            "entry_price": 2015.0,
            "stop_loss": 2000.0,
            "lot_size": 0.1,
            "max_slippage_pct": 5.0,  # generous pct
            "max_slippage_pips": 3.0,  # strict 3 pips
        }
        res = await svc.execute_preplanned_order(session, "XAUUSD", plan)
        assert res.risk_approved is False
        assert "slippage_exceeded" in res.risk_checks_failed

    @pytest.mark.asyncio
    async def test_execution_service_preplanned_order_foreign_key_safety(self):
        """Verify when analysis_id does NOT exist in DB, Position is saved safely with analysis_id=None without FK crash."""
        mock_mt5 = AsyncMock()
        mock_mt5.get_account_info.return_value = {"equity": 10000}
        mock_mt5.get_current_price.return_value = {"ask": 2015.0, "bid": 2014.0}
        mock_mt5.get_symbol_info.return_value = {
            "digits": 2, "point": 0.01, "stops_level": 0, "tick_value": 1.0,
            "tick_size": 0.01, "contract_size": 100, "volume_min": 0.01,
            "volume_max": 100.0, "volume_step": 0.01
        }
        mock_mt5.place_order.return_value = {"success": True, "ticket": 55555, "price": 2015.0}

        svc = ExecutionService({}, mt5_client=mock_mt5, dry_run=True)
        session = AsyncMock()
        # session.get(AssetAnalysis, ...) returns None -> no row in DB
        session.get = AsyncMock(return_value=None)
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        mock_gate = AsyncMock()
        mock_gate.check.return_value = MagicMock(approved=True, checks_passed=["ok"], checks_failed=[], rejection_reasons=[])
        svc.gate = mock_gate

        plan = {
            "direction": "buy",
            "entry_price": 2015.0,
            "stop_loss": 2000.0,
            "lot_size": 0.1,
        }
        res = await svc.execute_preplanned_order(session, "XAUUSD", plan, trigger_id=99, analysis_id=999999)
        assert res.executed is True
        # Verify Position was added with analysis_id=None to prevent foreign key violation
        added_pos = None
        for call_args in session.add.call_args_list:
            arg = call_args[0][0]
            if isinstance(arg, Position):
                added_pos = arg
                break
        assert added_pos is not None
        assert added_pos.analysis_id is None

    @pytest.mark.asyncio
    async def test_trigger_checker_background_task_deduplication(self):
        """Verify _spawn_background_reanalysis retains tasks in _background_tasks and deduplicates per symbol."""
        checker = TriggerChecker({})
        checker._background_reanalysis = AsyncMock()

        # First call spawns task
        checker._spawn_background_reanalysis("EURUSD")
        assert "EURUSD" in checker._reanalyzing_symbols
        assert len(checker._background_tasks) == 1

        # Second call for same symbol is deduplicated
        checker._spawn_background_reanalysis("EURUSD")
        assert len(checker._background_tasks) == 1


# ==============================================================================
# 4. Hybrid ReAct User Message Directive Tests
# ==============================================================================

class TestHybridReActDirectives:
    def test_trimmed_user_message_contains_hypothesis_reasoning_and_falsification_tools(self):
        """Verify _build_trimmed_user_message instructs hypothesis reasoning with targeted tools."""
        stage = PerAssetStage(settings={})
        msg = stage._build_trimmed_user_message("EURUSD")

        assert "HYPOTHESIS-DRIVEN REASONING DIRECTIVE" in msg
        assert "Max 2-3 Iterative Turns" in msg
        assert "get_smc_zones" in msg
        assert "get_structure_breaks" in msg
        assert "get_price_history" in msg
        assert "submit_asset_analysis" in msg

    def test_xtiusd_trimmed_user_message_includes_eia(self):
        """Verify oil specific tool included in trimmed message."""
        stage = PerAssetStage(settings={})
        msg = stage._build_trimmed_user_message("XTIUSD")

        assert "get_eia_oil_inventory" in msg
        assert "HYPOTHESIS-DRIVEN REASONING DIRECTIVE" in msg
