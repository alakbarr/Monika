import pytest
import pandas as pd
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from execution.mt5_client import MT5Client
from database.models import PriceOHLCV

class TestMT5OHLCVSync:
    @pytest.mark.asyncio
    async def test_save_ohlcv_inserts_and_updates_forming_candle(self):
        client = MT5Client({})
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        ts = datetime(2026, 8, 25, 20, 0, 0, tzinfo=timezone.utc)
        df_initial = pd.DataFrame([{
            "time": ts,
            "open": 2000.0,
            "high": 2005.0,
            "low": 1995.0,
            "close": 2002.0,
            "volume": 100.0,
        }])

        # First run: record does not exist
        mock_result_none = MagicMock()
        mock_result_none.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result_none

        saved_1 = await client.save_ohlcv(mock_session, "XAUUSD", "H4", df_initial)
        assert saved_1 == 1
        assert mock_session.add.called

        # Second run: record exists (forming candle price moved)
        existing = PriceOHLCV(
            symbol="XAUUSD", timeframe="H4", timestamp=ts,
            open=2000.0, high=2005.0, low=1995.0, close=2002.0, volume=100.0
        )
        mock_result_exists = MagicMock()
        mock_result_exists.scalar_one_or_none.return_value = existing
        mock_session.execute.return_value = mock_result_exists

        df_updated = pd.DataFrame([{
            "time": ts,
            "open": 2000.0,
            "high": 2010.0,  # new high
            "low": 1995.0,
            "close": 2008.0, # new close
            "volume": 250.0, # new volume
        }])

        saved_2 = await client.save_ohlcv(mock_session, "XAUUSD", "H4", df_updated)
        assert saved_2 == 1
        assert existing.high == 2010.0
        assert existing.close == 2008.0
        assert existing.volume == 250.0
