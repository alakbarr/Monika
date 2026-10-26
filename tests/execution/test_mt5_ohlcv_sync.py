import pytest
import pandas as pd
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from tests.conftest import create_mock_async_session
from monika.infrastructure.brokers.mt5_client import MT5Client
from monika.infrastructure.database.models import PriceOHLCV


class TestMT5OHLCVSync:
    @pytest.mark.asyncio
    async def test_save_ohlcv_inserts_and_updates_forming_candle(self):
        client = MT5Client({})
        mock_session = create_mock_async_session()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        ts = datetime(2026, 8, 25, 20, 0, 0, tzinfo=timezone.utc)
        df_initial = pd.DataFrame(
            [
                {
                    "time": ts,
                    "open": 2000.0,
                    "high": 2005.0,
                    "low": 1995.0,
                    "close": 2002.0,
                    "volume": 100.0,
                }
            ]
        )

        # First run: record does not exist
        mock_result_none = MagicMock()
        mock_result_none.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result_none

        saved_1 = await client.save_ohlcv(mock_session, "XAUUSD", "H4", df_initial)
        assert saved_1 == 1
        assert mock_session.add.called

        # Second run: record exists (forming candle price moved)
        existing = PriceOHLCV(
            symbol="XAUUSD",
            timeframe="H4",
            timestamp=ts,
            open=2000.0,
            high=2005.0,
            low=1995.0,
            close=2002.0,
            volume=100.0,
        )
        mock_result_exists = MagicMock()
        mock_result_exists.scalar_one_or_none.return_value = existing
        mock_session.execute.return_value = mock_result_exists

        df_updated = pd.DataFrame(
            [
                {
                    "time": ts,
                    "open": 2000.0,
                    "high": 2010.0,  # new high
                    "low": 1995.0,
                    "close": 2008.0,  # new close
                    "volume": 250.0,  # new volume
                }
            ]
        )

        saved_2 = await client.save_ohlcv(mock_session, "XAUUSD", "H4", df_updated)
        assert saved_2 == 1
        assert existing.high == 2010.0
        assert existing.close == 2008.0
        assert existing.volume == 250.0

    @pytest.mark.asyncio
    async def test_save_ohlcv_bulk_lookup_single_query_for_multiple_rows(self):
        client = MT5Client({"trading": {"mt5": {"broker_utc_offset_hours": 2}}})
        mock_session = create_mock_async_session()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        ts1 = datetime(2026, 10, 26, 7, 0, 0, tzinfo=timezone.utc)
        ts2 = datetime(2026, 10, 26, 8, 0, 0, tzinfo=timezone.utc)
        existing_row = PriceOHLCV(
            symbol="EURUSD",
            timeframe="H1",
            timestamp=ts1,
            canonical_timestamp=ts1,
            open=1.0800,
            high=1.0810,
            low=1.0790,
            close=1.0805,
            volume=100.0,
        )
        bulk_res = MagicMock()
        bulk_res.scalars.return_value.all.return_value = [existing_row]
        mock_session.execute = AsyncMock(return_value=bulk_res)

        df_batch = pd.DataFrame(
            [
                {"time": ts1, "open": 1.0800, "high": 1.0820, "low": 1.0790, "close": 1.0815, "volume": 150.0},
                {"time": ts2, "open": 1.0815, "high": 1.0830, "low": 1.0810, "close": 1.0825, "volume": 90.0},
            ]
        )

        saved = await client.save_ohlcv(mock_session, "EURUSD", "H1", df_batch)
        assert saved == 2
        assert mock_session.execute.await_count == 1
        assert existing_row.close == 1.0815
        mock_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_mt5_client_offset_updates_when_settings_hot_reloaded(self):
        settings = {"trading": {"mt5": {"broker_utc_offset_hours": 3}}}
        client = MT5Client(settings)
        assert await client.get_broker_utc_offset_seconds() == 10800

        # Simulate hot-reload of settings dict in-place
        settings["trading"]["mt5"]["broker_utc_offset_hours"] = 2
        assert await client.get_broker_utc_offset_seconds() == 7200
