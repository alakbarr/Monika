import pytest
import pandas as pd
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock
from data_sources.dxy_yfinance import DXYFetcher
from database.models import DXYData

class TestDXYFetcher:

    @pytest.mark.asyncio
    @patch('data_sources.dxy_yfinance.DXYFetcher._download')
    async def test_fetch_success(self, mock_download):
        df = pd.DataFrame({"Close": [100.5]}, index=[pd.Timestamp('2024-01-01')])
        mock_download.return_value = df
        
        fetcher = DXYFetcher(AsyncMock())
        fetcher._save = AsyncMock(return_value=1)
        
        res = await fetcher.fetch()
        
        assert res == 1
        fetcher._save.assert_awaited_once_with(df)

    @pytest.mark.asyncio
    @patch('data_sources.dxy_yfinance.DXYFetcher._download')
    async def test_fetch_empty(self, mock_download):
        mock_download.return_value = pd.DataFrame()
        
        fetcher = DXYFetcher(AsyncMock())
        
        res = await fetcher.fetch()
        
        assert res == 0

    @pytest.mark.asyncio
    @patch('data_sources.dxy_yfinance.DXYFetcher._download')
    async def test_fetch_exception(self, mock_download):
        mock_download.side_effect = Exception("API down")
        
        fetcher = DXYFetcher(AsyncMock())
        
        res = await fetcher.fetch()
        
        assert res == 0

    @pytest.mark.asyncio
    async def test_save_new(self):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        df = pd.DataFrame({"Close": [105.0]}, index=[pd.Timestamp('2024-01-01')])
        
        fetcher = DXYFetcher(mock_session)
        res = await fetcher._save(df)
        
        assert res == 1
        mock_session.add.assert_called_once()
        args, _ = mock_session.add.call_args
        assert isinstance(args[0], DXYData)
        assert args[0].close == 105.0
        assert args[0].date == datetime(2024, 1, 1, tzinfo=timezone.utc)
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_save_existing(self):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = 1  # Exists
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        df = pd.DataFrame({"Close": [105.0]}, index=[pd.Timestamp('2024-01-01')])
        
        fetcher = DXYFetcher(mock_session)
        res = await fetcher._save(df)
        
        assert res == 0
        mock_session.add.assert_not_called()

    def test_download(self):
        with patch('data_sources.dxy_yfinance.yf.download') as mock_download:
            mock_download.return_value = pd.DataFrame()
            fetcher = DXYFetcher(AsyncMock())
            fetcher._download("5d")
            mock_download.assert_called_once_with("DX-Y.NYB", period="5d", progress=False, auto_adjust=True)
