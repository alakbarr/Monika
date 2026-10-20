"""Tests for CanonicalPriceLoader in backtesting."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
import pytest

from monika.application.backtest.price_series import CanonicalPriceLoader
from monika.core.exceptions import DataQualityError


@pytest.mark.asyncio
async def test_load_series_insufficient_bars_raises_data_quality_error():
    loader = CanonicalPriceLoader()
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result

    with pytest.raises(DataQualityError) as exc_info:
        await loader.load_series(
            session=mock_session,
            symbol="EURUSD",
            timeframe="H1",
            min_bars=50,
        )
    assert exc_info.value.code == "INSUFFICIENT_BARS"


@pytest.mark.asyncio
async def test_load_series_success_and_deduplication():
    loader = CanonicalPriceLoader()
    mock_session = AsyncMock()

    t0 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 1, 1, 11, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    # Mock rows returned descending from database: t2, t1, duplicate t1, t0
    r0 = MagicMock(timestamp=t0, canonical_timestamp=t0, open=1.0, high=1.1, low=0.9, close=1.05, volume=100.0)
    r1_old = MagicMock(timestamp=t1, canonical_timestamp=t1, open=1.05, high=1.15, low=1.0, close=1.1, volume=110.0)
    r1_new = MagicMock(timestamp=t1, canonical_timestamp=t1, open=1.05, high=1.16, low=1.0, close=1.12, volume=115.0)
    r2 = MagicMock(timestamp=t2, canonical_timestamp=t2, open=1.12, high=1.2, low=1.1, close=1.18, volume=120.0)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [r2, r1_new, r1_old, r0]
    mock_session.execute.return_value = mock_result

    df = await loader.load_series(
        session=mock_session,
        symbol="EURUSD",
        timeframe="H1",
        min_bars=3,
        max_gap_pct=0.20,
    )

    assert len(df) == 3
    assert df.index.is_monotonic_increasing
    # Deduplication kept latest r1_new
    assert df.loc[t1, "close"] == 1.12
    assert df.loc[t2, "close"] == 1.18


def test_validate_continuity_excessive_gap_raises():
    loader = CanonicalPriceLoader()
    import pandas as pd

    # Create artificial 50-hour gap on H1 crypto
    t0 = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(hours=1)
    t2 = t0 + timedelta(hours=50)

    df = pd.DataFrame(
        {
            "open": [100.0, 101.0, 105.0],
            "high": [102.0, 103.0, 106.0],
            "low": [99.0, 100.0, 104.0],
            "close": [101.0, 102.0, 105.5],
            "volume": [10.0, 12.0, 15.0],
        },
        index=pd.to_datetime([t0, t1, t2], utc=True),
    )

    with pytest.raises(DataQualityError) as exc_info:
        loader._validate_continuity(df, "BTCUSD", "H1", max_gap_pct=0.05)
    assert exc_info.value.code == "EXCESSIVE_DATA_GAPS"
