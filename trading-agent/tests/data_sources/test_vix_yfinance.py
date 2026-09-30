# ==============================================================================
# File: tests/data_sources/test_vix_yfinance.py
# ==============================================================================

import pytest
import pandas as pd
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock
from data_sources.vix_yfinance import VIXFetcher
from database.models import VIXData


class TestVIXFetcher:

    @pytest.mark.asyncio
    @patch('data_sources.vix_yfinance.VIXFetcher._fetch_yahoo_direct')
    async def test_fetch_tier1_success(self, mock_tier1):
        """Tier 1 Yahoo Direct succeeds, saves data, no further tiers invoked."""
        df = pd.DataFrame({"Close": [15.5]}, index=[pd.Timestamp('2024-01-01', tz='UTC')])
        mock_tier1.return_value = df

        fetcher = VIXFetcher(AsyncMock())
        fetcher._save = AsyncMock(return_value=1)
        fetcher._fetch_cboe_cdn = AsyncMock()
        fetcher._fetch_fred = AsyncMock()
        fetcher._fetch_yfinance = AsyncMock()

        res = await fetcher.fetch()

        assert res == 1
        mock_tier1.assert_awaited_once_with("10d")
        fetcher._save.assert_awaited_once_with(df)
        fetcher._fetch_cboe_cdn.assert_not_called()
        fetcher._fetch_fred.assert_not_called()
        fetcher._fetch_yfinance.assert_not_called()

    @pytest.mark.asyncio
    @patch('data_sources.vix_yfinance.VIXFetcher._fetch_yahoo_direct')
    @patch('data_sources.vix_yfinance.VIXFetcher._fetch_cboe_cdn')
    async def test_fetch_tier2_cboe_fallback(self, mock_cboe, mock_yahoo):
        """Tier 1 fails, Tier 2 CBOE succeeds."""
        mock_yahoo.return_value = None
        df_cboe = pd.DataFrame({"Close": [16.2]}, index=[pd.Timestamp('2024-01-01', tz='UTC')])
        mock_cboe.return_value = df_cboe

        fetcher = VIXFetcher(AsyncMock())
        fetcher._save = AsyncMock(return_value=1)
        fetcher._fetch_fred = AsyncMock()
        fetcher._fetch_yfinance = AsyncMock()

        res = await fetcher.fetch(period="5d")

        assert res == 1
        mock_yahoo.assert_awaited_once_with("5d")
        mock_cboe.assert_awaited_once_with("5d")
        fetcher._save.assert_awaited_once_with(df_cboe)
        fetcher._fetch_fred.assert_not_called()
        fetcher._fetch_yfinance.assert_not_called()

    @pytest.mark.asyncio
    @patch('data_sources.vix_yfinance.VIXFetcher._fetch_yahoo_direct')
    @patch('data_sources.vix_yfinance.VIXFetcher._fetch_cboe_cdn')
    @patch('data_sources.vix_yfinance.VIXFetcher._fetch_fred')
    async def test_fetch_tier3_fred_fallback(self, mock_fred, mock_cboe, mock_yahoo):
        """Tier 1 & Tier 2 fail, Tier 3 FRED succeeds when fred_api_key is present."""
        mock_yahoo.return_value = None
        mock_cboe.return_value = None
        df_fred = pd.DataFrame({"Close": [14.8]}, index=[pd.Timestamp('2024-01-01', tz='UTC')])
        mock_fred.return_value = df_fred

        fetcher = VIXFetcher(AsyncMock(), fred_api_key="mock_key")
        fetcher._save = AsyncMock(return_value=1)
        fetcher._fetch_yfinance = AsyncMock()

        res = await fetcher.fetch(period="5d")

        assert res == 1
        mock_fred.assert_awaited_once_with("5d")
        fetcher._save.assert_awaited_once_with(df_fred)
        fetcher._fetch_yfinance.assert_not_called()

    @pytest.mark.asyncio
    @patch('data_sources.vix_yfinance.VIXFetcher._fetch_yahoo_direct')
    @patch('data_sources.vix_yfinance.VIXFetcher._fetch_cboe_cdn')
    @patch('data_sources.vix_yfinance.VIXFetcher._fetch_yfinance')
    async def test_fetch_tier4_yfinance_fallback(self, mock_yf, mock_cboe, mock_yahoo):
        """Tiers 1-3 fail, Tier 4 yfinance succeeds."""
        mock_yahoo.return_value = None
        mock_cboe.return_value = None
        df_yf = pd.DataFrame({"Close": [15.0]}, index=[pd.Timestamp('2024-01-01', tz='UTC')])
        mock_yf.return_value = df_yf

        fetcher = VIXFetcher(AsyncMock(), fred_api_key="")
        fetcher._save = AsyncMock(return_value=1)

        res = await fetcher.fetch()

        assert res == 1
        mock_yf.assert_awaited_once_with("10d")
        fetcher._save.assert_awaited_once_with(df_yf)

    @pytest.mark.asyncio
    @patch('data_sources.vix_yfinance.VIXFetcher._fetch_yahoo_direct')
    @patch('data_sources.vix_yfinance.VIXFetcher._fetch_cboe_cdn')
    @patch('data_sources.vix_yfinance.VIXFetcher._fetch_yfinance')
    async def test_fetch_all_tiers_failed(self, mock_yf, mock_cboe, mock_yahoo):
        """All tiers fail gracefully returning 0 without raising exceptions."""
        mock_yahoo.return_value = None
        mock_cboe.return_value = None
        mock_yf.return_value = None

        fetcher = VIXFetcher(AsyncMock(), fred_api_key="")
        fetcher._save = AsyncMock()

        res = await fetcher.fetch()

        assert res == 0
        fetcher._save.assert_not_called()

    @pytest.mark.asyncio
    @patch('data_sources.vix_yfinance.fetch_with_retry')
    async def test_fetch_yahoo_direct_parsing(self, mock_http):
        """Test parsing of direct Yahoo Finance chart v8 json payload."""
        mock_http.return_value = {
            "chart": {
                "result": [{
                    "timestamp": [1704067200, 1704153600],
                    "indicators": {
                        "quote": [{
                            "close": [14.5, 15.2]
                        }]
                    }
                }]
            }
        }
        fetcher = VIXFetcher(AsyncMock())
        df = await fetcher._fetch_yahoo_direct("5d")

        assert df is not None
        assert len(df) == 2
        assert "Close" in df.columns
        assert df["Close"].iloc[0] == 14.5
        assert df["Close"].iloc[1] == 15.2

    @pytest.mark.asyncio
    @patch('data_sources.vix_yfinance.fetch_with_retry')
    async def test_fetch_cboe_cdn_parsing(self, mock_http):
        """Test parsing of CBOE daily price CSV."""
        mock_http.return_value = (
            "DATE,OPEN,HIGH,LOW,CLOSE\n"
            "09/24/2026,15.83,16.57,15.34,15.67\n"
            "09/25/2026,15.61,15.94,14.68,14.87\n"
        )
        fetcher = VIXFetcher(AsyncMock())
        df = await fetcher._fetch_cboe_cdn("5d")

        assert df is not None
        assert len(df) == 2
        assert "Close" in df.columns
        assert df["Close"].iloc[-1] == 14.87

    @pytest.mark.asyncio
    @patch('data_sources.vix_yfinance.fetch_with_retry')
    async def test_fetch_fred_parsing(self, mock_http):
        """Test parsing of FRED VIXCLS series json."""
        mock_http.return_value = {
            "observations": [
                {"date": "2026-09-25", "value": "14.87"},
                {"date": "2026-09-24", "value": "15.67"},
                {"date": "2026-09-23", "value": "."},  # Holiday / missing
            ]
        }
        fetcher = VIXFetcher(AsyncMock(), fred_api_key="mock_key")
        df = await fetcher._fetch_fred("5d")

        assert df is not None
        assert len(df) == 2
        assert df["Close"].iloc[0] == 14.87
        assert df["Close"].iloc[1] == 15.67

    @pytest.mark.asyncio
    async def test_save_new(self):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        df = pd.DataFrame({"Close": [20.0]}, index=[pd.Timestamp('2024-01-01')])
        
        fetcher = VIXFetcher(mock_session)
        res = await fetcher._save(df)
        
        assert res == 1
        mock_session.add.assert_called_once()
        args, _ = mock_session.add.call_args
        assert isinstance(args[0], VIXData)
        assert args[0].close == 20.0
        assert args[0].date == datetime(2024, 1, 1, tzinfo=timezone.utc)
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_save_existing(self):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = 1  # Exists
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        df = pd.DataFrame({"Close": [20.0]}, index=[pd.Timestamp('2024-01-01')])
        
        fetcher = VIXFetcher(mock_session)
        res = await fetcher._save(df)
        
        assert res == 0
        mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_latest(self):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_result = MagicMock()
        
        row = VIXData(date=datetime(2024, 1, 1, tzinfo=timezone.utc), close=18.5)
        mock_result.scalar_one_or_none.return_value = row
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        fetcher = VIXFetcher(mock_session)
        res = await fetcher.get_latest()
        
        assert res["close"] == 18.5
        assert res["date"] == datetime(2024, 1, 1, tzinfo=timezone.utc)

    @pytest.mark.asyncio
    async def test_get_latest_none(self):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        fetcher = VIXFetcher(mock_session)
        res = await fetcher.get_latest()
        
        assert res is None

    def test_download(self):
        with patch('data_sources.vix_yfinance.yf.download') as mock_download:
            mock_download.return_value = pd.DataFrame()
            fetcher = VIXFetcher(AsyncMock())
            fetcher._download("5d")
            mock_download.assert_called_once_with("^VIX", period="5d", progress=False, auto_adjust=True, timeout=8)

    @pytest.mark.asyncio
    async def test_save_existing_via_scalars(self):
        """Verify deduplication works with SQLAlchemy scalars().all() result."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()

        mock_result = MagicMock()
        existing_dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
        mock_result.scalars.return_value.all.return_value = [existing_dt]
        mock_session.execute = AsyncMock(return_value=mock_result)

        df = pd.DataFrame({"Close": [20.0]}, index=[pd.Timestamp('2024-01-01')])

        fetcher = VIXFetcher(mock_session)
        res = await fetcher._save(df)

        assert res == 0
        mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_save_partial_existing(self):
        """Verify that existing dates are skipped while new dates are inserted."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()

        mock_result = MagicMock()
        existing_dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
        mock_result.scalars.return_value.all.return_value = [existing_dt]
        mock_session.execute = AsyncMock(return_value=mock_result)

        df = pd.DataFrame({
            "Close": [20.0, 21.5]
        }, index=[
            pd.Timestamp('2024-01-01'),
            pd.Timestamp('2024-01-02')
        ])

        fetcher = VIXFetcher(mock_session)
        res = await fetcher._save(df)

        assert res == 1
        mock_session.add.assert_called_once()
        saved_record = mock_session.add.call_args[0][0]
        assert saved_record.date == datetime(2024, 1, 2, tzinfo=timezone.utc)
        assert saved_record.close == 21.5

    @pytest.mark.asyncio
    async def test_save_duplicate_in_dataframe(self):
        """Verify that duplicate rows within the same DataFrame are deduplicated."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        df = pd.DataFrame({
            "Close": [20.0, 20.5]
        }, index=[
            pd.Timestamp('2024-01-01'),
            pd.Timestamp('2024-01-01')
        ])

        fetcher = VIXFetcher(mock_session)
        res = await fetcher._save(df)

        assert res == 1
        mock_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_commit_failure_returns_zero(self):
        """Verify that when safe_commit fails, _save returns 0."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        df = pd.DataFrame({"Close": [20.0]}, index=[pd.Timestamp('2024-01-01')])

        with patch("database.safe_ops.safe_commit", new_callable=AsyncMock) as mock_safe_commit:
            mock_safe_commit.return_value = False
            fetcher = VIXFetcher(mock_session)
            res = await fetcher._save(df)

            assert res == 0

