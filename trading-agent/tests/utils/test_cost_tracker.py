import pytest
import json
from unittest.mock import MagicMock, AsyncMock, patch
from utils.analytics.cost_tracker import CostTracker
from utils.analytics.pricing import cost_usd, get_price, is_free_tier, infer_provider_from_model
from database.models import SystemConfig
from datetime import datetime, timezone


class TestCostTracker:
    def test_free_tier_pricing_rules(self):
        """Validasi bahwa Gemini (free), Groq, OpenRouter :free, openrouter/free, dan Ollama bernilai $0.0."""
        # 1. Gemini direct free tier
        assert cost_usd("gemini-3.7-flash", 10000, 5000, provider="gemini") == 0.0
        assert cost_usd("gemini-3.5-flash", 10000, 5000) == 0.0  # Auto-inferred
        assert cost_usd("models/gemini-2.5-pro", 10000, 5000) == 0.0
        assert is_free_tier("gemini-3.7-flash", provider="gemini") is True

        # 2. Groq developer free tier
        assert cost_usd("groq-compound", 10000, 5000, provider="groq") == 0.0
        assert cost_usd("groq/qwen3.6-27b", 10000, 5000) == 0.0
        assert is_free_tier("groq-compound") is True

        # 3. OpenRouter Free Tier (:free and openrouter/free)
        assert cost_usd("meta-llama/llama-3.3-70b-instruct:free", 10000, 5000, provider="openrouter") == 0.0
        assert cost_usd("google/gemini-2.0-flash-exp:free", 10000, 5000) == 0.0
        assert cost_usd("openrouter/free", 10000, 5000) == 0.0
        assert is_free_tier("meta-llama/llama-3.3-70b-instruct:free") is True
        assert is_free_tier("openrouter/free") is True

        # 4. Ollama Local
        assert cost_usd("llama3.2", 10000, 5000, provider="ollama") == 0.0
        assert is_free_tier("llama3.2") is True

    def test_paid_tier_pricing_rules(self):
        """Validasi bahwa model berbayar dihitung presisi sesuai rate card PRICING."""
        # 1. Gemini Paid Key (GEMINI_PAID_API_KEY)
        gemini_paid_cost = cost_usd("gemini-3.7-flash", 1_000_000, 1_000_000, is_direct_free_tier=False)
        # 1M in ($1.50) + 1M out ($7.50) = $9.00
        assert round(gemini_paid_cost, 2) == 9.00

        # 2. Anthropic Claude
        claude_cost = cost_usd("claude-sonnet-5", 1_000_000, 1_000_000)
        # 1M in ($2.00) + 1M out ($10.00) = $12.00
        assert round(claude_cost, 2) == 12.00

        # 3. DeepSeek
        deepseek_cost = cost_usd("deepseek-chat", 1_000_000, 1_000_000)
        # 1M in ($0.14) + 1M out ($0.28) = $0.42
        assert round(deepseek_cost, 2) == 0.42

        # 4. OpenAI
        gpt_cost = cost_usd("gpt-4o", 1_000_000, 1_000_000)
        # 1M in ($2.50) + 1M out ($10.00) = $12.50
        assert round(gpt_cost, 2) == 12.50

    @pytest.mark.asyncio
    async def test_log_cycle_cost_gemini_free_tier(self):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalar.return_value = None
        mock_session.execute.return_value = mock_result

        settings = {
            "llm": {
                "task_roles": {
                    "stage1_fundamental": {"primary": "gemini-3.7-flash", "provider": "gemini"},
                    "stage2_per_asset_primary": {"primary": "gemini-3.5-flash", "provider": "gemini"},
                }
            }
        }

        cost = await CostTracker.log_cycle_cost(
            mock_session, 100_000, 5_000, 500_000, 20_000, settings=settings
        )
        assert cost == 0.0
        mock_session.add.assert_called_once()
        args = mock_session.add.call_args[0][0]
        assert args.key == "api_cost_tracking"
        history = json.loads(args.value)
        assert history[0]["total_cost_usd"] == 0.0

    @pytest.mark.asyncio
    async def test_log_cycle_cost_claude_paid_tier(self):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalar.return_value = None
        mock_session.execute.return_value = mock_result

        settings = {
            "llm": {
                "task_roles": {
                    "stage1_fundamental": {"primary": "claude-sonnet-5", "provider": "anthropic"},
                    "stage2_per_asset_primary": {"primary": "claude-sonnet-5", "provider": "anthropic"},
                }
            }
        }

        # 1000 in + 3000 in = 4000 in @ $2/1M = $0.008
        # 2000 out + 4000 out = 6000 out @ $10/1M = $0.060
        # total = 0.068
        cost = await CostTracker.log_cycle_cost(
            mock_session, 1000, 2000, 3000, 4000, settings=settings
        )
        assert round(cost, 3) == 0.068

    @pytest.mark.asyncio
    async def test_check_and_update_budget_status_ssot_and_invariants(self):
        """Memverifikasi bahwa TokenUsageLog menjadi SSOT dan mtd_cost >= daily_cost selalu ditegakkan."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        
        mock_cfg_pause = MagicMock()
        mock_cfg_pause.key = "budget_pause"
        mock_cfg_pause.value = "true"
        
        scalar_calls = []
        def execute_side_effect(stmt):
            mock_res = MagicMock()
            sql_str = str(stmt).lower()
            if "token_usage_log" in sql_str:
                if "group by" in sql_str:
                    mock_res.all.return_value = [("gemini", 50000), ("anthropic", 2000)]
                else:
                    if len(scalar_calls) == 0:
                        scalar_calls.append(1)
                        mock_res.scalar_one.return_value = 0.1698
                    else:
                        mock_res.scalar_one.return_value = 0.0
            elif "system_config" in sql_str:
                mock_res.scalar_one_or_none.return_value = mock_cfg_pause
            else:
                mock_res.scalar_one.return_value = 0.0
                mock_res.scalar_one_or_none.return_value = None
            return mock_res
            
        mock_session.execute.side_effect = execute_side_effect
        
        settings = {
            "cost_tracking": {
                "monthly_budget_usd": 100.0,
                "daily_budget_usd": 5.0,
            }
        }
        
        status = await CostTracker.check_and_update_budget_status(mock_session, settings)
        
        # MTD = 0.1698, Daily = 0.0, Invariant MTD >= Daily holds
        assert status["mtd_cost"] == 0.1698
        assert status["daily_cost"] == 0.0
        assert status["is_paused"] is False
        assert mock_cfg_pause.value == "false"  # Auto-cleared!
        assert CostTracker.is_budget_paused_cached() is False

    @pytest.mark.asyncio
    async def test_check_and_update_budget_status_triggers_daily_pause(self):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        
        mock_cfg_pause = MagicMock()
        mock_cfg_pause.key = "budget_pause"
        mock_cfg_pause.value = "false"
        
        scalar_calls = []
        def execute_side_effect(stmt):
            mock_res = MagicMock()
            sql_str = str(stmt).lower()
            if "token_usage_log" in sql_str:
                if "group by" in sql_str:
                    mock_res.all.return_value = [("anthropic", 500000)]
                else:
                    if len(scalar_calls) == 0:
                        scalar_calls.append(1)
                        mock_res.scalar_one.return_value = 10.0
                    else:
                        mock_res.scalar_one.return_value = 5.50
            elif "system_config" in sql_str:
                mock_res.scalar_one_or_none.return_value = mock_cfg_pause
            else:
                mock_res.scalar_one.return_value = 0.0
                mock_res.scalar_one_or_none.return_value = None
            return mock_res
            
        mock_session.execute.side_effect = execute_side_effect
        
        settings = {
            "cost_tracking": {
                "monthly_budget_usd": 100.0,
                "daily_budget_usd": 5.0,
            }
        }
        
        with patch("utils.infra.notifier.AgentNotifier.send_critical", AsyncMock()):
            status = await CostTracker.check_and_update_budget_status(mock_session, settings)
        
        assert status["is_paused"] is True
        assert status["daily_cost"] == 5.50
        assert mock_cfg_pause.value == "true"
        assert CostTracker.is_budget_paused_cached() is True

    @pytest.mark.asyncio
    async def test_clear_budget_pause(self):
        mock_session = AsyncMock()
        mock_cfg_pause = MagicMock()
        mock_cfg_pause.value = "true"
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = mock_cfg_pause
        mock_session.execute = AsyncMock(return_value=mock_res)
        
        CostTracker._cached_pause_state = True
        await CostTracker.clear_budget_pause(mock_session)
        
        assert mock_cfg_pause.value == "false"
        assert CostTracker.is_budget_paused_cached() is False
