import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone
from data_sources.cftc_cot import CFTCCOTFetcher, DISAGGREGATED_URL, FINANCIAL_URL
from database.models import COTReport


class TestCFTCCOTFetcher:

    @pytest.mark.asyncio
    async def test_fetch_all_empty(self):
        fetcher = CFTCCOTFetcher(AsyncMock(), {})
        res = await fetcher.fetch_all()
        assert res == 0

    @pytest.mark.asyncio
    async def test_fetch_all_routing_and_code_query(self):
        config = {
            "markets": {
                "gold": "088691",          # commodity
                "british_pound": "096742", # financial
            }
        }
        fetcher = CFTCCOTFetcher(AsyncMock(), config)
        fetcher._fetch_and_save = AsyncMock(return_value=1)

        res = await fetcher.fetch_all()

        assert res == 2
        assert fetcher._fetch_and_save.call_count == 2

        # Check call 1: Gold (commodity) -> DISAGGREGATED_URL with contract code query
        call1 = fetcher._fetch_and_save.call_args_list[0]
        assert call1.args[0] == DISAGGREGATED_URL
        assert call1.args[1] == {
            "$where": "cftc_contract_market_code='088691'",
            "$order": "report_date_as_yyyy_mm_dd DESC",
            "$limit": "52",
        }
        assert call1.args[2] == "gold"
        assert call1.args[3] == "088691"

        # Check call 2: GBP (financial) -> FINANCIAL_URL with contract code query
        call2 = fetcher._fetch_and_save.call_args_list[1]
        assert call2.args[0] == FINANCIAL_URL
        assert call2.args[1] == {
            "$where": "cftc_contract_market_code='096742'",
            "$order": "report_date_as_yyyy_mm_dd DESC",
            "$limit": "52",
        }
        assert call2.args[2] == "british_pound"
        assert call2.args[3] == "096742"

    @pytest.mark.asyncio
    @patch('data_sources.cftc_cot.fetch_with_retry')
    async def test_fetch_and_save_tff_forex(self, mock_fetch):
        # Sample response from gpe5-46if for British Pound
        mock_fetch.return_value = [{
            "report_date_as_yyyy_mm_dd": "2026-08-18T00:00:00.000",
            "cftc_contract_market_code": "096742",
            "dealer_positions_long_all": "133730",
            "dealer_positions_short_all": "65165",
            "asset_mgr_positions_long": "33516",
            "asset_mgr_positions_short": "150756",
            "lev_money_positions_long": "70821",
            "lev_money_positions_short": "27944"
        }]

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        fetcher = CFTCCOTFetcher(mock_session, {})
        res = await fetcher._fetch_and_save(
            url=FINANCIAL_URL,
            params={"$where": "cftc_contract_market_code='096742'"},
            market_name="british_pound",
            market_code="096742"
        )

        assert res == 1
        mock_session.add.assert_called_once()
        saved_record = mock_session.add.call_args[0][0]
        assert isinstance(saved_record, COTReport)
        assert saved_record.market_code == "096742"
        assert saved_record.leveraged_long == 70821
        assert saved_record.leveraged_short == 27944
        assert saved_record.asset_mgr_long == 33516
        assert saved_record.asset_mgr_short == 150756
        assert saved_record.dealer_long == 133730
        assert saved_record.dealer_short == 65165

    @pytest.mark.asyncio
    @patch('data_sources.cftc_cot.fetch_with_retry')
    async def test_fetch_and_save_commodity_managed_money(self, mock_fetch):
        # Sample response from kh3c-gbw2 for Gold
        mock_fetch.return_value = [{
            "report_date_as_yyyy_mm_dd": "2026-08-18T00:00:00.000",
            "cftc_contract_market_code": "088691",
            "swap_positions_long_all": "17590",
            "swap__positions_short_all": "246615",
            "other_rept_positions_long": "95430",
            "other_rept_positions_short": "21857",
            "m_money_positions_long_all": "157173",
            "m_money_positions_short_all": "11251"
        }]

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        fetcher = CFTCCOTFetcher(mock_session, {})
        res = await fetcher._fetch_and_save(
            url=DISAGGREGATED_URL,
            params={"$where": "cftc_contract_market_code='088691'"},
            market_name="gold",
            market_code="088691"
        )

        assert res == 1
        mock_session.add.assert_called_once()
        saved_record = mock_session.add.call_args[0][0]
        assert isinstance(saved_record, COTReport)
        assert saved_record.market_code == "088691"
        assert saved_record.leveraged_long == 157173
        assert saved_record.leveraged_short == 11251
        assert saved_record.dealer_long == 17590
        assert saved_record.dealer_short == 246615
        assert saved_record.asset_mgr_long == 95430
        assert saved_record.asset_mgr_short == 21857

    @pytest.mark.asyncio
    @patch('data_sources.cftc_cot.fetch_with_retry')
    async def test_fetch_and_save_existing_duplicate(self, mock_fetch):
        mock_fetch.return_value = [{
            "report_date_as_yyyy_mm_dd": "2026-08-18T00:00:00.000"
        }]

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = 99  # Already exists in DB
        mock_session.execute = AsyncMock(return_value=mock_result)

        fetcher = CFTCCOTFetcher(mock_session, {})
        res = await fetcher._fetch_and_save("http://test", {}, "gold", "088691")

        assert res == 0
        mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    @patch('data_sources.cftc_cot.fetch_with_retry')
    async def test_fetch_and_save_non_list_response(self, mock_fetch):
        mock_fetch.return_value = "<html>Error 500</html>"

        mock_session = AsyncMock()
        fetcher = CFTCCOTFetcher(mock_session, {})
        res = await fetcher._fetch_and_save("http://test", {}, "gold", "088691")

        assert res == 0
        mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    @patch('data_sources.cftc_cot.fetch_with_retry')
    async def test_fetch_and_save_with_non_dict_row(self, mock_fetch):
        mock_fetch.return_value = [
            "malformed_string_row",
            123,
            {
                "report_date_as_yyyy_mm_dd": "2026-08-18T00:00:00.000",
                "cftc_contract_market_code": "088691",
                "swap_positions_long_all": "100",
            },
        ]

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        fetcher = CFTCCOTFetcher(mock_session, {})
        res = await fetcher._fetch_and_save("http://test", {}, "gold", "088691")

        assert res == 1
        mock_session.add.assert_called_once()

    def test_int_parser(self):
        assert CFTCCOTFetcher._int("12,345") == 12345
        assert CFTCCOTFetcher._int(100) == 100
        assert CFTCCOTFetcher._int(100.7) == 100
        assert CFTCCOTFetcher._int(" 500 ") == 500
        assert CFTCCOTFetcher._int(None) == 0
        assert CFTCCOTFetcher._int("invalid") == 0
        assert CFTCCOTFetcher._int([]) == 0

    def test_parse_date(self):
        dt = CFTCCOTFetcher._parse_date("2026-08-18T00:00:00.000")
        assert dt == datetime(2026, 8, 18, 0, 0, tzinfo=timezone.utc)
        assert CFTCCOTFetcher._parse_date("2026-08-18") == datetime(2026, 8, 18, 0, 0, tzinfo=timezone.utc)
        assert CFTCCOTFetcher._parse_date("") is None
        assert CFTCCOTFetcher._parse_date(None) is None
        assert CFTCCOTFetcher._parse_date(12345) is None
        assert CFTCCOTFetcher._parse_date("invalid-date") is None


