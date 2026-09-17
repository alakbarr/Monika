import pytest
import pandas as pd
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock
from data_sources.vix_yfinance import VIXFetcher
from database.models import VIXData

class TestVIXFetcher:

    @pytest.mark.asyncio
    @patch('data_sources.vix_yfinance.VIXFetcher._download')
    async def test_fetch_success(self, mock_download):
        df = pd.DataFrame({"Close": [15.5]}, index=[pd.Timestamp('2024-01-01')])
        mock_download.return_value = df
        
        fetcher = VIXFetcher(AsyncMock())
        fetcher._save = AsyncMock(return_value=1)
        
        res = await fetcher.fetch()
        
        assert res == 1
        fetcher._save.assert_awaited_once_with(df)

    @pytest.mark.asyncio
    @patch('data_sources.vix_yfinance.VIXFetcher._download')
    async def test_fetch_empty(self, mock_download):
        mock_download.return_value = pd.DataFrame()
        
        fetcher = VIXFetcher(AsyncMock())
        
        res = await fetcher.fetch()
        
        assert res == 0

    @pytest.mark.asyncio
    @patch('data_sources.vix_yfinance.VIXFetcher._download')
    async def test_fetch_exception(self, mock_download):
        mock_download.side_effect = Exception("API down")
        
        fetcher = VIXFetcher(AsyncMock())
        
        res = await fetcher.fetch()
        
        assert res == 0

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
            mock_download.assert_called_once_with("^VIX", period="5d", progress=False, auto_adjust=True)
