import pytest
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock
from analysis.stages.per_asset_stage import PerAssetStage
from database.models import AssetAnalysis, FundamentalBrief

class TestPerAssetStageRecovery(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.settings = {
            "trading": {
                "pairs": ["EURUSD", "BTCUSD"],
                "risk": {"max_risk_per_trade_pct": 1.0}
            },
            "analysis": {
                "enable_preflight_gate": False
            },
            "llm": {
                "task_roles": {
                    "stage2_per_asset_primary": {"primary": "gemini-3.5-flash"},
                    "stage2_per_asset_secondary": {"primary": "gemini-3.5-flash"},
                    "stage2_session_trigger": {"primary": "gemini-3.5-flash"}
                }
            },
            "data_quality": {
                "max_brief_age_analysis_hours": 5.0
            }
        }

    def test_user_messages_contain_mandatory_tool_instruction(self):
        stage = PerAssetStage(self.settings)
        msg1 = stage._build_user_message("EURUSD")
        self.assertIn("CRITICAL MANDATORY REQUIREMENT", msg1)
        self.assertIn("submit_asset_analysis", msg1)

        msg2 = stage._build_trimmed_user_message("EURUSD")
        self.assertIn("CRITICAL MANDATORY REQUIREMENT", msg2)
        self.assertIn("submit_asset_analysis", msg2)

    async def test_recovery_tier2_heuristic_text_extraction(self):
        stage = PerAssetStage(self.settings)
        mock_session = AsyncMock()
        mock_session.add = MagicMock()

        dummy_brief = FundamentalBrief(
            id=1, generated_at=datetime.now(timezone.utc), structured_json="{}"
        )
        saved_analysis = AssetAnalysis(id=12345, symbol="EURUSD", decision="buy", confidence=0.8, rationale="breakout", stop_loss=1.0800, take_profit=1.0950)

        submitted = False
        def dynamic_execute(stmt, *args, **kwargs):
            stmt_str = str(stmt)
            res = MagicMock()
            if "fundamental_brief" in stmt_str:
                res.scalar_one_or_none.return_value = dummy_brief
                res.scalars.return_value.all.return_value = [dummy_brief]
            elif "asset_analysis" in stmt_str:
                if submitted:
                    res.scalar_one_or_none.return_value = saved_analysis
                else:
                    res.scalar_one_or_none.return_value = None
            else:
                res.scalar_one_or_none.return_value = None
                res.scalars.return_value.all.return_value = []
                res.first.return_value = MagicMock(total_trades=0, winning_trades=0)
            return res

        mock_session.execute.side_effect = dynamic_execute

        mock_client = MagicMock()
        mock_client.model = "gemini-3.5-flash"
        mock_client.run_agent = AsyncMock(return_value={
            "success": True,
            "final_text": "### Technical Analysis\nTrend is strongly bullish.\n**Decision**: BUY\nConfidence: 0.8\nRationale: Clean breakout above H4 resistance.",
            "tool_calls_made": 0,
            "turns": 1,
            "input_tokens": 100,
            "output_tokens": 50,
            "thinking_tokens": 20
        })
        mock_client.run_agent_from_messages = AsyncMock(return_value={"success": False})

        stage.primary_client = mock_client
        stage._load_playbook = MagicMock(return_value="Playbook text")

        def on_submit(payload):
            nonlocal submitted
            submitted = True
            return {"status": "recorded", "id": 12345}

        with patch("analysis.prefetch.stage2_prefetcher.Stage2DataBundler.fetch_bundle", new_callable=AsyncMock) as mock_bundle, \
             patch("analysis.tools.tool_executor.ToolExecutor._tool_submit_asset_analysis", new_callable=AsyncMock, side_effect=on_submit) as mock_submit, \
             patch.object(stage, "_check_minimum_data_quality", new_callable=AsyncMock, return_value=(True, "ok")), \
             patch.object(stage, "_check_data_coherence_for_analysis", new_callable=AsyncMock, return_value=(True, "ok")), \
             patch.object(stage, "_run_prescreen", new_callable=AsyncMock, return_value=(True, "ok")), \
             patch.object(stage, "_verify_data_currency", new_callable=AsyncMock, return_value=(True, "ok")), \
             patch.object(stage, "_fetch_precomputed_data", new_callable=AsyncMock, return_value=""), \
             patch.object(stage, "_get_specialist_trust_weights", new_callable=AsyncMock, return_value={}), \
             patch.object(stage, "_get_specialist_reliability_cached", new_callable=AsyncMock, return_value={}), \
             patch.object(stage, "_run_second_opinion_check", new_callable=AsyncMock, return_value={"agree": True}), \
             patch("analysis.validators.output_verifier.OutputVerifier.verify_and_correct", new_callable=AsyncMock, return_value=({"decision": "buy"}, [])), \
             patch("analysis.calculators.adaptive_policy.AdaptiveRiskPolicy.get_effective_threshold", new_callable=AsyncMock, return_value=(7, "default")), \
             patch("utils.api.claude_rate_limiter.ClaudeRateLimiter.acquire_session_slot", new_callable=AsyncMock):
            
            mock_bundle.return_value = ("A" * 600, {"EURUSD": {}})

            res = await stage.run_one(mock_session, "EURUSD")
            self.assertTrue(res["success"])
            self.assertEqual(res["decision"], "buy")
            self.assertEqual(mock_submit.call_count, 1)

    async def test_recovery_tier3_deterministic_wait_record(self):
        stage = PerAssetStage(self.settings)
        mock_session = AsyncMock()
        mock_session.add = MagicMock()

        dummy_brief = FundamentalBrief(
            id=1, generated_at=datetime.now(timezone.utc), structured_json="{}"
        )

        def dynamic_execute(stmt, *args, **kwargs):
            stmt_str = str(stmt)
            res = MagicMock()
            if "fundamental_brief" in stmt_str:
                res.scalar_one_or_none.return_value = dummy_brief
                res.scalars.return_value.all.return_value = [dummy_brief]
            elif "asset_analysis" in stmt_str:
                res.scalar_one_or_none.return_value = None
            else:
                res.scalar_one_or_none.return_value = None
                res.scalars.return_value.all.return_value = []
                res.first.return_value = MagicMock(total_trades=0, winning_trades=0)
            return res

        mock_session.execute.side_effect = dynamic_execute

        mock_client = MagicMock()
        mock_client.model = "gemini-3.5-flash"
        mock_client.run_agent = AsyncMock(return_value={
            "success": True,
            "final_text": "Market is choppy and unreadable today.",
            "tool_calls_made": 0,
            "turns": 1,
            "input_tokens": 100,
            "output_tokens": 50,
            "thinking_tokens": 20
        })
        mock_client.run_agent_from_messages = AsyncMock(return_value={"success": False})

        stage.primary_client = mock_client
        stage._load_playbook = MagicMock(return_value="Playbook text")

        with patch("analysis.prefetch.stage2_prefetcher.Stage2DataBundler.fetch_bundle", new_callable=AsyncMock) as mock_bundle, \
             patch.object(stage, "_check_minimum_data_quality", new_callable=AsyncMock, return_value=(True, "ok")), \
             patch.object(stage, "_check_data_coherence_for_analysis", new_callable=AsyncMock, return_value=(True, "ok")), \
             patch.object(stage, "_run_prescreen", new_callable=AsyncMock, return_value=(True, "ok")), \
             patch.object(stage, "_verify_data_currency", new_callable=AsyncMock, return_value=(True, "ok")), \
             patch.object(stage, "_fetch_precomputed_data", new_callable=AsyncMock, return_value=""), \
             patch.object(stage, "_get_specialist_trust_weights", new_callable=AsyncMock, return_value={}), \
             patch.object(stage, "_get_specialist_reliability_cached", new_callable=AsyncMock, return_value={}), \
             patch("analysis.calculators.adaptive_policy.AdaptiveRiskPolicy.get_effective_threshold", new_callable=AsyncMock, return_value=(7, "default")), \
             patch("utils.api.claude_rate_limiter.ClaudeRateLimiter.acquire_session_slot", new_callable=AsyncMock):
            
            mock_bundle.return_value = ("A" * 600, {"EURUSD": {}})

            res = await stage.run_one(mock_session, "EURUSD")
            self.assertTrue(res["success"])
            self.assertEqual(res["decision"], "wait")
            
            # Verify AssetAnalysis was added to session
            added_analysis = [call.args[0] for call in mock_session.add.call_args_list if isinstance(call.args[0], AssetAnalysis)]
            self.assertEqual(len(added_analysis), 1)
            self.assertEqual(added_analysis[0].decision, "wait")
            self.assertEqual(added_analysis[0].confidence, 0.0)
