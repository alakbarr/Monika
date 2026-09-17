import pytest
from unittest.mock import AsyncMock, MagicMock
from utils.llm.prompt_ab_test import PromptABTest, OfflinePromptOptimizer

class TestPromptABTest:
    def test_init_and_sync_variant(self):
        ab = PromptABTest(test_name="entry_prompt_test", variant_a_pct=1.0)
        assert ab.test_name == "entry_prompt_test"
        assert ab.get_variant() == "A"

        ab_b = PromptABTest(test_name="entry_prompt_test", variant_a_pct=0.0)
        assert ab_b.get_variant() == "B"

    @pytest.mark.asyncio
    async def test_get_variant_bandit_warmup(self):
        ab = PromptABTest(test_name="warmup_test", min_warmup_samples=10)
        # None session falls back to sync get_variant
        res = await ab.get_variant_bandit(None)
        assert res in ("A", "B")

class TestOfflinePromptOptimizer:
    def test_select_champion_empty(self):
        opt = OfflinePromptOptimizer()
        variant, promotable = opt.select_champion({})
        assert variant == "A"
        assert promotable is False

    def test_select_champion_promotable(self):
        opt = OfflinePromptOptimizer()
        scores = {
            "A": {"win_rate": 52.0, "count": 20},
            "B": {"win_rate": 58.5, "count": 15},
        }
        variant, promotable = opt.select_champion(scores, min_win_rate_delta=3.0)
        assert variant == "B"
        assert promotable is True

    def test_select_champion_insufficient_samples(self):
        opt = OfflinePromptOptimizer()
        scores = {
            "A": {"win_rate": 50.0, "count": 20},
            "B": {"win_rate": 60.0, "count": 5},  # count < 10
        }
        variant, promotable = opt.select_champion(scores, min_win_rate_delta=3.0)
        assert variant == "B"
        assert promotable is False

    def test_select_champion_insufficient_margin(self):
        opt = OfflinePromptOptimizer()
        scores = {
            "A": {"win_rate": 50.0, "count": 20},
            "B": {"win_rate": 51.5, "count": 20},  # delta 1.5 < 3.0
        }
        variant, promotable = opt.select_champion(scores, min_win_rate_delta=3.0)
        assert variant == "B"
        assert promotable is False

    def test_score_variant_performance_metrics(self):
        opt = OfflinePromptOptimizer()
        results = [
            {"pnl": 100.0},
            {"pnl": 50.0},
            {"pnl": -50.0},
        ]
        metrics = opt.score_variant_performance("B", results)
        assert metrics["variant"] == "B"
        assert metrics["count"] == 3
        assert metrics["wins"] == 2
        assert metrics["losses"] == 1
        assert metrics["win_rate"] == 66.67
        assert metrics["profit_factor"] == 3.0
        assert metrics["total_pnl"] == 100.0

