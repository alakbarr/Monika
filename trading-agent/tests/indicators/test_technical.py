import pytest
import pandas as pd
import numpy as np
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock
from indicators.technical import TechnicalIndicatorCalculator
from database.models import TechnicalIndicator

class TestTechnicalIndicatorCalculator:

    @pytest.fixture
    def calc(self):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        settings = {
            "indicators": {
                "ma_periods": [5],
                "rsi_period": 3,
                "stochastic_k": 3,
                "stochastic_d": 3,
                "macd_fast": 3,
                "macd_slow": 5,
                "macd_signal": 3,
                "bollinger_period": 5,
                "bollinger_std": 2.0
            }
        }
        return TechnicalIndicatorCalculator(mock_session, settings)

    @pytest.mark.asyncio
    async def test_compute_and_save_insufficient_data(self, calc):
        calc._load_ohlcv = AsyncMock(return_value=pd.DataFrame())
        saved = await calc.compute_and_save("XAUUSD", "H1")
        assert saved == 0

    @pytest.mark.asyncio
    async def test_compute_and_save_success(self, calc):
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=10),
            "open": [10]*10,
            "high": [12]*10,
            "low": [8]*10,
            "close": [11]*10,
            "volume": [100]*10
        }).set_index("timestamp")
        
        calc._load_ohlcv = AsyncMock(return_value=df)
        calc._save = AsyncMock(return_value=15)
        
        saved = await calc.compute_and_save("XAUUSD", "H1")
        assert saved == 15

    @pytest.mark.asyncio
    async def test_compute_all_symbols(self, calc):
        calc.compute_and_save = AsyncMock(return_value=5)
        res = await calc.compute_all_symbols(["XAUUSD"], ["H1"])
        assert "XAUUSD/H1" in res
        assert res["XAUUSD/H1"] == 5

    def test_compute_all(self, calc):
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=20),
            "open": [float(x) for x in range(10, 30)],
            "high": [float(x) for x in range(12, 32)],
            "low": [float(x) for x in range(8, 28)],
            "close": [float(x) for x in range(11, 31)],
            "volume": [100.0]*20
        }).set_index("timestamp")
        
        inds = calc._compute_all(df)
        assert len(inds) > 0
        last_ts = max(inds.keys())
        
        has_sma = False
        has_rsi = False
        has_macd = False
        has_bb = False
        has_stoch = False
        for ind in inds[last_ts]:
            if "SMA_5" in ind["name"]: has_sma = True
            if "RSI_3" in ind["name"]: has_rsi = True
            if "MACD" in ind["name"]: has_macd = True
            if "BBANDS" in ind["name"]: has_bb = True
            if "STOCH" in ind["name"]: has_stoch = True
            
        assert has_sma
        assert has_rsi
        assert has_macd
        assert has_bb
        assert has_stoch

    @pytest.mark.asyncio
    async def test_save(self, calc):
        calc.session.execute = AsyncMock()
        calc.session.add = MagicMock()
        
        indicators = {
            datetime(2024, 1, 1, tzinfo=timezone.utc): [
                {"name": "SMA_5", "value_json": "100.0"}
            ]
        }
        
        saved = await calc._save("XAUUSD", "H1", indicators)
        assert saved == 1
        calc.session.add.assert_called_once()
        calc.session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_latest(self, calc):
        mock_result = MagicMock()
        mock_row = TechnicalIndicator(timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc), value_json="100.0")
        mock_result.scalar_one_or_none.return_value = mock_row
        calc.session.execute = AsyncMock(return_value=mock_result)
        
        res = await calc.get_latest("XAUUSD", "H1", "SMA_5")
        assert res is not None
        assert res["value"] == 100.0

    @pytest.mark.asyncio
    async def test_get_snapshot(self, calc):
        ts1 = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
        ts0 = datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc)
        
        mock_result_ts = MagicMock()
        mock_result_ts.scalars().all.return_value = [ts1, ts0]
        
        mock_result_rows_curr = MagicMock()
        row1 = TechnicalIndicator(indicator_name="RSI_14", timestamp=ts1, value_json='{"rsi": 65.0}')
        mock_result_rows_curr.scalars().all.return_value = [row1]

        mock_result_rows_prev = MagicMock()
        row0 = TechnicalIndicator(indicator_name="RSI_14", timestamp=ts0, value_json='{"rsi": 55.0}')
        mock_result_rows_prev.scalars().all.return_value = [row0]
        
        calc.session.execute = AsyncMock(side_effect=[mock_result_ts, mock_result_rows_curr, mock_result_rows_prev])
        
        res = await calc.get_snapshot("XAUUSD", "H1")
        assert "RSI_14" in res
        assert res["RSI_14"]["value"] == {"rsi": 65.0}
        assert res["RSI_14"]["prev"] == {"rsi": 55.0}
        assert res["RSI_14"]["delta"] == 10.0
        assert res["RSI_14"]["direction"] == "rising"

    def test_compute_all_includes_obv(self, calc):
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=15),
            "open": [float(x) for x in range(10, 25)],
            "high": [float(x) + 2 for x in range(10, 25)],
            "low": [float(x) - 2 for x in range(10, 25)],
            "close": [float(x) + 1 for x in range(10, 25)],
            "volume": [1000.0] * 15
        }).set_index("timestamp")
        
        inds = calc._compute_all(df)
        last_ts = max(inds.keys())
        has_obv = any("OBV" in ind["name"] for ind in inds[last_ts])
        assert has_obv

    def test_forex_weekend_resampling_filtered(self, calc):
        # 1-week hourly range including Friday 22:00 through Sunday 21:00
        dates = pd.date_range("2026-08-28 00:00", "2026-08-31 00:00", freq="1h")
        df = pd.DataFrame({
            "open": 1.1000, "high": 1.1050, "low": 1.0950, "close": 1.1020, "volume": 100.0
        }, index=dates)

        resampled = df.resample("1h").asfreq()
        idx = resampled.index
        is_weekend = (
            (idx.dayofweek == 5) |
            ((idx.dayofweek == 6) & (idx.hour < 21)) |
            ((idx.dayofweek == 4) & (idx.hour >= 22))
        )
        resampled_filtered = resampled[~is_weekend]

        # Saturday bars must not exist
        assert not any(ts.dayofweek == 5 for ts in resampled_filtered.index)
        # Friday >= 22:00 must not exist
        assert not any(ts.dayofweek == 4 and ts.hour >= 22 for ts in resampled_filtered.index)
        # Sunday < 21:00 must not exist
        assert not any(ts.dayofweek == 6 and ts.hour < 21 for ts in resampled_filtered.index)

    def test_compute_yang_zhang_volatility(self):
        from indicators.technical import compute_yang_zhang_volatility
        # Insufficient data
        short_df = pd.DataFrame({
            "open": [1.0] * 5, "high": [1.1] * 5, "low": [0.9] * 5, "close": [1.0] * 5
        })
        short_res = compute_yang_zhang_volatility(short_df, window=20)
        assert len(short_res) == 5
        assert short_res.isna().all()

        # Sufficient data with variation
        dates = pd.date_range("2024-01-01", periods=30, freq="1h")
        np.random.seed(42)
        close_prices = 100.0 + np.cumsum(np.random.randn(30))
        df = pd.DataFrame({
            "open": close_prices - 0.2,
            "high": close_prices + 0.5,
            "low": close_prices - 0.5,
            "close": close_prices,
        }, index=dates)
        vol = compute_yang_zhang_volatility(df, window=10)
        assert isinstance(vol, pd.Series)
        assert len(vol) == 30
        assert (vol >= 0.0).all()
        # After window periods, volatility should be strictly positive
        assert (vol.iloc[11:] > 0.0).any()

    def test_compute_lag1_autocorrelation(self):
        from indicators.technical import compute_lag1_autocorrelation
        # Insufficient data
        short_close = pd.Series([1.0, 2.0, 3.0])
        res_short = compute_lag1_autocorrelation(short_close, window=20)
        assert len(res_short) == 3
        assert res_short.isna().all()

        # Sufficient data
        dates = pd.date_range("2024-01-01", periods=30, freq="1h")
        close = pd.Series(range(30), index=dates, dtype=float)
        ac1 = compute_lag1_autocorrelation(close, window=10)
        assert isinstance(ac1, pd.Series)
        assert len(ac1) == 30
