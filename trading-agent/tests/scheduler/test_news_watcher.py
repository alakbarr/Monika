import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta
from scheduler.news_watcher import NewsWatcher
from database.models import NewsItem

class TestNewsWatcher:
    @pytest.fixture
    def settings(self, tmp_path):
        return {
            "trading": {
                "schedule": {
                    "news_check_minutes": 5,
                    "news_watcher_state_file": str(tmp_path / "dummy_test_state.json")
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
    @patch("scheduler.news_watcher.get_session")
    @patch("analysis.prefetch.news_digest.NewsDigestProcessor")
    async def test_run_once_no_news(self, mock_processor, mock_get_session, settings):
        watcher = NewsWatcher(settings)
        watcher._fetch_new_news = AsyncMock(return_value=[])
        
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_get_session.return_value = mock_ctx
        
        result = await watcher.run_once()
        assert result["new_items"] == 0
        assert not result["reanalysis_triggered"]

    @pytest.mark.asyncio
    @patch("scheduler.news_watcher.get_session")
    @patch("analysis.prefetch.news_digest.NewsDigestProcessor")
    async def test_run_once_with_news_fallback(self, mock_processor, mock_get_session, settings):
        watcher = NewsWatcher(settings)
        
        news_high = self._make_news("nuclear attack on major city", impact="HIGH")
        news_med = self._make_news("us cpi shows inflation cooling", impact="MEDIUM")
        news_none = self._make_news("random stuff", impact="LOW")
        
        watcher._fetch_new_news = AsyncMock(return_value=[news_high, news_med, news_none])
        watcher._get_affected_symbols = MagicMock(return_value=["XAUUSD"])
        watcher._trigger_reanalysis = AsyncMock()
        
        mock_session = AsyncMock()
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
    @patch("scheduler.news_watcher.get_session")
    @patch("analysis.prefetch.news_digest.NewsDigestProcessor")
    async def test_run_once_with_gemini(self, mock_processor, mock_get_session, settings):
        watcher = NewsWatcher(settings)
        
        news1 = self._make_news("news 1", impact="BREAKING")
        news2 = self._make_news("news 2", impact="MEDIUM")
        
        watcher._fetch_new_news = AsyncMock(return_value=[news1, news2])
        watcher._get_affected_symbols = MagicMock(return_value=["EURUSD"])
        watcher._trigger_reanalysis = AsyncMock()
        
        mock_session = AsyncMock()
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

    @pytest.mark.asyncio
    @patch("asyncio.sleep", new_callable=AsyncMock)
    @patch("scheduler.news_watcher.get_session")
    async def test_trigger_reanalysis(self, mock_get_sess, mock_sleep, settings):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_get_sess.return_value = mock_ctx
        
        mock_cycle = MagicMock()
        mock_cycle.run_once = AsyncMock()
        
        mock_fundamental = MagicMock()
        mock_fundamental.run = AsyncMock()
        
        mock_per_asset = MagicMock()
        mock_per_asset.run_all = AsyncMock()
        
        watcher = NewsWatcher(settings, mock_cycle, mock_fundamental, mock_per_asset)
        
        # Scenario 1: All assets -> Full cycle
        await watcher._trigger_reanalysis([self._make_news("test")], ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD"])
        assert mock_cycle.run_once.call_count == 1
        # mock_cycle.run_once is awaited inside create_task, but we mock create_task itself
        
        # Scenario 2: Partial assets -> fundamental + targeted per_asset
        await watcher._trigger_reanalysis([self._make_news("test")], ["EURUSD"])
        
        mock_fundamental.run.assert_awaited_once()
        assert mock_per_asset.run_all.call_count == 1

    @pytest.mark.asyncio
    @patch("scheduler.news_watcher.get_session")
    @patch("analysis.prefetch.news_digest.NewsDigestProcessor")
    async def test_run_once_narrative_exhaustion_suppressed(self, mock_processor, mock_get_session, settings):
        watcher = NewsWatcher(settings)
        
        # Breaking news that is tagged NARRATIVE_EXHAUSTION (old story rehash)
        news_rehash = self._make_news("White House reiterates tariff comments", impact="BREAKING")
        news_rehash.sentiment = "NARRATIVE_EXHAUSTION,BEARISH_USD"
        
        watcher._fetch_new_news = AsyncMock(return_value=[news_rehash])
        watcher._trigger_reanalysis = AsyncMock()
        
        mock_session = AsyncMock()
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

