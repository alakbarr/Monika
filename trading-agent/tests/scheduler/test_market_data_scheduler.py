import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from scheduler.market_data_scheduler import MarketDataScheduler


class TestMarketDataScheduler:

    @pytest.fixture
    def settings(self):
        return {
            "trading": {
                "asset_universe": ["XAUUSD", "BTCUSD"],
                "mt5": {"timeframes": ["M15", "H1", "H4", "D1"]},
                "schedule": {"market_data_sync_interval_seconds": 180},
                "indicators": {"rsi_period": 14},
            }
        }

    @pytest.mark.asyncio
    async def test_sync_now_success(self, settings):
        mock_mt5 = AsyncMock()
        mock_mt5.ensure_connected.return_value = True
        mock_mt5.fetch_and_save_all.return_value = {"XAUUSD/H1": 10, "BTCUSD/H1": 10}

        scheduler = MarketDataScheduler(settings=settings, mt5_client=mock_mt5)

        mock_session = AsyncMock()

        with patch("scheduler.market_data_scheduler.get_session") as mock_get_session, \
             patch("scheduler.market_data_scheduler.is_forex_market_closed", return_value=False), \
             patch("scheduler.market_data_scheduler.TechnicalIndicatorCalculator") as mock_calc_cls, \
             patch("scheduler.market_data_scheduler.MarketStructureAnalyzer") as mock_analyzer_cls:

            mock_get_session.return_value.__aenter__.return_value = mock_session

            mock_calc = AsyncMock()
            mock_calc.compute_all_symbols.return_value = {"XAUUSD/H1": 10}
            mock_calc_cls.return_value = mock_calc

            mock_analyzer = AsyncMock()
            mock_analyzer.analyze_all.return_value = {"XAUUSD": {"swings": 5}}
            mock_analyzer_cls.return_value = mock_analyzer

            res = await scheduler.sync_now()

            assert res["status"] == "success"
            mock_mt5.fetch_and_save_all.assert_awaited_once()
            mock_calc.compute_all_symbols.assert_awaited_once()
            mock_analyzer.analyze_all.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_sync_now_mt5_disconnected(self, settings):
        mock_mt5 = AsyncMock()
        mock_mt5.ensure_connected.return_value = False

        scheduler = MarketDataScheduler(settings=settings, mt5_client=mock_mt5)
        res = await scheduler.sync_now()

        assert res["status"] == "failed"
        assert res["reason"] == "mt5_disconnected"

    @pytest.mark.asyncio
    async def test_sync_now_no_mt5_client(self, settings):
        scheduler = MarketDataScheduler(settings=settings, mt5_client=None)
        res = await scheduler.sync_now()

        assert res["status"] == "skipped"
        assert res["reason"] == "no_mt5_client"

    @pytest.mark.asyncio
    async def test_sync_now_weekend_filters_crypto(self, settings):
        mock_mt5 = AsyncMock()
        mock_mt5.ensure_connected.return_value = True
        mock_mt5.fetch_and_save_all.return_value = {"BTCUSD/H1": 5}

        scheduler = MarketDataScheduler(settings=settings, mt5_client=mock_mt5)
        mock_session = AsyncMock()

        with patch("scheduler.market_data_scheduler.get_session") as mock_get_session, \
             patch("scheduler.market_data_scheduler.is_forex_market_closed", return_value=True), \
             patch("scheduler.market_data_scheduler.TechnicalIndicatorCalculator") as mock_calc_cls, \
             patch("scheduler.market_data_scheduler.MarketStructureAnalyzer") as mock_analyzer_cls:

            mock_get_session.return_value.__aenter__.return_value = mock_session

            mock_calc = AsyncMock()
            mock_calc.compute_all_symbols.return_value = {"BTCUSD/H1": 5}
            mock_calc_cls.return_value = mock_calc

            mock_analyzer = AsyncMock()
            mock_analyzer.analyze_all.return_value = {"BTCUSD": {"swings": 2}}
            mock_analyzer_cls.return_value = mock_analyzer

            res = await scheduler.sync_now()

            assert res["status"] == "success"
            # Pastikan hanya simbol crypto yang diambil saat weekend
            call_kwargs = mock_mt5.fetch_and_save_all.call_args[1]
            assert call_kwargs["symbols"] == ["BTCUSD"]

    def test_start_stop_lifecycle(self, settings):
        mock_mt5 = MagicMock()
        scheduler = MarketDataScheduler(settings=settings, mt5_client=mock_mt5)
        assert scheduler._running is False

        scheduler.stop()
        assert scheduler._running is False
