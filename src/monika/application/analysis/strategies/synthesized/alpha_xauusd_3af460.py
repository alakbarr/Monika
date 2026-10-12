from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xauusd_3af460(EdgeStrategy):
    strategy_id: str = "alpha_xauusd_3af460"
    applicable_symbols: set = {"XAUUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.atr_period = int(self.settings.get('atr_period', 14))
        self.sma_period = int(self.settings.get('sma_period', 50))
        self.exhaustion_mult = float(self.settings.get('exhaustion_mult', 2.5))
        self.timeframe = str(self.settings.get('timeframe', 'H1'))
        self.limit = int(self.settings.get('limit', 100))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            candles = await self.get_historical_candles(
                session=session, 
                symbol=symbol, 
                timeframe=self.timeframe, 
                limit=self.limit
            )
            
            if not candles or len(candles) < max(self.atr_period, self.sma_period) + 5:
                return EdgeSignal(
                    strategy_id=self.strategy_id, 
                    symbol=symbol, 
                    direction=None, 
                    valid=False, 
                    confidence=0.0, 
                    rationale="Insufficient candle data", 
                    tags=["insufficient_data"]
                )

            df = pd.DataFrame([{
                'timestamp': getattr(c, 'timestamp', getattr(c, 'time', None)),
                'open': float(getattr(c, 'open', c.get('open', 0.0))),
                'high': float(getattr(c, 'high', c.get('high', 0.0))),
                'low': float(getattr(c, 'low', c.get('low', 0.0))),
                'close': float(getattr(c, 'close', c.get('close', 0.0))),
                'volume': float(getattr(c, 'volume', c.get('volume', 0.0)))
            } for c in candles])

            df['high_low'] = df['high'] - df['low']
            df['high_close'] = (df['high'] - df['close'].shift()).abs()
            df['low_close'] = (df['low'] - df['close'].shift()).abs()
            df['tr'] = df[['high_low', 'high_close', 'low_close']].max(axis=1)
            df['atr'] = df['tr'].rolling(window=self.atr_period, min_periods=1).mean()
            df['sma'] = df['close'].rolling(window=self.sma_period, min_periods=1).mean()

            df['atr'] = df['atr'].ffill().bfill().fillna(0.0)
            df['sma'] = df['sma'].ffill().bfill().fillna(df['close'])

            latest = df.iloc[-1]
            close = float(latest['close'])
            sma = float(latest['sma'])
            atr = float(latest['atr'])
            high = float(latest['high'])
            low = float(latest['low'])

            if atr <= 0:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="ATR is zero or invalid",
                    tags=["invalid_atr"]
                )

            distance = close - sma
            threshold = atr * self.exhaustion_mult

            direction = None
            confidence = 0.0
            rationale = ""
            tags = ["mean_reversion", "atr_exhaustion"]

            if distance > threshold:
                direction = 'sell'
                confidence = min(0.95, 0.5 + (abs(distance) - threshold) / (threshold * 2.0))
                rationale = f"Price exhausted upwards: distance {distance:.2f} > threshold {threshold:.2f}"
                tags.append("exhaustion_up")
            elif distance < -threshold:
                direction = 'buy'
                confidence = min(0.95, 0.5 + (abs(distance) - threshold) / (threshold * 2.0))
                rationale = f"Price exhausted downwards: distance {distance:.2f} < -threshold {-threshold:.2f}"
                tags.append("exhaustion_down")
            else:
                direction = None
                confidence = 0.1
                rationale = f"Price within normal range of SMA: distance {distance:.2f}"
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
