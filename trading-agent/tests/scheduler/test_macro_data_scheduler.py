import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from scheduler.macro_data_scheduler import MacroDataScheduler


class TestMacroDataScheduler:

    @pytest.fixture
    def settings(self):
        return {
            "trading": {
                "schedule": {"macro_data_refresh_minutes": 30},
            },
            "data_sources": {
                "fred": {"api_key": "dummy"},
                "cftc_cot": {"market": "all"},
            }
        }

    @pytest.mark.asyncio
    async def test_macro_data_scheduler_init(self, settings):
        scheduler = MacroDataScheduler(settings)
        assert scheduler.interval_minutes == 30.0
        assert scheduler._running is False

    @pytest.mark.asyncio
    async def test_refresh_macro_data_runs_sources(self, settings):
        scheduler = MacroDataScheduler(settings)

        with patch("scheduler.macro_data_scheduler.get_session") as mock_get_session:
            mock_session = AsyncMock()
            mock_get_session.return_value.__aenter__.return_value = mock_session

            with patch("data_sources.coinglass_funding.CoinglasFundingFetcher") as mock_coinglass_cls, \
                 patch("scrapers.sentiment.binance_sentiment.BinanceSentimentFetcher") as mock_binance_cls, \
                 patch("scrapers.sentiment.myfxbook_sentiment.MyFxBookSentimentFetcher") as mock_myfx_cls, \
                 patch("scrapers.sentiment.fxssi_sentiment.FXSSISentimentFetcher") as mock_fxssi_cls, \
                 patch("data_sources.vix_yfinance.VIXFetcher") as mock_vix_cls, \
                 patch("data_sources.fred_treasury_yield.FREDDataFetcher") as mock_fred_cls, \
                 patch("data_sources.cftc_cot.CFTCCOTFetcher") as mock_cftc_cls, \
                 patch("data_sources.dxy_yfinance.DXYFetcher") as mock_dxy_cls, \
                 patch("data_sources.bond_yields_fetcher.BondYieldFetcher") as mock_bond_cls, \
                 patch("data_sources.fear_greed.FearGreedFetcher") as mock_fg_cls, \
                 patch("data_sources.eia_oil_inventory.EIAInventoryFetcher") as mock_eia_cls:

                mock_cg = AsyncMock()
                mock_cg.fetch.return_value = {"funding_rate": 0.0001}
                mock_coinglass_cls.return_value = mock_cg

                mock_bn = AsyncMock()
                mock_bn.fetch.return_value = {"long_ratio": 0.65}
                mock_binance_cls.return_value = mock_bn

                mock_mf = AsyncMock()
                mock_mf.fetch.return_value = {"long_pct": 48}
                mock_myfx_cls.return_value = mock_mf

                mock_fx = AsyncMock()
                mock_fx.fetch.return_value = {"ratio": 52}
                mock_fxssi_cls.return_value = mock_fx

                mock_vix = AsyncMock()
                mock_vix.fetch.return_value = 5
                mock_vix_cls.return_value = mock_vix

                mock_fred = AsyncMock()
                mock_fred.fetch_all.return_value = {"saved": 3}
                mock_fred_cls.return_value = mock_fred

                mock_cftc = AsyncMock()
                mock_cftc.fetch_all.return_value = 8
                mock_cftc_cls.return_value = mock_cftc

                mock_dxy = AsyncMock()
                mock_dxy.fetch.return_value = 10
                mock_dxy_cls.return_value = mock_dxy

                mock_bond = AsyncMock()
                mock_bond.fetch.return_value = {"10y": 4.2}
                mock_bond_cls.return_value = mock_bond

                mock_fg = AsyncMock()
                mock_fg.fetch.return_value = {"current_value": 55, "classification": "Neutral"}
                mock_fg_cls.return_value = mock_fg

                mock_eia = AsyncMock()
                mock_eia.fetch.return_value = {"crude": -1.2}
                mock_eia_cls.return_value = mock_eia

                res = await scheduler.refresh_macro_data()

                assert "btc_funding" in res
                assert "binance_sentiment" in res
                assert "myfxbook_sentiment" in res
                assert "fxssi_sentiment" in res
                assert "vix" in res
                assert "fred" in res
                assert "cftc" in res
                assert "dxy" in res
                assert "bond_yields" in res
                assert "fear_greed" in res
                assert "eia_oil" in res
                assert res["vix"].get("saved") == 5
                assert res["dxy"].get("saved") == 10
                assert res["fear_greed"].get("value") == 55
                assert res["btc_funding"] == {"funding_rate": 0.0001}

    @pytest.mark.asyncio
    async def test_macro_data_scheduler_start_and_stop(self, settings):
        scheduler = MacroDataScheduler(settings)
        scheduler.refresh_macro_data = AsyncMock(return_value={"status": "ok"})

        task = asyncio.create_task(scheduler.start())
        await asyncio.sleep(0.01)
        assert scheduler._running is True
        scheduler.stop()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        assert scheduler._running is False
