import pytest
import pandas as pd
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock
from indicators.structure import MarketStructureAnalyzer

class TestMarketStructureAnalyzer:

    @pytest.fixture
    def analyzer(self):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        return MarketStructureAnalyzer(mock_session, {"indicators": {"swing_window": 2, "sr_tolerance": 0.002, "sr_min_touches": 2}})

    @pytest.mark.asyncio
    async def test_analyze_insufficient_data(self, analyzer):
        analyzer._load_ohlcv = AsyncMock(return_value=pd.DataFrame())
        analyzer._prune_old_data = AsyncMock()
        
        res = await analyzer.analyze("XAUUSD", "H1")
        assert res["swing_points"] == 0

    @pytest.mark.asyncio
    async def test_analyze_all(self, analyzer):
        analyzer.analyze = AsyncMock(return_value={"swing_points": 5})
        res = await analyzer.analyze_all(["XAUUSD"], ["H1"])
        assert "XAUUSD/H1" in res
        assert res["XAUUSD/H1"]["swing_points"] == 5

    def test_find_swings(self, analyzer):
        df = pd.DataFrame({
            "high": [1, 2, 3, 2, 1, 2, 4, 2, 1],
            "low": [0.5, 1, 2, 1, 0.5, 1, 3, 1, 0.5],
            "timestamp": pd.date_range("2024-01-01", periods=9)
        }).set_index("timestamp")
        
        highs, lows = analyzer._find_swings(df)
        assert not highs.empty
        assert not lows.empty

    def test_find_sr_zones(self, analyzer):
        highs = pd.DataFrame([{"price": 100.0, "timestamp": datetime.now()}, {"price": 100.1, "timestamp": datetime.now()}])
        lows = pd.DataFrame()
        df = pd.DataFrame()
        
        zones = analyzer._find_sr_zones(highs, lows, df)
        assert len(zones) == 1
        assert zones[0]["strength"] == 2

    def test_find_liquidity_zones(self, analyzer):
        highs = pd.DataFrame([{"price": 100.0, "timestamp": datetime.now()}])
        lows = pd.DataFrame([{"price": 50.0, "timestamp": datetime.now()}])
        
        df = pd.DataFrame(columns=["high", "low"])
        df.index = pd.DatetimeIndex([])
        zones = analyzer._find_liquidity_zones(highs, lows, "XAUUSD", "H1", df)
        assert len(zones) == 2
        assert zones[0].type == "above_swing_high"
        assert zones[1].type == "below_swing_low"

    def test_find_fvg(self, analyzer):
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=3),
            "open": [10, 15, 20],
            "high": [12, 17, 22],
            "low": [8, 13, 18],
            "close": [11, 16, 21]
        }).set_index("timestamp")
        
        # Bullish FVG: candle3.low (18) > candle1.high (12)
        zones = analyzer._find_fvg(df, "XAUUSD", "H1")
        assert len(zones) == 1
        assert zones[0].direction == "bullish"
        assert zones[0].gap_high == 18
        assert zones[0].gap_low == 12

    def test_check_fvg_filled(self, analyzer):
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=3),
            "low": [20, 15, 10], # price trades down to 10
            "high": [25, 20, 15]
        })
        
        # Bullish FVG from gap_low=12 to gap_high=18
        filled = analyzer._check_fvg_filled(df, 0, 18, 12, "bullish")
        assert filled is not None # filled when low hits 10 <= 12

    def test_find_order_blocks(self, analyzer):
        # We need at least 10 candles, and the loop checks range(2, n-5)
        # We need the impulse to be > max(body_size*3, atr*2)
        base_open = [10] * 12
        base_high = [11] * 12
        base_low = [9] * 12
        base_close = [10] * 12
        
        # Setup starting at index 12
        # candle 12: bearish OB candle (open=10, close=9, high=12, low=8)
        # candle 13: bullish (open=10, close=11, high=11, low=9)
        # candle 14: impulse (open=11, close=14, high=15, low=11)
        # candle 15: big impulse (open=14, close=19, high=25, low=14)
        # candle 16-19: stay above (low > 8)
        
        o = base_open + [10, 10, 11, 14, 15, 15, 15, 15]
        h = base_high + [12, 11, 15, 25, 20, 20, 20, 20]
        l = base_low + [8, 9, 11, 14, 14, 14, 14, 14]
        c = base_close + [9, 11, 14, 19, 19, 19, 19, 19]

        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=20),
            "open": o,
            "high": h,
            "low": l,
            "close": c
        }).set_index("timestamp")
        
        obs = analyzer._find_order_blocks(df, "XAUUSD", "H1")
        assert len(obs) == 1
        assert obs[0].direction == "bullish"

    @pytest.mark.asyncio
    async def test_save_swings(self, analyzer):
        analyzer.session.execute = AsyncMock()
        highs = pd.DataFrame([{"timestamp": datetime.now(), "price": 100}])
        lows = pd.DataFrame([{"timestamp": datetime.now(), "price": 50}])
        
        saved = await analyzer._save_swings("XAUUSD", "H1", highs, lows)
        assert saved == 2

    @pytest.mark.asyncio
    async def test_get_structure_snapshot(self, analyzer):
        mock_result = MagicMock()
        mock_result.scalars().all.return_value = []
        analyzer.session.execute = AsyncMock(return_value=mock_result)
        
        snap = await analyzer.get_structure_snapshot("XAUUSD", "H1")
        assert "swing_highs" in snap
        assert "order_blocks" in snap

import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from database.models import Base, PriceOHLCV

@pytest_asyncio.fixture
async def test_db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session
    
    await engine.dispose()

@pytest.mark.asyncio
async def test_load_ohlcv_regression_most_recent(test_db_session):
    now = datetime.now(timezone.utc)
    rows = []
    # Seed 600 rows (limit is 500)
    for i in range(600):
        ts = now - pd.Timedelta(days=600-i)
        rows.append(PriceOHLCV(
            symbol="XAUUSD",
            timeframe="H1",
            timestamp=ts,
            open=10.0, high=12.0, low=8.0, close=11.0, volume=100
        ))
    test_db_session.add_all(rows)
    await test_db_session.commit()
    
    analyzer = MarketStructureAnalyzer(test_db_session, {})
    df = await analyzer._load_ohlcv("XAUUSD", "H1")
    
    assert len(df) == 500
    
    expected_last_ts = rows[-1].timestamp
    actual_last_ts = df.index[-1]
    
    expected_first_ts = rows[-500].timestamp
    actual_first_ts = df.index[0]
    
    assert actual_last_ts == expected_last_ts, "Should end with the most recent data"
    assert actual_first_ts == expected_first_ts, "Should start exactly 500 bars ago"


@pytest.mark.asyncio
async def test_analyze_end_to_end_async_thread(test_db_session):
    """Verify analyze() executes end-to-end with asyncio.to_thread without NameError or missing vars."""
    now = datetime.now(timezone.utc)
    rows = []
    for i in range(25):
        ts = now - pd.Timedelta(hours=25 - i)
        rows.append(PriceOHLCV(
            symbol="EURUSD",
            timeframe="H1",
            timestamp=ts,
            open=1.1000 + (i % 3) * 0.001,
            high=1.1050 + (i % 3) * 0.001,
            low=1.0950 - (i % 3) * 0.001,
            close=1.1010 + (i % 3) * 0.001,
            volume=200.0,
        ))
    test_db_session.add_all(rows)
    await test_db_session.commit()

    analyzer = MarketStructureAnalyzer(test_db_session, {"indicators": {"swing_window": 2}})
    counts = await analyzer.analyze("EURUSD", "H1")
    assert isinstance(counts, dict)
    assert "swing_points" in counts
    assert "sr_zones" in counts
    assert "liquidity_zones" in counts
    assert "fvg_zones" in counts
    assert "order_blocks" in counts
    assert "struct_breaks" in counts

