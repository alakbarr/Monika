import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta
from tests.conftest import create_mock_async_session
from monika.application.scheduler.news_watcher import NewsWatcher
from monika.infrastructure.database.models import NewsItem


class TestNewsWatcher:
    @pytest.fixture
    def settings(self, tmp_path):
        return {
            "trading": {
                "schedule": {
                    "news_check_minutes": 5,
                    "news_watcher_state_file": str(tmp_path / "dummy_test_state.json"),
                }
            }
        }

    def _make_news(self, title, summary="", impact=None, currency_tags=None):
        news = MagicMock(spec=NewsItem)
        news.title = title
        news.summary = summary
        news.impact = impact
        news.currency_tags = currency_tags
        news.fetched_at = datetime.now(timezone.utc)
        news.published_at = datetime.now(timezone.utc)
        news.url = f"http://test.com/{title.replace(' ', '')}"
        return news

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    @patch("monika.application.scheduler.news_watcher.get_session")
    @patch("monika.application.analysis.prefetch.news_digest.NewsDigestProcessor")
    async def test_run_once_no_news(self, mock_processor, mock_get_session, settings):
        watcher = NewsWatcher(settings)
        watcher._fetch_new_news = AsyncMock(return_value=[])

        mock_session = create_mock_async_session()
        mock_session.add = MagicMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_get_session.return_value = mock_ctx

        result = await watcher.run_once()
        assert result["new_items"] == 0
        assert not result["reanalysis_triggered"]

    @pytest.mark.asyncio
    @patch("monika.application.scheduler.news_watcher.get_session")
    @patch("monika.application.analysis.prefetch.news_digest.NewsDigestProcessor")
    async def test_run_once_with_news_fallback(self, mock_processor, mock_get_session, settings):
        watcher = NewsWatcher(settings)

        news_high = self._make_news("nuclear attack on major city", impact="BREAKING")
        news_med = self._make_news("us cpi shows inflation cooling", impact="MEDIUM")
        news_none = self._make_news("random stuff", impact="LOW")

        watcher._fetch_new_news = AsyncMock(return_value=[news_high, news_med, news_none])
        watcher._get_affected_symbols = MagicMock(return_value=["XAUUSD"])
        watcher._trigger_reanalysis = AsyncMock()

        mock_session = create_mock_async_session()
        mock_session.add = MagicMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_get_session.return_value = mock_ctx

        # Simulate gemini failure
        processor_instance = mock_processor.return_value
        processor_instance.classify_unscored_news = AsyncMock(side_effect=Exception("API Error"))

        result = await watcher.run_once()

        assert result["new_items"] == 3
        assert result["high_impact_found"] == 1
        assert result["medium_impact_found"] == 1
        assert result["reanalysis_triggered"]

        watcher._trigger_reanalysis.assert_called_once()

    @pytest.mark.asyncio
    @patch("monika.application.scheduler.news_watcher.get_session")
    @patch("monika.application.analysis.prefetch.news_digest.NewsDigestProcessor")
    async def test_run_once_with_gemini(self, mock_processor, mock_get_session, settings):
        watcher = NewsWatcher(settings)

        news1 = self._make_news("news 1", impact="BREAKING")
        news2 = self._make_news("news 2", impact="MEDIUM")

        watcher._fetch_new_news = AsyncMock(return_value=[news1, news2])
        watcher._get_affected_symbols = MagicMock(return_value=["EURUSD"])
        watcher._trigger_reanalysis = AsyncMock()

        mock_session = create_mock_async_session()
        mock_session.add = MagicMock()

        # Return mock_session for all get_session() contexts
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_get_session.return_value = mock_ctx

        # Mock the session.execute().scalars().all() to return our items
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [news1, news2]
        mock_session.execute.return_value = mock_result

        processor_instance = mock_processor.return_value
        processor_instance.classify_unscored_news = AsyncMock()

        result = await watcher.run_once()

        assert result["high_impact_found"] == 1
        assert result["medium_impact_found"] == 1
        assert result["reanalysis_triggered"]

    def test_regex_matching(self, settings):
        watcher = NewsWatcher(settings)

        assert watcher._is_high_impact(self._make_news("Emergency cut by FED"))
        assert watcher._is_high_impact(self._make_news("War declared in middle east"))
        assert not watcher._is_high_impact(self._make_news("CPI inflation report"))

        assert watcher._is_medium_impact(self._make_news("CPI inflation report"))
        assert watcher._is_medium_impact(self._make_news("Fed speak scheduled for today"))

    def test_get_affected_symbols(self, settings):
        watcher = NewsWatcher(settings)

        news1 = self._make_news("ECB raises rate", currency_tags="EUR,GBP")
        affected = watcher._get_affected_symbols([news1])
        assert "EURUSD" in affected
        assert "GBPUSD" in affected

        # fallback title scan
        news2 = self._make_news("Bank of Japan intervenes in JPY")
        affected2 = watcher._get_affected_symbols([news2])
        assert "USDJPY" in affected2

        # BTC / Crypto tags
        news_btc = self._make_news("SEC approves spot Bitcoin ETF", currency_tags="BTC")
        affected_btc = watcher._get_affected_symbols([news_btc])
        assert "BTCUSD" in affected_btc

        # Oil tags
        news_oil = self._make_news("OPEC surprise output cut", currency_tags="XTI")
        affected_oil = watcher._get_affected_symbols([news_oil])
        assert "XTIUSD" in affected_oil
        assert "XBRUSD" in affected_oil

        # FOMC affects all (8 assets)
        news3 = self._make_news("fomc rate decision causes dollar surge")
        affected3 = watcher._get_affected_symbols([news3])
        assert len(affected3) >= 8
        assert "XAUUSD" in affected3
        assert "BTCUSD" in affected3
        assert "XTIUSD" in affected3

    def test_get_affected_symbols_routine_usd_vs_tier1_macro(self, settings):
        watcher = NewsWatcher(settings)
        all_8_symbols = ["AUDUSD", "BTCUSD", "EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "XBRUSD", "XTIUSD"]
        core_4_symbols = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]

        # 1. Routine USD news (e.g. jobless claims) -> only 4 core USD symbols
        routine_news = self._make_news(
            "US initial jobless claims edge lower",
            summary="Initial claims dropped slightly to 215k.",
            currency_tags="USD",
        )
        affected_routine = watcher._get_affected_symbols([routine_news])
        assert affected_routine == core_4_symbols
        assert "BTCUSD" not in affected_routine
        assert "AUDUSD" not in affected_routine
        assert "XTIUSD" not in affected_routine
        assert "XBRUSD" not in affected_routine

        # Routine USD news via title scan only (no currency_tags)
        routine_title_news = self._make_news("USD steadies after retail sales data meets expectations")
        assert watcher._get_affected_symbols([routine_title_news]) == core_4_symbols

        # 2. Tier-1 systemic macro shocks -> all 8 symbols
        tier1_cases = [
            ("FOMC rate decision causes dollar surge", "USD"),
            ("US CPI inflation print hotter than expected", "USD"),
            ("Nonfarm payrolls surge by 300k", "USD"),
            ("Fed Chair Powell delivers hawkish remarks", "USD"),
            ("Federal Reserve announces monetary policy decision", "USD"),
            ("NFP report beats consensus expectations", "USD"),
            ("Emergency rate cut announced by central authorities", "USD"),
            ("Inflation shock rattles global debt markets", "USD"),
            ("Fed rate trajectory remains uncertain", "USD"),
            ("Non-farm employment data surprises to upside", "USD"),
        ]
        for title, tag in tier1_cases:
            t1_news = self._make_news(title, currency_tags=tag)
            affected = watcher._get_affected_symbols([t1_news])
            assert affected == all_8_symbols, f"Failed for Tier-1 shock: '{title}'"

    @pytest.mark.asyncio
    @patch("asyncio.sleep", new_callable=AsyncMock)
    @patch("monika.application.scheduler.news_watcher.get_session")
    async def test_trigger_reanalysis(self, mock_get_sess, mock_sleep, settings):
        mock_session = create_mock_async_session()
        mock_session.add = MagicMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_get_sess.return_value = mock_ctx

        mock_cycle = MagicMock()
        mock_cycle.run_once = AsyncMock()

        mock_fundamental = MagicMock()
        mock_fundamental.run = AsyncMock()
        mock_fundamental.patch_brief = AsyncMock()

        mock_per_asset = MagicMock()
        mock_per_asset.run_all = AsyncMock(return_value={})

        watcher = NewsWatcher(settings, mock_cycle, mock_fundamental, mock_per_asset)

        # Scenario 1: All assets -> delta revision patch_brief + targeted per_asset (NO full cycle)
        await watcher._trigger_reanalysis([self._make_news("test")], ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD"])
        assert mock_cycle.run_once.call_count == 0
        assert mock_fundamental.patch_brief.call_count == 1
        assert mock_per_asset.run_all.call_count == 1

        # Reset per-symbol cooldown for scenario 2
        watcher._last_reanalysis.clear()

        # Scenario 2: Partial assets -> delta revision patch_brief + targeted per_asset
        await watcher._trigger_reanalysis([self._make_news("test2")], ["EURUSD"])

        assert mock_cycle.run_once.call_count == 0
        assert mock_fundamental.patch_brief.call_count == 2
        assert mock_per_asset.run_all.call_count == 2

    @pytest.mark.asyncio
    @patch("monika.application.scheduler.news_watcher.get_session")
    @patch("monika.application.analysis.prefetch.news_digest.NewsDigestProcessor")
    async def test_run_once_narrative_exhaustion_suppressed(self, mock_processor, mock_get_session, settings):
        watcher = NewsWatcher(settings)

        # Breaking news that is tagged NARRATIVE_EXHAUSTION (old story rehash)
        news_rehash = self._make_news("White House reiterates tariff comments", impact="BREAKING")
        news_rehash.sentiment = "NARRATIVE_EXHAUSTION,BEARISH_USD"

        watcher._fetch_new_news = AsyncMock(return_value=[news_rehash])
        watcher._trigger_reanalysis = AsyncMock()

        mock_session = create_mock_async_session()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_get_session.return_value = mock_ctx

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [news_rehash]
        mock_session.execute.return_value = mock_result

        result = await watcher.run_once()

        # Should NOT trigger emergency reanalysis
        assert not result["reanalysis_triggered"]
        watcher._trigger_reanalysis.assert_not_called()

    @pytest.mark.asyncio
    @patch("monika.application.scheduler.news_watcher.get_session")
    @patch("monika.application.analysis.prefetch.news_digest.NewsDigestProcessor")
    async def test_run_once_breaking_news_logs_info(self, mock_processor, mock_get_session, settings, caplog):
        import logging

        watcher = NewsWatcher(settings)
        news_breaking = self._make_news("major geopolitical crisis breaks out", impact="BREAKING")
        watcher._fetch_new_news = AsyncMock(return_value=[news_breaking])
        watcher._get_affected_symbols = MagicMock(return_value=["XAUUSD"])
        watcher._trigger_reanalysis = AsyncMock()

        mock_session = create_mock_async_session()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [news_breaking]
        mock_session.execute.return_value = mock_result
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_get_session.return_value = mock_ctx

        processor_instance = mock_processor.return_value
        processor_instance.classify_unscored_news = AsyncMock()

        with caplog.at_level(logging.INFO):
            result = await watcher.run_once()

        assert result["reanalysis_triggered"] is True
        assert any("BREAKING NEWS DETECTED" in rec.message and rec.levelno == logging.INFO for rec in caplog.records)

    @pytest.mark.asyncio
    @patch("monika.application.scheduler.news_watcher.get_session")
    @patch("monika.application.analysis.prefetch.news_digest.NewsDigestProcessor")
    async def test_run_once_high_impact_does_not_trigger_reanalysis(
        self, mock_processor, mock_get_session, settings, caplog
    ):
        import logging

        watcher = NewsWatcher(settings)
        news_high = self._make_news("fed speaker gives routine rate guidance", impact="HIGH")
        watcher._fetch_new_news = AsyncMock(return_value=[news_high])
        watcher._get_affected_symbols = MagicMock(return_value=["USDJPY"])
        watcher._trigger_reanalysis = AsyncMock()

        mock_session = create_mock_async_session()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [news_high]
        mock_session.execute.return_value = mock_result
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_get_session.return_value = mock_ctx

        processor_instance = mock_processor.return_value
        processor_instance.classify_unscored_news = AsyncMock()

        with caplog.at_level(logging.INFO):
            result = await watcher.run_once()

        assert result["reanalysis_triggered"] is False
        assert result["high_impact_found"] == 1
        watcher._trigger_reanalysis.assert_not_called()
        assert any("High-impact news recorded" in rec.message for rec in caplog.records)

    @pytest.mark.asyncio
    @patch("monika.application.scheduler.news_watcher.get_session")
    @patch("monika.application.analysis.prefetch.news_digest.NewsDigestProcessor")
    async def test_run_once_skips_duplicate_classification_when_lock_held(
        self, mock_processor, mock_get_session, settings
    ):
        from monika.application.analysis.prefetch.news_digest.classification import (
            get_news_classification_lock,
        )

        watcher = NewsWatcher(settings)
        news_routine = self._make_news("routine market update", impact=None)
        watcher._fetch_new_news = AsyncMock(return_value=[news_routine])

        mock_session = create_mock_async_session()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [news_routine]
        mock_session.execute.return_value = mock_result
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_get_session.return_value = mock_ctx

        processor_instance = mock_processor.return_value
        processor_instance.classify_unscored_news = AsyncMock()

        cls_lock = get_news_classification_lock()
        async with cls_lock:
            await watcher.run_once()

        # Because another worker holds the classification lock and item is not a shock keyword,
        # NewsWatcher must skip spawning a duplicate concurrent classification pass.
        processor_instance.classify_unscored_news.assert_not_called()

    @pytest.mark.asyncio
    @patch("asyncio.sleep", new_callable=AsyncMock)
    @patch("monika.application.scheduler.news_watcher.get_session")
    @patch("monika.core.analytics.cost_tracker.CostTracker.is_budget_paused", new_callable=AsyncMock)
    @patch("monika.core.analytics.cost_tracker.CostTracker.is_budget_paused_cached", return_value=False)
    async def test_trigger_reanalysis_budget_paused_suppresses_runs(
        self, mock_cached_paused, mock_is_paused, mock_get_sess, mock_sleep, settings
    ):
        mock_is_paused.return_value = True

        mock_session = create_mock_async_session()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_get_sess.return_value = mock_ctx

        mock_fundamental = MagicMock()
        mock_fundamental.patch_brief = AsyncMock()
        mock_per_asset = MagicMock()
        mock_per_asset.run_all = AsyncMock()

        watcher = NewsWatcher(settings, fundamental_stage=mock_fundamental, per_asset_stage=mock_per_asset)
        watcher._run_targeted_reanalysis_and_route = AsyncMock()
        watcher._tighten_sl_on_breaking_news = AsyncMock()

        news_item = self._make_news("Fed Emergency Shock", impact="HIGH", currency_tags="USD")
        await watcher._trigger_reanalysis([news_item], ["EURUSD", "GBPUSD"])

        # In decoupled architecture: budget pause allows free-tier news re-analysis
        watcher._run_targeted_reanalysis_and_route.assert_called_once()
        assert watcher._targeted_reruns_today == 1

    @pytest.mark.asyncio
    @patch("asyncio.sleep", new_callable=AsyncMock)
    @patch("monika.application.scheduler.news_watcher.get_session")
    @patch("monika.core.analytics.cost_tracker.CostTracker.is_budget_paused", new_callable=AsyncMock)
    @patch("monika.core.analytics.cost_tracker.CostTracker.is_budget_paused_cached", return_value=False)
    @patch("monika.core.analytics.cost_tracker.CostTracker.evaluate_budget", new_callable=AsyncMock)
    async def test_trigger_reanalysis_near_budget_filters_idle_assets(
        self,
        mock_eval_budget,
        mock_cached_paused,
        mock_is_paused,
        mock_get_sess,
        mock_sleep,
        settings,
    ):
        mock_is_paused.return_value = False
        # Daily budget = 3.0, Daily cost = 2.85 (>= 90% soft guard: $2.85 >= $2.70)
        mock_eval_budget.return_value = {
            "daily_cost": 2.85,
            "daily_budget": 3.0,
            "weekly_cost": 10.0,
            "weekly_budget": 18.0,
            "mtd_cost": 30.0,
            "monthly_budget": 60.0,
            "is_paused": False,
        }

        mock_session = create_mock_async_session()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_get_sess.return_value = mock_ctx

        # Mock execute queries: only EURUSD has an open position
        async def mock_execute(stmt, *args, **kwargs):
            mock_res = MagicMock()
            stmt_str = str(stmt)
            if "positions.symbol" in stmt_str:
                mock_res.scalars.return_value.all.return_value = ["EURUSD"]
                return mock_res
            mock_res.scalar_one_or_none.return_value = 0
            mock_res.scalar.return_value = 0
            mock_res.scalars.return_value.all.return_value = []
            return mock_res

        mock_session.execute = AsyncMock(side_effect=mock_execute)

        mock_fundamental = MagicMock()
        mock_fundamental.patch_brief = AsyncMock()
        mock_per_asset = MagicMock()
        mock_per_asset.run_all = AsyncMock()

        watcher = NewsWatcher(settings, fundamental_stage=mock_fundamental, per_asset_stage=mock_per_asset)
        watcher._run_targeted_reanalysis_and_route = AsyncMock()
        watcher._tighten_sl_on_breaking_news = AsyncMock()

        news_item = self._make_news("Fed Rate Hike Threat", impact="HIGH", currency_tags="USD")

        # Scenario 1: Mixed assets (EURUSD has open position, GBPUSD and USDJPY are idle)
        await watcher._trigger_reanalysis([news_item], ["EURUSD", "GBPUSD", "USDJPY"])

        watcher._run_targeted_reanalysis_and_route.assert_called_once()
        called_symbols = watcher._run_targeted_reanalysis_and_route.call_args.kwargs.get("symbols")
        assert called_symbols == ["EURUSD"]

        # Reset mocks for Scenario 2: All affected assets are idle (no open positions)
        watcher._run_targeted_reanalysis_and_route.reset_mock()
        mock_fundamental.patch_brief.reset_mock()

        async def mock_execute_none(stmt, *args, **kwargs):
            mock_res = MagicMock()
            stmt_str = str(stmt)
            if "positions.symbol" in stmt_str:
                mock_res.scalars.return_value.all.return_value = []
                return mock_res
            mock_res.scalar_one_or_none.return_value = 0
            mock_res.scalar.return_value = 0
            mock_res.scalars.return_value.all.return_value = []
            return mock_res

        mock_session.execute = AsyncMock(side_effect=mock_execute_none)
        await watcher._trigger_reanalysis([news_item], ["GBPUSD", "USDJPY"])

        # Re-analysis completely suppressed for idle assets
        watcher._run_targeted_reanalysis_and_route.assert_not_called()

    @pytest.mark.asyncio
    @patch("asyncio.sleep", new_callable=AsyncMock)
    @patch("monika.application.scheduler.news_watcher.get_session")
    @patch("monika.core.analytics.cost_tracker.CostTracker.is_budget_paused", new_callable=AsyncMock)
    @patch("monika.core.analytics.cost_tracker.CostTracker.is_budget_paused_cached", return_value=False)
    @patch("monika.core.analytics.cost_tracker.CostTracker.evaluate_budget", new_callable=AsyncMock)
    async def test_trigger_reanalysis_weekly_near_budget_filters_idle_assets(
        self,
        mock_eval_budget,
        mock_cached_paused,
        mock_is_paused,
        mock_get_sess,
        mock_sleep,
        settings,
    ):
        mock_is_paused.return_value = False
        # Daily cost = 1.0 (daily budget 3.0, <90%), Weekly cost = 16.50 (weekly budget 18.0, >= 90% soft guard: 16.50 >= 16.20)
        mock_eval_budget.return_value = {
            "daily_cost": 1.0,
            "daily_budget": 3.0,
            "weekly_cost": 16.50,
            "weekly_budget": 18.0,
            "mtd_cost": 30.0,
            "monthly_budget": 60.0,
            "is_paused": False,
        }

        mock_session = create_mock_async_session()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_get_sess.return_value = mock_ctx

        async def mock_execute(stmt, *args, **kwargs):
            mock_res = MagicMock()
            stmt_str = str(stmt)
            if "positions.symbol" in stmt_str:
                mock_res.scalars.return_value.all.return_value = ["EURUSD"]
                return mock_res
            mock_res.scalar_one_or_none.return_value = 0
            mock_res.scalar.return_value = 0
            mock_res.scalars.return_value.all.return_value = []
            return mock_res

        mock_session.execute = AsyncMock(side_effect=mock_execute)

        mock_fundamental = MagicMock()
        mock_fundamental.patch_brief = AsyncMock()
        mock_per_asset = MagicMock()
        mock_per_asset.run_all = AsyncMock()

        watcher = NewsWatcher(settings, fundamental_stage=mock_fundamental, per_asset_stage=mock_per_asset)
        watcher._run_targeted_reanalysis_and_route = AsyncMock()
        watcher._tighten_sl_on_breaking_news = AsyncMock()

        news_item = self._make_news("Fed Rate Hike Threat", impact="HIGH", currency_tags="USD")

        # Mixed assets: EURUSD open, GBPUSD idle -> GBPUSD dropped
        await watcher._trigger_reanalysis([news_item], ["EURUSD", "GBPUSD"])

        watcher._run_targeted_reanalysis_and_route.assert_called_once()
        called_symbols = watcher._run_targeted_reanalysis_and_route.call_args.kwargs.get("symbols")
        assert called_symbols == ["EURUSD"]


class TestNewsWatcherPersistence:
    @pytest.fixture
    def state_file(self, tmp_path):
        return tmp_path / "news_watcher_state.json"

    @pytest.fixture
    def settings(self, state_file):
        return {
            "trading": {
                "schedule": {
                    "news_check_minutes": 5,
                    "news_watcher_state_file": str(state_file),
                }
            },
            "news_classification_control": {
                "max_targeted_reruns_per_day": 10,
            },
        }

    def test_state_persistence_restores_reruns_and_cooldown(self, settings, state_file):
        watcher1 = NewsWatcher(settings)
        now_utc = datetime.now(timezone.utc)
        cooldown_time = now_utc - timedelta(minutes=10)

        watcher1._targeted_reruns_today = 4
        watcher1._last_reanalysis = {"EURUSD": cooldown_time}
        watcher1._last_seen_at = now_utc - timedelta(hours=1)
        watcher1._save_persistent_state()

        assert state_file.exists()

        watcher2 = NewsWatcher(settings)
        assert watcher2._targeted_reruns_today == 4
        assert "EURUSD" in watcher2._last_reanalysis
        assert abs((watcher2._last_reanalysis["EURUSD"] - cooldown_time).total_seconds()) < 1.0

    def test_state_day_rollover_resets_counter(self, settings, state_file):
        now_utc = datetime.now(timezone.utc)
        cooldown_time = now_utc - timedelta(minutes=10)
        state_data = {
            "last_seen_at": (now_utc - timedelta(hours=2)).isoformat(),
            "forced_reruns_today": 2,
            "forced_rerun_day": "2020-01-01",
            "targeted_reruns_today": 8,
            "targeted_rerun_day": "2020-01-01",
            "last_reanalysis": {"EURUSD": cooldown_time.isoformat()},
        }
        state_file.write_text(json.dumps(state_data), encoding="utf-8")

        watcher = NewsWatcher(settings)
        assert watcher._targeted_reruns_today == 0
        assert watcher._forced_reruns_today == 0
        assert "EURUSD" in watcher._last_reanalysis

    def test_corrupt_and_missing_json_handling(self, settings, state_file):
        # Missing file: clean startup
        if state_file.exists():
            state_file.unlink()
        watcher = NewsWatcher(settings)
        assert watcher._targeted_reruns_today == 0
        assert watcher._last_reanalysis == {}

        # Corrupt JSON: must not crash, use defaults
        state_file.write_text("{ corrupted json [", encoding="utf-8")
        watcher_corrupt = NewsWatcher(settings)
        assert watcher_corrupt._targeted_reruns_today == 0
        assert watcher_corrupt._last_reanalysis == {}

    def test_partial_json_without_day_does_not_silently_grant_reruns(self, settings, state_file):
        # Partial state with budget used but missing day fields:
        # must NOT reset to 0 (which would silently grant reruns)
        state_data = {
            "targeted_reruns_today": 7,
            "forced_reruns_today": 2,
        }
        state_file.write_text(json.dumps(state_data), encoding="utf-8")

        watcher = NewsWatcher(settings)
        assert watcher._targeted_reruns_today == 7
        assert watcher._forced_reruns_today == 2

    def test_future_and_unparseable_cooldown_timestamps_ignored(self, settings, state_file):
        now_utc = datetime.now(timezone.utc)
        valid_time = now_utc - timedelta(minutes=15)
        future_time = now_utc + timedelta(days=2)
        state_data = {
            "targeted_reruns_today": 2,
            "last_reanalysis": {
                "INVALID": "not-a-valid-timestamp",
                "FUTURE": future_time.isoformat(),
                "VALID": valid_time.isoformat(),
            },
        }
        state_file.write_text(json.dumps(state_data), encoding="utf-8")

        watcher = NewsWatcher(settings)
        assert "INVALID" not in watcher._last_reanalysis
        assert "FUTURE" not in watcher._last_reanalysis
        assert "VALID" in watcher._last_reanalysis
        assert abs((watcher._last_reanalysis["VALID"] - valid_time).total_seconds()) < 1.0

    @pytest.mark.asyncio
    @patch("asyncio.sleep", new_callable=AsyncMock)
    @patch("monika.application.scheduler.news_watcher.get_session")
    async def test_trigger_reanalysis_persists_counter_and_cooldown_immediately(
        self, mock_get_sess, mock_sleep, settings, state_file
    ):
        mock_session = create_mock_async_session()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_get_sess.return_value = mock_ctx

        mock_cycle = MagicMock()
        mock_cycle.run_once = AsyncMock()
        mock_cycle._cycle_lock = None

        mock_fundamental = MagicMock()
        mock_fundamental.patch_brief = AsyncMock()

        mock_per_asset = MagicMock()
        mock_per_asset.run_all = AsyncMock(return_value={})

        news_item = MagicMock(spec=NewsItem)
        news_item.title = "Fed Emergency Cut"
        news_item.summary = "Surprise cut"
        news_item.impact = "HIGH"
        news_item.currency_tags = "USD"
        news_item.published_at = datetime.now(timezone.utc)
        news_item.fetched_at = datetime.now(timezone.utc)

        watcher = NewsWatcher(settings, mock_cycle, mock_fundamental, mock_per_asset)
        watcher._run_targeted_reanalysis_and_route = AsyncMock()
        watcher._tighten_sl_on_breaking_news = AsyncMock()

        assert watcher._targeted_reruns_today == 0
        await watcher._trigger_reanalysis([news_item], ["EURUSD"])

        assert watcher._targeted_reruns_today == 1
        assert "EURUSD" in watcher._last_reanalysis
        assert state_file.exists()

        saved = json.loads(state_file.read_text(encoding="utf-8"))
        assert saved["targeted_reruns_today"] == 1
        assert "EURUSD" in saved["last_reanalysis"]
