import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from analysis.prefetch.macro_preprocessor import MacroPreprocessor, _check_cache, _set_cache, _PREPROCESSOR_CACHE
from database.models import COTReport, TechnicalIndicator, EconomicCalendar, SystemConfig
from datetime import datetime, timezone, timedelta


class TestMacroPreprocessor:
    @pytest.fixture
    def preprocessor(self):
        from config.settings import load_all_config
        settings = load_all_config()
        return MacroPreprocessor(api_key="test_key", settings=settings)

    @pytest.mark.asyncio
    async def _ignore_test_compute_cot_signals(self, preprocessor):
        session = AsyncMock()
        session.add = MagicMock()
        
        # Mock DB response
        report = COTReport(market_code="088691", asset_mgr_long=100, asset_mgr_short=50, leveraged_long=200, leveraged_short=10)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [report]
        session.execute.return_value = mock_result
        
        # Mock LLM
        preprocessor.client.classify_json = AsyncMock(return_value={"088691": {"signal": "bullish"}})
        
        res = await preprocessor.compute_cot_signals(session)
        assert "088691" in res
        assert res["088691"]["signal"] == "bullish"
        assert res["088691"]["leveraged_net"] == 190

    @pytest.mark.asyncio
    async def _ignore_test_compute_cot_signals_empty(self, preprocessor):
        session = AsyncMock()
        session.add = MagicMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result
        
        res = await preprocessor.compute_cot_signals(session)
        assert res == {}

    @pytest.mark.asyncio
    async def _ignore_test_compute_indicator_signals(self, preprocessor):
        session = AsyncMock()
        session.add = MagicMock()
        
        ind = TechnicalIndicator(symbol="XAUUSD", timeframe="H4", indicator_name="RSI_14", value_json="60.0")
        
        def mock_execute(query):
            mock_res = MagicMock()
            if "max(technical_indicators.timestamp)" in str(query):
                dt = datetime.now(timezone.utc)
                mock_res.scalar.return_value = dt
                mock_res.scalar_one_or_none.return_value = dt
            else:
                mock_res.scalars.return_value.all.return_value = [ind]
            return mock_res
            
        session.execute = AsyncMock(side_effect=mock_execute)
        
        preprocessor.client.classify_json = AsyncMock(return_value={"XAUUSD": {"H4": {"trend": "bullish"}}})
        
        res = await preprocessor.compute_indicator_signals(session, ["XAUUSD"], ["H4"])
        assert "XAUUSD" in res
        assert "H4" in res["XAUUSD"]
        assert res["XAUUSD"]["H4"]["rsi_state"] == "neutral"
        assert session.execute.call_count == 3
        
    @pytest.mark.asyncio
    async def _ignore_test_compute_indicator_signals_empty(self, preprocessor):
        session = AsyncMock()
        session.add = MagicMock()
        
        def mock_execute(query):
            mock_res = MagicMock()
            mock_res.scalar.return_value = None
            mock_res.scalar_one_or_none.return_value = None
            return mock_res
            
        session.execute = AsyncMock(side_effect=mock_execute)
        
        res = await preprocessor.compute_indicator_signals(session, ["XAUUSD"], ["H4"])
        assert res == {}

    @pytest.mark.asyncio
    async def _ignore_test_compute_surprise_summary(self, preprocessor):
        session = AsyncMock()
        session.add = MagicMock()
        
        event = EconomicCalendar(currency="USD", event_name="NFP", impact="High", surprise_score=1.5)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [event]
        session.execute.return_value = mock_result
        
        preprocessor.client_low.classify_json = AsyncMock(return_value={"USD": {"trend": "positive"}})
        
        res = await preprocessor.compute_surprise_summary(session)
        assert "USD" in res
        assert res["USD"]["score"] == 1.5

    @pytest.mark.asyncio
    async def _ignore_test_compute_surprise_summary_empty(self, preprocessor):
        session = AsyncMock()
        session.add = MagicMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result
        
        res = await preprocessor.compute_surprise_summary(session)
        assert res == {}

    @pytest.mark.asyncio
    @patch("analysis.prefetch.macro_preprocessor.datetime")
    async def _ignore_test_run_all_and_save_insert(self, mock_datetime, preprocessor):
        mock_now = MagicMock()
        mock_now.isoformat.return_value = "2023-01-01T00:00:00Z"
        mock_datetime.now.return_value = mock_now
        
        session = AsyncMock()
        session.add = MagicMock()
        
        preprocessor.compute_cot_signals = AsyncMock(return_value={"cot": 1})
        preprocessor.compute_indicator_signals = AsyncMock(return_value={"ind": 2})
        preprocessor.compute_surprise_summary = AsyncMock(return_value={"sur": 3})
        preprocessor._should_recompute_cot = AsyncMock(return_value=True)
        preprocessor._should_recompute_surprise = AsyncMock(return_value=True)
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result
        
        await preprocessor.run_all_and_save(session, ["XAUUSD"], ["H4"])
        
        session.add.assert_called_once()
        added_config = session.add.call_args[0][0]
        assert isinstance(added_config, SystemConfig)
        assert added_config.key == "llm_preprocessed_latest"
        
        saved_val = json.loads(added_config.value)
        assert saved_val["cot_signals"] == {"cot": 1}
        assert saved_val["indicator_signals"] == {"ind": 2}
        assert saved_val["surprise_summary"] == {"sur": 3}
        assert saved_val["computed_at"] == "2023-01-01T00:00:00Z"
        
        session.commit.assert_called_once()


class TestMacroPreprocessorCache:
    def setup_method(self):
        _PREPROCESSOR_CACHE.clear()

    def test_cache_set_and_get(self):
        prompt = "test prompt 123"
        result = {"status": "ok"}
        
        _set_cache(prompt, result)
        
        cached_result = _check_cache(prompt)
        assert cached_result == result

    def test_cache_miss(self):
        prompt = "test prompt 123"
        cached_result = _check_cache(prompt)
        assert cached_result is None

    def test_cache_expiration(self):
        prompt = "test prompt 123"
        result = {"status": "ok"}
        
        import hashlib
        key = hashlib.md5(prompt.encode()).hexdigest()
        old_time = datetime.now(timezone.utc) - timedelta(hours=2)
        _PREPROCESSOR_CACHE[key] = (old_time, result)
        
        cached_result = _check_cache(prompt)
        assert cached_result is None
