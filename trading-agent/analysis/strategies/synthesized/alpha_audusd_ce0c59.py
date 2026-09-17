from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_audusd_ce0c59(EdgeStrategy):
    strategy_id: str = "alpha_audusd_ce0c59"
    applicable_symbols: set = {"AUDUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        # Define hyperparameters with safe fallbacks
        self.base_lookback = int(self.settings.get("base_lookback", 20))
        self.min_lookback = int(self.settings.get("min_lookback", 10))
        self.max_lookback = int(self.settings.get("max_lookback", 40))
        self.volume_ma_period = int(self.settings.get("volume_ma_period", 20))
        self.volume_factor = float(self.settings.get("volume_factor", 5.0))
        self.trend_filter_period = int(self.settings.get("trend_filter_period", 200))
        self.volume_threshold_ratio = float(self.settings.get("volume_threshold_ratio", 1.1))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            # Fetch historical candles (using H1 timeframe for dynamic Donchian expansion)
            candles = await self.get_historical_candles(
                session=session, 
                symbol=symbol, 
                timeframe='H1', 
                limit=250
            )
            
            if not candles or len(candles) < 50:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient candle history available.",
                    tags=["insufficient_data"]
                )

            # Parse candles safely into a structured format
            data = []
            for c in candles:
                try:
                    data.append({
                        'open': float(c.open if hasattr(c, 'open') else c['open']),
                        'high': float(c.high if hasattr(c, 'high') else c['high']),
                        'low': float(c.low if hasattr(c, 'low') else c['low']),
                        'close': float(c.close if hasattr(c, 'close') else c['close']),
                        'volume': float(c.volume if hasattr(c, 'volume') else c['volume']),
                    })
                except Exception:
                    continue

            df = pd.DataFrame(data)
            if len(df) < 50:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Failed to parse sufficient candle data.",
                    tags=["parse_error"]
                )

            # Sanitize NaNs/Infs
            df = df.ffill().bfill()

            # Calculate Volume Z-Score to measure volume expansion
            vol_ma = df['volume'].rolling(window=self.volume_ma_period, min_periods=1).mean()
            vol_std = df['volume'].rolling(window=self.volume_ma_period, min_periods=1).std().fillna(0.0)
            vol_std = vol_std.replace(0.0, 1e-8)  # Prevent division by zero
            vol_z = (df['volume'] - vol_ma) / vol_std

            # Trend Filter (EMA) to align with institutional flow
            trend_period = min(self.trend_filter_period, len(df))
            ema_trend = df['close'].ewm(span=trend_period, adjust=False).mean()

            # Extract latest metrics
            latest_vol_z = float(vol_z.iloc[-1])
            latest_vol_ma = float(vol_ma.iloc[-1])
            latest_volume = float(df['volume'].iloc[-1])
            latest_close = float(df['close'].iloc[-1])
            latest_trend = float(ema_trend.iloc[-1])

            # Dynamic lookback calculation:
            # High volume (positive Z-score) -> Shorten lookback (faster breakout detection)
            # Low volume (negative Z-score) -> Lengthen lookback (filter out noise)
            raw_lookback = self.base_lookback - (self.volume_factor * latest_vol_z)
            clamped_lookback = max(self.min_lookback, min(self.max_lookback, raw_lookback))
            
            # Ensure lookback is a safe integer and does not exceed available history
            lookback = int(round(clamped_lookback))
            lookback = min(lookback, len(df) - 2)

            # Calculate Donchian Channel boundaries on prior candles (excluding current candle)
            donchian_high = float(df['high'].iloc[-lookback-1:-1].max())
            donchian_low = float(df['low'].iloc[-lookback-1:-1].min())

            # Signal Generation Logic
            direction = None
            confidence = 0.0
            rationale = ""
            tags = ["volume_weighted_donchian"]

            # Volume confirmation check
            volume_confirmed = latest_volume > (latest_vol_ma * self.volume_threshold_ratio)
            bullish_trend = latest_close > latest_trend
            bearish_trend = latest_close < latest_trend

            # Breakout conditions
            breakout_high = latest_close > donchian_high
            breakout_low = latest_close < donchian_low

            if breakout_high:
                if volume_confirmed and bullish_trend:
                    direction = 'buy'
                    confidence = float(min(0.85, 0.5 + 0.15 * (latest_volume / (latest_vol_ma + 1e-8))))
                    rationale = (f"Bullish breakout above dynamic Donchian High ({donchian_high:.5f}) "
                                 f"with volume confirmation (Z-score: {latest_vol_z:.2f}) and trend alignment.")
                    tags.extend(["bullish_breakout", "trend_aligned"])
                elif volume_confirmed:
                    direction = 'buy'
                    confidence = 0.60
                    rationale = (f"Bullish breakout above dynamic Donchian High ({donchian_high:.5f}) "
                                 f"with volume confirmation, but counter-trend.")
                    tags.extend(["bullish_breakout", "counter_trend"])

            elif breakout_low:
                if volume_confirmed and bearish_trend:
                    direction = 'sell'
                    confidence = float(min(0.85, 0.5 + 0.15 * (latest_volume / (latest_vol_ma + 1e-8))))
                    rationale = (f"Bearish breakout below dynamic Donchian Low ({donchian_low:.5f}) "
                                 f"with volume confirmation (Z-score: {latest_vol_z:.2f}) and trend alignment.")
                    tags.extend(["bearish_breakout", "trend_aligned"])
                elif volume_confirmed:
                    direction = 'sell'
                    confidence = 0.60
                    rationale = (f"Bearish breakout below dynamic Donchian Low ({donchian_low:.5f}) "
                                 f"with volume confirmation, but counter-trend.")
                    tags.extend(["bearish_breakout", "counter_trend"])

            if direction is None:
                direction = None
                confidence = 0.0
                rationale = (f"Price ({latest_close:.5f}) remains within dynamic Donchian Channel "
                             f"[{donchian_low:.5f}, {donchian_high:.5f}] (Lookback: {lookback}).")
                tags.append("no_breakout")

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=direction,
                valid=True,
                confidence=confidence,
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
