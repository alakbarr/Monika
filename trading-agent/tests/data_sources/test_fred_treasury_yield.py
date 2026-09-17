import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone
from data_sources.fred_treasury_yield import FREDDataFetcher
from database.models import TreasuryYield, InterestRate

class TestFREDDataFetcher:

    @pytest.mark.asyncio
    async def test_fetch_all_no_key(self):
        fetcher = FREDDataFetcher(AsyncMock(), {}, api_key="")
        res = await fetcher.fetch_all()
        assert res == {"treasury": 0, "interest_rates": 0}

    @pytest.mark.asyncio
    async def test_fetch_all_success(self):
        config = {
            "series": {
                "2Y Treasury": "DGS2",
                "Fed Funds": "FEDFUNDS",
                "Unknown": "UNKNOWN"
            }
        }
        fetcher = FREDDataFetcher(AsyncMock(), config, api_key="test")
        
        fetcher._fetch_treasury_series = AsyncMock(return_value=2)
        fetcher._fetch_interest_rate = AsyncMock(return_value=1)
        
        res = await fetcher.fetch_all()
        
        assert res == {"treasury": 2, "interest_rates": 1}
        fetcher._fetch_treasury_series.assert_awaited_once_with("DGS2", "2Y")
        fetcher._fetch_interest_rate.assert_awaited_once_with("FEDFUNDS", "FED")

    @pytest.mark.asyncio
    async def test_fetch_treasury_series(self):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        fetcher = FREDDataFetcher(mock_session, {}, api_key="test")
        
        fetcher._call_fred = AsyncMock(return_value=[
            {"date": "2024-01-01", "value": "4.5"},
            {"date": "2024-01-02", "value": "."}  # missing data
        ])
        
        res = await fetcher._fetch_treasury_series("DGS2", "2Y")
        
        assert res == 1
        mock_session.add.assert_called_once()
        args, _ = mock_session.add.call_args
        assert isinstance(args[0], TreasuryYield)
        assert args[0].tenor == "2Y"
        assert args[0].yield_percent == 4.5
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_fetch_interest_rate(self):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        fetcher = FREDDataFetcher(mock_session, {}, api_key="test")
        
        fetcher._call_fred = AsyncMock(return_value=[
            {"date": "2024-01-01", "value": "5.25"}
        ])
        
        res = await fetcher._fetch_interest_rate("FEDFUNDS", "FED")
        
        assert res == 1
        mock_session.add.assert_called_once()
        args, _ = mock_session.add.call_args
        assert isinstance(args[0], InterestRate)
        assert args[0].bank == "FED"
        assert args[0].rate_percent == 5.25
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    @patch('data_sources.fred_treasury_yield.fetch_with_retry')
    async def test_call_fred(self, mock_fetch):
        mock_fetch.return_value = {"observations": [{"date": "2024-01-01", "value": "1.0"}]}
        
        fetcher = FREDDataFetcher(AsyncMock(), {}, api_key="test")
        res = await fetcher._call_fred("DGS2", limit=5)
        
        assert len(res) == 1
        assert res[0]["value"] == "1.0"
        
        mock_fetch.assert_awaited_once()
        args, kwargs = mock_fetch.call_args
        assert kwargs["params"]["series_id"] == "DGS2"
        assert kwargs["params"]["limit"] == "5"

    def test_parse_date(self):
        dt = FREDDataFetcher._parse_date("2024-05-15")
        assert dt.year == 2024
        assert dt.month == 5
        assert dt.day == 15
        assert dt.tzinfo == timezone.utc
        
        # invalid date
        dt = FREDDataFetcher._parse_date("invalid")
        assert dt is None

    @pytest.mark.asyncio
    async def test_fetch_treasury_series_handles_nd_gracefully(self):
        """M-10: Guard float conversions when FRED returns 'ND' or empty string."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        fetcher = FREDDataFetcher(mock_session, {}, api_key="test")
        fetcher._call_fred = AsyncMock(return_value=[
            {"date": "2024-01-01", "value": "ND"},
            {"date": "2024-01-02", "value": "."},
            {"date": "2024-01-03", "value": ""},
            {"date": "2024-01-04", "value": "4.25"},
        ])

        res = await fetcher._fetch_treasury_series("DGS10", "10Y")
        assert res == 1
        mock_session.add.assert_called_once()
        args, _ = mock_session.add.call_args
        assert args[0].yield_percent == 4.25

    @pytest.mark.asyncio
    async def test_fetch_interest_rate_handles_nd_gracefully(self):
        """M-10: Guard float conversions in interest rates when FRED returns 'ND'."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()

        fetcher = FREDDataFetcher(mock_session, {}, api_key="test")
        fetcher._call_fred = AsyncMock(return_value=[
            {"date": "2024-01-01", "value": "ND"}
        ])

        res = await fetcher._fetch_interest_rate("FEDFUNDS", "FED")
        assert res == 0
        mock_session.add.assert_not_called()


