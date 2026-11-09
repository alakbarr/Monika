from tests.conftest import create_mock_async_session
import pytest
import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch
from monika.application.analysis.prefetch.macro_preprocessor import (
    MacroPreprocessor,
    _check_cache,
    _set_cache,
    _PREPROCESSOR_CACHE,
)
from monika.infrastructure.database.models import COTReport, TechnicalIndicator, EconomicCalendar, SystemConfig
from datetime import datetime, timezone, timedelta


class TestMacroPreprocessor:
    @pytest.fixture
    def preprocessor(self):
        from monika.core.config.settings import load_all_config

        settings = load_all_config()
        return MacroPreprocessor(api_key="test_key", settings=settings)

    @pytest.mark.asyncio
    async def _ignore_test_compute_cot_signals(self, preprocessor):
        session = create_mock_async_session()
        session.add = MagicMock()

        # Mock DB response
        report = COTReport(
            market_code="088691", asset_mgr_long=100, asset_mgr_short=50, leveraged_long=200, leveraged_short=10
        )
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
        session = create_mock_async_session()
        session.add = MagicMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result

        res = await preprocessor.compute_cot_signals(session)
        assert res == {}

    @pytest.mark.asyncio
    async def _ignore_test_compute_indicator_signals(self, preprocessor):
        session = create_mock_async_session()
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
        session = create_mock_async_session()
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
        session = create_mock_async_session()
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
    async def test_compute_surprise_summary_handles_offset_naive_datetime(self, preprocessor):
        session = create_mock_async_session()
        naive_dt = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=2)
        event = EconomicCalendar(
            currency="USD", event_name="NFP", impact="high", surprise_score=2.5, event_time=naive_dt
        )
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [event]
        session.execute.return_value = mock_result

        res = await preprocessor.compute_surprise_summary(session)
        assert "USD" in res
        assert res["USD"]["score"] > 0
        assert res["USD"]["trend"] == "positive"

    @pytest.mark.asyncio
    @patch("monika.application.analysis.prefetch.macro_preprocessor.datetime")
    async def _ignore_test_run_all_and_save_insert(self, mock_datetime, preprocessor):
        mock_now = MagicMock()
        mock_now.isoformat.return_value = "2023-01-01T00:00:00Z"
        mock_datetime.now.return_value = mock_now

        session = create_mock_async_session()
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
        assert added_config.value is not None

        saved_val = json.loads(added_config.value)
        assert saved_val["cot_signals"] == {"cot": 1}
        assert saved_val["indicator_signals"] == {"ind": 2}
        assert saved_val["surprise_summary"] == {"sur": 3}
        assert saved_val["computed_at"] == "2023-01-01T00:00:00Z"

        session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_cot_signals_no_duplicate_processing(self, preprocessor, caplog):
        from monika.infrastructure.database.models import PriceOHLCV

        session = create_mock_async_session()
        # Mock 5 D1 bars with -6.0% move (from 100.0 down to 94.0)
        bars = [
            PriceOHLCV(symbol="XTIUSD", timeframe="D1", close=94.0),
            PriceOHLCV(symbol="XTIUSD", timeframe="D1", close=95.0),
            PriceOHLCV(symbol="XTIUSD", timeframe="D1", close=97.0),
            PriceOHLCV(symbol="XTIUSD", timeframe="D1", close=99.0),
            PriceOHLCV(symbol="XTIUSD", timeframe="D1", close=100.0),
        ]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = bars
        session.execute = AsyncMock(return_value=mock_result)

        cot_signals = {
            "067651": {
                "signal": "bullish",
                "symbol": "XTIUSD",
                "market_code": "067651",
            },
            "XTIUSD": {
                "signal": "bullish",
                "symbol": "XTIUSD",
                "market_code": "067651",
            },
        }

        with caplog.at_level(logging.INFO):
            validated = await preprocessor._validate_cot_signals_against_price(session, cot_signals)

        # Ensure single DB execute for XTIUSD
        assert session.execute.call_count == 1

        # Both keys must have identical low-confidence metadata
        assert validated["067651"]["_confidence"] == "low"
        assert validated["XTIUSD"]["_confidence"] == "low"
        assert validated["067651"]["_conflict"] is True
        assert validated["XTIUSD"]["_conflict"] is True
        assert validated["067651"]["_price_change_5d"] == -0.06
        assert validated["XTIUSD"]["_price_change_5d"] == -0.06

        # Zero WARNING logs
        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warnings) == 0

        # Divergence logged exactly once at INFO
        divergence_logs = [r for r in caplog.records if "COT divergence for XTIUSD" in r.message]
        assert len(divergence_logs) == 1
        assert divergence_logs[0].levelno == logging.INFO

    @pytest.mark.asyncio
    async def test_validate_cot_signals_inverted_pairs_consistency(self, preprocessor):
        from monika.infrastructure.database.models import PriceOHLCV

        session = create_mock_async_session()
        # USDJPY price rises +1.5% (from 150.0 to 152.25)
        bullish_bars = [
            PriceOHLCV(symbol="USDJPY", timeframe="D1", close=152.25),
            PriceOHLCV(symbol="USDJPY", timeframe="D1", close=151.5),
            PriceOHLCV(symbol="USDJPY", timeframe="D1", close=151.0),
            PriceOHLCV(symbol="USDJPY", timeframe="D1", close=150.5),
            PriceOHLCV(symbol="USDJPY", timeframe="D1", close=150.0),
        ]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = bullish_bars
        session.execute = AsyncMock(return_value=mock_result)

        cot_signals = {
            "097741": {
                "signal": "bullish",
                "symbol": "USDJPY",
                "market_code": "097741",
                "pair_signal": "bearish",
            },
            "USDJPY": {
                "signal": "bearish",
                "symbol": "USDJPY",
                "market_code": "097741",
                "pair_signal": "bearish",
            },
        }

        # Pair bias is bearish, but price rose +1.5% -> conflict
        val = await preprocessor._validate_cot_signals_against_price(session, cot_signals)
        assert val["097741"]["_confidence"] == "low"
        assert val["USDJPY"]["_confidence"] == "low"
        assert val["097741"]["_conflict"] is True
        assert val["USDJPY"]["_conflict"] is True
        assert "bearish" in val["097741"]["_conflict_detail"]

        # Now test aligned case: USDJPY price falls -1.5% (from 150.0 to 147.75)
        bearish_bars = [
            PriceOHLCV(symbol="USDJPY", timeframe="D1", close=147.75),
            PriceOHLCV(symbol="USDJPY", timeframe="D1", close=148.5),
            PriceOHLCV(symbol="USDJPY", timeframe="D1", close=149.0),
            PriceOHLCV(symbol="USDJPY", timeframe="D1", close=149.5),
            PriceOHLCV(symbol="USDJPY", timeframe="D1", close=150.0),
        ]
        mock_result.scalars.return_value.all.return_value = bearish_bars
        val2 = await preprocessor._validate_cot_signals_against_price(session, cot_signals)
        assert val2["097741"]["_confidence"] == "high"
        assert val2["USDJPY"]["_confidence"] == "high"
        assert val2["097741"]["_conflict"] is False
        assert val2["USDJPY"]["_conflict"] is False

    @pytest.mark.asyncio
    async def test_validate_cot_signals_adaptive_thresholds(self, preprocessor):
        from monika.infrastructure.database.models import PriceOHLCV

        session = create_mock_async_session()
        # BTC moves -2.0% (from 80,000 to 78,400) -> within crypto 3.5% threshold
        bars_small = [
            PriceOHLCV(symbol="BTCUSD", timeframe="D1", close=78400.0),
            PriceOHLCV(symbol="BTCUSD", timeframe="D1", close=79000.0),
            PriceOHLCV(symbol="BTCUSD", timeframe="D1", close=79500.0),
            PriceOHLCV(symbol="BTCUSD", timeframe="D1", close=80000.0),
            PriceOHLCV(symbol="BTCUSD", timeframe="D1", close=80000.0),
        ]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = bars_small
        session.execute = AsyncMock(return_value=mock_result)

        cot_signals = {
            "BTCUSD": {"signal": "bullish", "symbol": "BTCUSD", "market_code": "133741"},
        }
        val = await preprocessor._validate_cot_signals_against_price(session, cot_signals)
        assert val["BTCUSD"]["_confidence"] == "high"
        assert val["BTCUSD"]["_conflict"] is False

        # BTC moves -5.0% (from 80,000 to 76,000) -> exceeds crypto 3.5% threshold
        bars_large = [
            PriceOHLCV(symbol="BTCUSD", timeframe="D1", close=76000.0),
            PriceOHLCV(symbol="BTCUSD", timeframe="D1", close=77000.0),
            PriceOHLCV(symbol="BTCUSD", timeframe="D1", close=78000.0),
            PriceOHLCV(symbol="BTCUSD", timeframe="D1", close=79000.0),
            PriceOHLCV(symbol="BTCUSD", timeframe="D1", close=80000.0),
        ]
        mock_result.scalars.return_value.all.return_value = bars_large
        val2 = await preprocessor._validate_cot_signals_against_price(session, cot_signals)
        assert val2["BTCUSD"]["_confidence"] == "low"
        assert val2["BTCUSD"]["_conflict"] is True


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
