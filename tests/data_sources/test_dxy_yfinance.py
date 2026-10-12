import asyncio
import pytest
import pandas as pd
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock
from tests.conftest import create_mock_async_session
from data_sources.dxy_yfinance import DXYFetcher
from database.models import DXYData

class TestDXYFetcher:

    @pytest.mark.asyncio
    @patch('data_sources.dxy_yfinance.DXYFetcher._fetch_yahoo_direct')
    async def test_fetch_tier1_success(self, mock_direct):
        df = pd.DataFrame({"Close": [100.5]}, index=[pd.Timestamp('2024-01-01', tz='UTC')])
        mock_direct.return_value = df
        
        fetcher = DXYFetcher(MagicMock())
        fetcher._save = AsyncMock(return_value=1)
        fetcher._fetch_yfinance = AsyncMock()
        
        res = await fetcher.fetch()
        
        assert res == 1
        mock_direct.assert_awaited_once_with("10d")
        fetcher._save.assert_awaited_once_with(df)
        fetcher._fetch_yfinance.assert_not_called()

    @pytest.mark.asyncio
    @patch('data_sources.dxy_yfinance.DXYFetcher._fetch_yahoo_direct')
    @patch('data_sources.dxy_yfinance.DXYFetcher._fetch_yfinance')
    async def test_fetch_tier2_yfinance_fallback(self, mock_yf, mock_direct):
        mock_direct.return_value = None
        df_yf = pd.DataFrame({"Close": [101.2]}, index=[pd.Timestamp('2024-01-01', tz='UTC')])
        mock_yf.return_value = df_yf

        fetcher = DXYFetcher(MagicMock())
        fetcher._save = AsyncMock(return_value=1)

        res = await fetcher.fetch(period="5d")

        assert res == 1
        mock_direct.assert_awaited_once_with("5d")
        mock_yf.assert_awaited_once_with("5d")
        fetcher._save.assert_awaited_once_with(df_yf)

    @pytest.mark.asyncio
    @patch('data_sources.dxy_yfinance.DXYFetcher._fetch_yahoo_direct')
    @patch('data_sources.dxy_yfinance.DXYFetcher._fetch_yfinance')
    async def test_fetch_empty(self, mock_yf, mock_direct):
        mock_direct.return_value = None
        mock_yf.return_value = pd.DataFrame()
        
        fetcher = DXYFetcher(MagicMock())
        
        res = await fetcher.fetch()
        
        assert res == 0

    @pytest.mark.asyncio
    @patch('data_sources.dxy_yfinance.DXYFetcher._fetch_yahoo_direct')
    @patch('data_sources.dxy_yfinance.DXYFetcher._fetch_yfinance')
    async def test_fetch_all_tiers_failed(self, mock_yf, mock_direct):
        mock_direct.return_value = None
        mock_yf.return_value = None
        
        fetcher = DXYFetcher(MagicMock())
        
        res = await fetcher.fetch()
        
        assert res == 0

    @pytest.mark.asyncio
    @patch('data_sources.dxy_yfinance.fetch_with_retry')
    async def test_fetch_yahoo_direct_success(self, mock_fetch):
        mock_fetch.return_value = {
            "chart": {
                "result": [{
                    "timestamp": [1704067200, 1704153600],
                    "indicators": {
                        "quote": [{
                            "close": [101.5, 102.0]
                        }]
                    }
                }]
            }
        }
        fetcher = DXYFetcher(MagicMock())
        df = await fetcher._fetch_yahoo_direct("10d")

        assert df is not None
        assert len(df) == 2
        assert list(df["Close"]) == [101.5, 102.0]
        assert df.index[0] == pd.to_datetime(1704067200, unit="s", utc=True)

    @pytest.mark.asyncio
    @patch('data_sources.dxy_yfinance.fetch_with_retry')
    async def test_fetch_yahoo_direct_missing_data(self, mock_fetch):
        mock_fetch.return_value = {"chart": {"result": []}}
        fetcher = DXYFetcher(MagicMock())
        df = await fetcher._fetch_yahoo_direct("10d")
        assert df is None

    @pytest.mark.asyncio
    @patch('data_sources.dxy_yfinance.fetch_with_retry')
    async def test_fetch_yahoo_direct_http_error(self, mock_fetch):
        mock_fetch.side_effect = Exception("Connection timeout")
        fetcher = DXYFetcher(MagicMock())
        df = await fetcher._fetch_yahoo_direct("10d")
        assert df is None

    @pytest.mark.asyncio
    async def test_fetch_yfinance_timeout(self):
        fetcher = DXYFetcher(MagicMock())
        async def mock_wait_for(coro, timeout):
            if hasattr(coro, "close"):
                coro.close()
            raise asyncio.TimeoutError()

        with patch('asyncio.wait_for', side_effect=mock_wait_for):
            df = await fetcher._fetch_yfinance("10d")
            assert df is None

    @pytest.mark.asyncio
    async def test_fetch_yfinance_exception(self):
        fetcher = DXYFetcher(MagicMock())
        with patch('asyncio.to_thread', side_effect=Exception("Crash")):
            df = await fetcher._fetch_yfinance("10d")
            assert df is None

    def test_download(self):
        with patch('data_sources.dxy_yfinance.yf.download') as mock_download:
            mock_download.return_value = pd.DataFrame()
            fetcher = DXYFetcher(MagicMock())
            fetcher._download("5d")
            mock_download.assert_called_once_with("DX-Y.NYB", period="5d", progress=False, auto_adjust=True, timeout=8)

    @pytest.mark.asyncio
    async def test_save_existing_via_scalars(self):
        """Verify deduplication works with SQLAlchemy scalars().all() result."""
        mock_session = create_mock_async_session()

        mock_result = MagicMock()
        existing_dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
        mock_result.scalars.return_value.all.return_value = [existing_dt]
        mock_session.execute = AsyncMock(return_value=mock_result)

        df = pd.DataFrame({"Close": [105.0]}, index=[pd.Timestamp('2024-01-01')])

        fetcher = DXYFetcher(mock_session)
        res = await fetcher._save(df)

        assert res == 0
        mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_save_partial_existing(self):
        """Verify that existing dates are skipped while new dates are inserted."""
        mock_session = create_mock_async_session()

        mock_result = MagicMock()
        existing_dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
        mock_result.scalars.return_value.all.return_value = [existing_dt]
        mock_session.execute = AsyncMock(return_value=mock_result)

        df = pd.DataFrame({
            "Close": [105.0, 106.5]
        }, index=[
            pd.Timestamp('2024-01-01'),
            pd.Timestamp('2024-01-02')
        ])

        fetcher = DXYFetcher(mock_session)
        res = await fetcher._save(df)

        assert res == 1
        mock_session.add.assert_called_once()
        saved_record = mock_session.add.call_args[0][0]
        assert saved_record.date == datetime(2024, 1, 2, tzinfo=timezone.utc)
        assert saved_record.close == 106.5

    @pytest.mark.asyncio
    async def test_save_duplicate_in_dataframe(self):
        """Verify that duplicate rows within the same DataFrame are deduplicated."""
        mock_session = MagicMock()
        mock_session.add = MagicMock()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        df = pd.DataFrame({
            "Close": [105.0, 105.5]
        }, index=[
            pd.Timestamp('2024-01-01'),
            pd.Timestamp('2024-01-01')
        ])

        fetcher = DXYFetcher(mock_session)
        res = await fetcher._save(df)

        assert res == 1
        mock_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_commit_failure_returns_zero(self):
        """Verify that when safe_commit fails, _save returns 0."""
        mock_session = MagicMock()
        mock_session.add = MagicMock()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        df = pd.DataFrame({"Close": [105.0]}, index=[pd.Timestamp('2024-01-01')])

        with patch("database.safe_ops.safe_commit", new_callable=AsyncMock) as mock_safe_commit:
            mock_safe_commit.return_value = False
            fetcher = DXYFetcher(mock_session)
            res = await fetcher._save(df)

            assert res == 0

