import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta
import json

from scheduler.trigger_checker import TriggerChecker
from database.models import TradeTrigger, AssetAnalysis, PriceOHLCV, TechnicalIndicator

class TestTriggerChecker:
    @pytest.fixture
    def settings(self):
        return {
            "trading": {
                "schedule": {
                    "trigger_check_minutes": 2
                }
            }
        }

    def _make_trigger(self, trigger_type, condition, age_hours=0):
        t = MagicMock(spec=TradeTrigger)
        t.id = 1
        t.trigger_type = trigger_type
        t.condition_json = json.dumps(condition)
        t.created_at = datetime.now(timezone.utc) - timedelta(hours=age_hours)
        t.asset_analysis_id = 100
        return t

    @pytest.mark.asyncio
    @patch("scheduler.trigger_checker.get_session")
    async def test_run_once(self, mock_get_session, settings):
        mock_per_asset = MagicMock()
        mock_per_asset.run_one = AsyncMock(return_value={"status": "completed", "skipped_by_brief_staleness": False})
        
        checker = TriggerChecker(settings, mock_per_asset)
        
        t1 = self._make_trigger("price_level", {})
        t2 = self._make_trigger("time", {})
        t3 = self._make_trigger("price_level", {}, age_hours=10)
        
        checker._expire_stale_triggers = AsyncMock(return_value=0)
        checker._get_pending_triggers = AsyncMock(return_value=[t1, t2, t3])
        
        # t1 will fire, t2 will not, t3 will be expired
        checker._evaluate_trigger = AsyncMock(side_effect=[True, False, "expired"])
        checker._fire_trigger = AsyncMock(return_value="XAUUSD")
        checker.check_invalidation_conditions = AsyncMock(return_value=[])
        
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_get_session.return_value = mock_ctx
        
        res = await checker.run_once()
        
        assert res["checked"] == 3
        assert res["fired"] == 1
        assert "XAUUSD" in res["symbols_reanalyzed"]
        
        mock_per_asset.run_one.assert_awaited_once_with(mock_session, "XAUUSD", bypass_prescreen=True, skip_cooldown=True)

    @pytest.mark.asyncio
    @patch("scheduler.trigger_checker.get_session")
    async def test_fire_trigger(self, mock_get_session, settings):
        checker = TriggerChecker(settings)
        t1 = self._make_trigger("price_level", {"price": 100})
        
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_get_session.return_value = mock_ctx
        
        analysis = MagicMock(spec=AssetAnalysis)
        analysis.symbol = "EURUSD"
        mock_session.get.return_value = analysis
        
        symbol = await checker._fire_trigger(mock_session, t1)
        
        assert symbol == "EURUSD"
        mock_session.execute.assert_awaited_once() # update trigger status
        # Add is synchronous in sqlalchemy
        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("scheduler.trigger_checker.get_session")
    async def test_check_price_level(self, mock_get_session, settings):
        checker = TriggerChecker(settings)
        t1 = self._make_trigger("price_level", {"price": 2000, "direction": "above", "symbol": "XAUUSD"})
        
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_get_session.return_value = mock_ctx
        
        bar = MagicMock(spec=PriceOHLCV)
        bar.close = 2010 # 2010 >= 2000 -> True
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = bar
        mock_session.execute.return_value = mock_result
        
        assert await checker._check_price_level(t1, json.loads(t1.condition_json))
        
        bar.close = 1990 # 1990 >= 2000 -> False
        assert not await checker._check_price_level(t1, json.loads(t1.condition_json))
        
        # Test below
        t2 = self._make_trigger("price_level", {"price": 2000, "direction": "below", "symbol": "XAUUSD"})
        bar.close = 1990 # 1990 <= 2000 -> True
        assert await checker._check_price_level(t2, json.loads(t2.condition_json))

    @pytest.mark.asyncio
    @patch("scheduler.trigger_checker.get_session")
    async def test_check_indicator(self, mock_get_session, settings):
        checker = TriggerChecker(settings)
        t1 = self._make_trigger("indicator", {
            "indicator": "RSI_14", "symbol": "XAUUSD", "timeframe": "H4",
            "threshold": 30, "direction": "below"
        })
        
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_get_session.return_value = mock_ctx
        
        ind = MagicMock(spec=TechnicalIndicator)
        ind.value_json = "25.5" # below 30
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = ind
        mock_session.execute.return_value = mock_result
        
        assert await checker._check_indicator(t1, json.loads(t1.condition_json))
        
        ind.value_json = "35.0" # not below 30
        assert not await checker._check_indicator(t1, json.loads(t1.condition_json))

        # dict indicator
        ind.value_json = '{"macd": 10, "signal": 5}'
        # the function checks next(v for v in value.values()), so 10
        t2 = self._make_trigger("indicator", {
            "indicator": "MACD", "symbol": "XAUUSD", "timeframe": "H4",
            "threshold": 0, "direction": "above"
        })
        assert await checker._check_indicator(t2, json.loads(t2.condition_json))

    def test_check_time(self, settings):
        checker = TriggerChecker(settings)
        
        # Future time -> False
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        t1 = self._make_trigger("time", {"fire_at": future.isoformat()})
        assert not checker._check_time(t1, json.loads(t1.condition_json))
        
        # Past time -> True
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        t2 = self._make_trigger("time", {"fire_at": past.isoformat()})
        assert checker._check_time(t2, json.loads(t2.condition_json))

    def test_trigger_age_fallback(self, settings):
        checker = TriggerChecker(settings)
        
        # 1 hour old -> not fired by fallback
        t1 = self._make_trigger("time", {}, age_hours=1)
        assert not checker._check_time(t1, {})
        
        # 7 hours old -> fired by fallback
        t2 = self._make_trigger("time", {}, age_hours=7)
        assert checker._check_time(t2, {})

    @pytest.mark.asyncio
    async def test_evaluate_trigger_ttl_expiration(self, settings):
        checker = TriggerChecker(settings) # max_trigger_age_hours = 6.0
        
        # Fresh price_level trigger (age 2h) -> not expired
        t_fresh = self._make_trigger("price_level", {"price": 2000, "direction": "above", "symbol": "XAUUSD"}, age_hours=2)
        checker._check_price_level = AsyncMock(return_value=False)
        assert await checker._evaluate_trigger(t_fresh) is False
        
        # Stale price_level trigger (age 20h > 18h TTL) -> expired
        t_stale = self._make_trigger("price_level", {"price": 2000, "direction": "above", "symbol": "XAUUSD"}, age_hours=20)
        assert await checker._evaluate_trigger(t_stale) == "expired"
        
        # Stale indicator trigger (age 19h > 18h TTL) -> expired
        t_ind_stale = self._make_trigger("indicator", {"indicator": "RSI_14", "symbol": "EURUSD", "direction": "below", "threshold": 30}, age_hours=19)
        assert await checker._evaluate_trigger(t_ind_stale) == "expired"

        # Stale news trigger (age 24h > 18h TTL) -> expired
        t_news_stale = self._make_trigger("news", {"detail": "NFP"}, age_hours=24)
        assert await checker._evaluate_trigger(t_news_stale) == "expired"

    @pytest.mark.asyncio
    @patch("scheduler.trigger_checker.get_session")
    async def test_expire_stale_triggers_batch(self, mock_get_session, settings):
        checker = TriggerChecker(settings)
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 5
        mock_session.execute.return_value = mock_result
        
        count = await checker._expire_stale_triggers(mock_session)
        assert count == 5
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("scheduler.trigger_checker.get_session")
    async def test_invalid_and_expired_triggers_commit(self, mock_get_session, settings):
        checker = TriggerChecker(settings)
        t_inv = self._make_trigger("price_level", {}, age_hours=1)
        t_inv.id = 11
        t_exp = self._make_trigger("price_level", {}, age_hours=20)
        t_exp.id = 12

        checker._expire_stale_triggers = AsyncMock(return_value=0)
        checker._get_pending_triggers = AsyncMock(return_value=[t_inv, t_exp])
        checker._evaluate_trigger = AsyncMock(side_effect=["invalid", "expired"])
        checker.check_invalidation_conditions = AsyncMock(return_value=[])

        mock_session = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_get_session.return_value = mock_ctx

        res = await checker.run_once()
        assert res["checked"] == 2
        assert res["fired"] == 0
        # Verify commit was awaited twice (once for invalid, once for expired)
        assert mock_session.commit.await_count == 2

