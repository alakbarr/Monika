from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_gbpusd_1c9869(EdgeStrategy):
    strategy_id: str = "alpha_gbpusd_1c9869"
    applicable_symbols: set = {"GBPUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        if not self.settings:
            self.settings = {}
        self.settings.setdefault('displacement_mult', 1.3)
        self.settings.setdefault('htf_period', 24)
        self.settings.setdefault('sweep_window', 6)

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            # Fetch H1 candles for HTF liquidity levels and M15 candles for LTF execution
            h1_candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe='H1', limit=100)
            m15_candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe='M15', limit=100)

            if not h1_candles or not m15_candles or len(h1_candles) < 30 or len(m15_candles) < 30:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient historical data for multi-timeframe analysis.",
                    tags=["insufficient_data"]
                )

            # Helper to convert candles to DataFrame safely without dynamic attribute access
            def to_df(candles):
                rows = []
                for c in candles:
                    try:
                        r = {
                            'open': float(c.open),
                            'high': float(c.high),
                            'low': float(c.low),
                            'close': float(c.close),
                            'volume': float(c.volume)
                        }
                    except AttributeError:
                        r = {
                            'open': float(c['open']),
                            'high': float(c['high']),
                            'low': float(c['low']),
                            'close': float(c['close']),
                            'volume': float(c.get('volume', 0.0))
                        }
                    rows.append(r)
                return pd.DataFrame(rows)

            df_h1 = to_df(h1_candles)
            df_m15 = to_df(m15_candles)

            # Sanitize DataFrames to avoid NaNs/Infs
            df_h1 = df_h1.ffill().bfill().fillna(0.0)
            df_m15 = df_m15.ffill().bfill().fillna(0.0)

            # Calculate HTF Liquidity Levels (Previous 24-hour High/Low)
            # Shift by 1 to avoid lookahead bias
            htf_period = int(self.settings.get('htf_period', 24))
            df_h1['htf_high'] = df_h1['high'].shift(1).rolling(window=htf_period, min_periods=12).max()
            df_h1['htf_low'] = df_h1['low'].shift(1).rolling(window=htf_period, min_periods=12).min()

            df_h1 = df_h1.ffill().bfill()

            current_htf_high = float(df_h1['htf_high'].iloc[-1])
            current_htf_low = float(df_h1['htf_low'].iloc[-1])

            if current_htf_high == 0.0 or current_htf_low == 0.0:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Invalid HTF liquidity levels calculated.",
                    tags=["invalid_levels"]
                )

            # LTF Analysis (M15)
            # Calculate average body size for displacement threshold
            df_m15['body'] = (df_m15['close'] - df_m15['open']).abs()
            df_m15['avg_body'] = df_m15['body'].rolling(window=20, min_periods=10).mean()
            df_m15 = df_m15.ffill().bfill()

            # Lookback window for sweep detection (excluding current candle)
            sweep_window = int(self.settings.get('sweep_window', 6))
            sweep_lookback = df_m15.iloc[-(sweep_window + 1):-1]
            current_candle = df_m15.iloc[-1]

            avg_body = float(current_candle['avg_body'])
            current_body = float(current_candle['body'])
            current_close = float(current_candle['close'])
            current_open = float(current_candle['open'])

            # Check for Bullish Sweep & Displacement
            # 1. Did any recent M15 candle sweep below HTF Low?
            swept_low = float(sweep_lookback['low'].min()) < current_htf_low
            # 2. Did it close back above HTF Low (or does the current candle close above it)?
            reclaimed_low = current_close > current_htf_low
            # 3. Displacement: Current candle is strongly bullish
            displacement_mult = float(self.settings.get('displacement_mult', 1.3))
            bullish_displacement = (current_close > current_open) and (current_body > avg_body * displacement_mult)
            # 4. Market Structure Shift (MSS): Current close is above the high of the sweeping candle
            sweeping_candles_bull = sweep_lookback[sweep_lookback['low'] < current_htf_low]
            mss_bullish = False
            if not sweeping_candles_bull.empty:
                sweeper_high = float(sweeping_candles_bull['high'].max())
                mss_bullish = current_close > sweeper_high

            # Check for Bearish Sweep & Displacement
            # 1. Did any recent M15 candle sweep above HTF High?
            swept_high = float(sweep_lookback['high'].max()) > current_htf_high
            # 2. Did it close back below HTF High?
            reclaimed_high = current_close < current_htf_high
            # 3. Displacement: Current candle is strongly bearish
            bearish_displacement = (current_close < current_open) and (current_body > avg_body * displacement_mult)
            # 4. Market Structure Shift (MSS): Current close is below the low of the sweeping candle
            sweeping_candles_bear = sweep_lookback[sweep_lookback['high'] > current_htf_high]
            mss_bearish = False
            if not sweeping_candles_bear.empty:
                sweeper_low = float(sweeping_candles_bear['low'].min())
                mss_bearish = current_close < sweeper_low

            direction = None
            confidence = 0.0
            rationale = ""
            tags = []

            if swept_low and reclaimed_low and bullish_displacement and mss_bullish:
                direction = 'buy'
                confidence = min(0.95, 0.70 + (current_body / (avg_body * displacement_mult + 1e-8)) * 0.1)
                rationale = (
                    f"Bullish liquidity sweep of HTF Low ({current_htf_low:.5f}) detected on M15. "
                    f"Displacement confirmed with body size {current_body:.5f} (Avg: {avg_body:.5f}) "
                    f"and Market Structure Shift above sweeper high."
                )
                tags = ["liquidity_sweep", "bullish_displacement", "mss_confirmed"]

            elif swept_high and reclaimed_high and bearish_displacement and mss_bearish:
                direction = 'sell'
                confidence = min(0.95, 0.70 + (current_body / (avg_body * displacement_mult + 1e-8)) * 0.1)
                rationale = (
                    f"Bearish liquidity sweep of HTF High ({current_htf_high:.5f}) detected on M15. "
                    f"Displacement confirmed with body size {current_body:.5f} (Avg: {avg_body:.5f}) "
                    f"and Market Structure Shift below sweeper low."
                )
                tags = ["liquidity_sweep", "bearish_displacement", "mss_confirmed"]

            else:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="No liquidity sweep with displacement detected.",
                    tags=["neutral", "no_setup"]
                )

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=direction,
                valid=True,
                confidence=round(confidence, 2),
                rationale=rationale,
                tags=tags
            )

        except Exception as e:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Calculation error: {e}",
                tags=["error"]
            )
