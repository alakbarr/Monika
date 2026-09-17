from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xauusd_72bf31(EdgeStrategy):
    strategy_id: str = "alpha_xauusd_72bf31"
    applicable_symbols: set = {"XAUUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.atr_period = int(self.settings.get('atr_period', 14))
        self.ma_period = int(self.settings.get('ma_period', 50))
        self.exhaustion_threshold = float(self.settings.get('exhaustion_threshold', 2.2))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe='H1', limit=120)
            min_required = max(self.atr_period, self.ma_period) + 5
            if not candles or len(candles) < min_required:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient historical candle data for ATR exhaustion analysis.",
                    tags=["insufficient_data"]
                )

            highs = []
            lows = []
            closes = []
            for c in candles:
                h = c.high if hasattr(c, 'high') else c.get('high', 0.0)
                l = c.low if hasattr(c, 'low') else c.get('low', 0.0)
                cl = c.close if hasattr(c, 'close') else c.get('close', 0.0)
                highs.append(float(h))
                lows.append(float(l))
                closes.append(float(cl))

            df = pd.DataFrame({'high': highs, 'low': lows, 'close': closes})
            df = df.replace([np.inf, -np.inf], np.nan).ffill().bfill().fillna(0.0)

            # Average True Range (ATR) calculation
            prev_close = df['close'].shift(1)
            tr1 = df['high'] - df['low']
            tr2 = (df['high'] - prev_close).abs()
            tr3 = (df['low'] - prev_close).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr = tr.rolling(window=self.atr_period, min_periods=1).mean()

            # Baseline Moving Average
            ma = df['close'].rolling(window=self.ma_period, min_periods=1).mean()

            current_close = df['close'].iloc[-1]
            current_ma = ma.iloc[-1]
            current_atr = atr.iloc[-1]

            if current_atr <= 0 or math.isnan(current_atr):
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Calculated ATR is zero or invalid.",
                    tags=["zero_atr"]
                )

            deviation = current_close - current_ma
            exhaustion_ratio = deviation / current_atr

            direction = None
            confidence = 0.0
            rationale = ""
            tags = ["atr_exhaustion", "mean_reversion"]

            if exhaustion_ratio >= self.exhaustion_threshold:
                direction = 'sell'
                confidence = min(1.0, float(abs(exhaustion_ratio) / (self.exhaustion_threshold * 2.0)))
                rationale = f"Bullish ATR exhaustion detected: deviation={deviation:.2f}, ATR={current_atr:.2f}, ratio={exhaustion_ratio:.2f}"
                tags.append("overbought")
            elif exhaustion_ratio <= -self.exhaustion_threshold:
                direction = 'buy'
                confidence = min(1.0, float(abs(exhaustion_ratio) / (self.exhaustion_threshold * 2.0)))
                rationale = f"Bearish ATR exhaustion detected: deviation={deviation:.2f}, ATR={current_atr:.2f}, ratio={exhaustion_ratio:.2f}"
                tags.append("oversold")
            else:
                direction = None
                confidence = 0.0
                rationale = f"Price within normal volatility bands: deviation={deviation:.2f}, ATR={current_atr:.2f}, ratio={exhaustion_ratio:.2f}"
                tags.append("neutral")

            valid = direction is not None
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=direction,
                valid=valid,
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
