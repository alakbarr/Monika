import pytest
import pandas as pd
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

from indicators.technical import TechnicalIndicatorCalculator
from indicators.structure import MarketStructureAnalyzer
from analysis.calculators.confluence_calculator import (
    calculate_priced_in_subscores,
    SYMBOL_TO_COT_CODE,
)
from analysis.prefetch.stage2_prefetcher import Stage2DataBundler, SYMBOL_FETCH_TASKS
from analysis.tools.tool_executor import ToolExecutor
from database.models import TechnicalIndicator, SwingPoint, FVGZone, OrderBlock, StructureBreak, PriceOHLCV


class TestTechnicalAnalysisImprovements:
    """Test suite covering technical analysis fixes."""

    # ------------------------------------------------------------------
    # C1: Indicator Delta & Direction Context
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_indicator_snapshot_delta_and_direction(self):
        mock_session = AsyncMock()
        calc = TechnicalIndicatorCalculator(mock_session, {})
        
        now = datetime.now(timezone.utc)
        prev = now - timedelta(hours=4)

        ts_res = MagicMock()
        ts_res.scalars().all.return_value = [now, prev]

        curr_row = TechnicalIndicator(
            indicator_name="RSI_14",
            symbol="EURUSD",
            timeframe="H4",
            timestamp=now,
            value_json='{"rsi": 58.5}',
        )
        prev_row = TechnicalIndicator(
            indicator_name="RSI_14",
            symbol="EURUSD",
            timeframe="H4",
            timestamp=prev,
            value_json='{"rsi": 48.5}',
        )

        curr_res = MagicMock()
        curr_res.scalars().all.return_value = [curr_row]

        prev_res = MagicMock()
        prev_res.scalars().all.return_value = [prev_row]

        mock_session.execute = AsyncMock(side_effect=[ts_res, curr_res, prev_res])

        snap = await calc.get_snapshot("EURUSD", "H4")
        assert "RSI_14" in snap
        item = snap["RSI_14"]
        assert item["value"] == {"rsi": 58.5}
        assert item["prev"] == {"rsi": 48.5}
        assert item["delta"] == 10.0
        assert item["direction"] == "rising"

    # ------------------------------------------------------------------
    # C2: USDJPY COT Mapping
    # ------------------------------------------------------------------
    def test_cot_mapping_contains_usdjpy(self):
        assert "USDJPY" in SYMBOL_TO_COT_CODE
        assert SYMBOL_TO_COT_CODE["USDJPY"] == "097741"

    @pytest.mark.asyncio
    async def test_priced_in_subscores_usdjpy_cot(self):
        mock_session = AsyncMock()
        from database.models import COTReport
        
        cot_row = COTReport(
            market_code="097741",
            report_date=datetime.now(timezone.utc),
            leveraged_long=80000,
            leveraged_short=10000,
        )
        mock_res_fw = MagicMock()
        mock_res_fw.scalar_one_or_none.return_value = None

        mock_res_cot = MagicMock()
        mock_res_cot.scalar_one_or_none.return_value = cot_row

        mock_res_empty = MagicMock()
        mock_res_empty.scalar_one_or_none.return_value = None
        mock_res_empty.scalars().all.return_value = []

        mock_session.execute = AsyncMock(side_effect=[mock_res_fw, mock_res_cot, mock_res_empty, mock_res_empty])

        subscores = await calculate_priced_in_subscores(mock_session, "USDJPY")
        assert subscores["cot"] >= 0

    # ------------------------------------------------------------------
    # C3: Structure Break Candle-Close Confirmation
    # ------------------------------------------------------------------
    def test_detect_structure_breaks_with_close_confirmation(self):
        analyzer = MarketStructureAnalyzer(AsyncMock(), {"indicators": {"swing_window": 2}})
        
        # Candles where high spikes to 105 but close is 98 (wick-only break of 100)
        dates = pd.date_range("2024-01-01", periods=5)
        df = pd.DataFrame({
            "high": [100.0, 95.0, 105.0, 96.0, 97.0],
            "low":  [90.0, 88.0, 90.0, 89.0, 90.0],
            "close": [98.0, 92.0, 98.0, 93.0, 95.0],
        }, index=dates)
        
        swings_high = pd.DataFrame([
            {"timestamp": dates[0], "price": 100.0},
            {"timestamp": dates[2], "price": 105.0},
        ])
        swings_low = pd.DataFrame([
            {"timestamp": dates[1], "price": 88.0},
        ])
        
        breaks = analyzer._detect_structure_breaks(df, swings_high, swings_low, "EURUSD", "H4")
        assert len(breaks) == 0

    # ------------------------------------------------------------------
    # C4: D1 Structure Breaks in SYMBOL_FETCH_TASKS
    # ------------------------------------------------------------------
    def test_d1_structure_breaks_in_fetch_tasks(self):
        d1_sb = any(t == ("get_structure_breaks", {"timeframe": "D1"}) for t in SYMBOL_FETCH_TASKS)
        d1_sw = any(t == ("get_swing_points", {"timeframe": "D1", "limit": 4}) for t in SYMBOL_FETCH_TASKS)
        assert d1_sb, "D1 structure breaks must be pre-fetched"
        assert d1_sw, "D1 swing points must be pre-fetched"

    # ------------------------------------------------------------------
    # H2: Order Block 50% Penetration Mitigation
    # ------------------------------------------------------------------
    def test_order_block_50pct_penetration_mitigation(self):
        analyzer = MarketStructureAnalyzer(AsyncMock(), {"indicators": {"swing_window": 2}})
        
        # Bullish OB: price_high=100, price_low=90, mid=95
        ob = OrderBlock(
            symbol="EURUSD",
            timeframe="H4",
            direction="bullish",
            price_high=100.0,
            price_low=90.0,
            formed_at=datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc),
        )
        
        # Future candle low = 97 (touches zone high 100, but doesn't reach mid 95)
        dates = pd.date_range("2024-01-01 04:00", periods=2, freq="4h", tz="UTC")
        df_touch_only = pd.DataFrame({
            "timestamp": dates,
            "open": [102.0, 101.0],
            "high": [103.0, 102.0],
            "low": [97.0, 98.0],
            "close": [101.0, 100.0],
        })
        
        blocks = analyzer._find_order_blocks(df_touch_only.set_index("timestamp"), "EURUSD", "H4", existing_obs=[ob])
        unmit = [b for b in blocks if b.mitigated_at is None and b.direction == "bullish"]
        assert len(unmit) >= 1

    # ------------------------------------------------------------------
    # H4: FVG 50% Fill Mitigation
    # ------------------------------------------------------------------
    def test_fvg_50pct_fill_mitigation(self):
        analyzer = MarketStructureAnalyzer(AsyncMock(), {})
        
        dates = pd.date_range("2024-01-01", periods=2)
        df_partial = pd.DataFrame({
            "timestamp": dates,
            "low": [17.0, 18.0],
            "high": [22.0, 23.0],
        })
        filled_ts = analyzer._check_fvg_filled(df_partial, 0, 20.0, 10.0, "bullish")
        assert filled_ts is None

        df_deep = pd.DataFrame({
            "timestamp": dates,
            "low": [14.0, 18.0],
            "high": [22.0, 23.0],
        })
        filled_ts_deep = analyzer._check_fvg_filled(df_deep, 0, 20.0, 10.0, "bullish")
        assert filled_ts_deep is not None

    # ------------------------------------------------------------------
    # H5: Fibonacci Maximum Range Swing Pair Selection
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_fibonacci_selects_max_range_swing_pair(self):
        mock_session = AsyncMock()
        executor = ToolExecutor(mock_session)
        
        now = datetime.now(timezone.utc)
        swings = [
            SwingPoint(symbol="EURUSD", timeframe="H4", type="high", price=100.0, timestamp=now - timedelta(hours=16)),
            SwingPoint(symbol="EURUSD", timeframe="H4", type="low", price=50.0, timestamp=now - timedelta(hours=12)),
            SwingPoint(symbol="EURUSD", timeframe="H4", type="high", price=55.0, timestamp=now - timedelta(hours=8)),
            SwingPoint(symbol="EURUSD", timeframe="H4", type="low", price=52.0, timestamp=now - timedelta(hours=4)),
        ]
        
        mock_res = MagicMock()
        mock_res.scalars().all.return_value = swings
        mock_session.execute = AsyncMock(return_value=mock_res)
        
        res = await executor._tool_get_fibonacci_levels({"symbol": "EURUSD", "timeframe": "H4"})
        assert res["move_size"] >= 45.0

    # ------------------------------------------------------------------
    # H6: Dynamic Price Precision in History Compression
    # ------------------------------------------------------------------
    def test_compress_history_dynamic_precision(self):
        bundler = Stage2DataBundler(AsyncMock(), {})
        
        history_eurusd = {
            "symbol": "EURUSD",
            "bars": [{
                "time": "2024-01-01T12:00:00Z",
                "open": 1.08456, "high": 1.08789, "low": 1.08234, "close": 1.08654
            }]
        }
        res_eur = bundler._compress_history(history_eurusd, "EURUSD")
        assert "1.08654" in res_eur

        history_xau = {
            "symbol": "XAUUSD",
            "bars": [{
                "time": "2024-01-01T12:00:00Z",
                "open": 2650.123, "high": 2655.456, "low": 2648.789, "close": 2652.85
            }]
        }
        res_xau = bundler._compress_history(history_xau, "XAUUSD")
        assert "2652.85" in res_xau

    # ------------------------------------------------------------------
    # H7: SMC Proximity Sorting
    # ------------------------------------------------------------------
    def test_smc_data_proximity_sorting(self):
        bundler = Stage2DataBundler(AsyncMock(), {})
        
        obs = [
            {"price_high": 1.0500, "price_low": 1.0450},
            {"price_high": 1.0810, "price_low": 1.0805},
            {"price_high": 1.0790, "price_low": 1.0785},
            {"price_high": 1.1100, "price_low": 1.1050},
        ]
        
        raw_data = {"order_blocks": obs, "fvg_zones": [], "liquidity_zones": [], "sr_zones": []}
        formatted = bundler.executor._format_smc_data(raw_data, current_price=1.0800)
        
        trimmed_obs = formatted["order_blocks"]
        assert len(trimmed_obs) == 3
        prices = [ob["price_high"] for ob in trimmed_obs]
        assert 1.0810 in prices
        assert 1.0790 in prices
