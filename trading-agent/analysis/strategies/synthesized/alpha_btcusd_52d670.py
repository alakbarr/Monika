from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_btcusd_52d670(EdgeStrategy):
    strategy_id: str = "alpha_btcusd_52d670"
    applicable_symbols: set = {"BTCUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.atr_period = int(self.settings.get("atr_period", 14))
        self.sma_period = int(self.settings.get("sma_period", 20))
        self.exhaustion_mult = float(self.settings.get("exhaustion_mult", 2.0))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe='H1', limit=100)
            if not candles or len(candles) < max(self.atr_period, self.sma_period) + 5:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient historical candle data",
                    tags=["insufficient_data"]
                )
            
            df = pd.DataFrame([{
                'high': float(c.high if hasattr(c, 'high') else c.get('high', 0.0)),
                'low': float(c.low if hasattr(c, 'low') else c.get('low', 0.0)),
                'close': float(c.close if hasattr(c, 'close') else c.get('close', 0.0))
            } for c in candles])

            df = df.ffill().bfill().fillna(0.0)

            # Calculate True Range and ATR
            df['prev_close'] = df['close'].shift(1)
            df['tr1'] = df['high'] - df['low']
            df['tr2'] = (df['high'] - df['prev_close']).abs()
            df['tr3'] = (df['low'] - df['prev_close']).abs()
            df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
            df['atr'] = df['tr'].rolling(window=self.atr_period, min_periods=1).mean()
            df['sma'] = df['close'].rolling(window=self.sma_period, min_periods=1).mean()

            df = df.replace([np.inf, -np.inf], np.nan).ffill().bfill().fillna(0.0)

            last_row = df.iloc[-1]
            close = float(last_row['close'])
            sma = float(last_row['sma'])
            atr = float(last_row['atr'])

            if atr <= 0.0:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="ATR is zero or negative, cannot compute exhaustion",
                    tags=["zero_atr"]
                )

            diff = close - sma
            threshold = self.exhaustion_mult * atr

            direction = None
            confidence = 0.0
            rationale = "Price within normal dispersion range"
            tags = ["mean_reversion", "atr_exhaustion"]

            if diff < -threshold:
                direction = 'buy'
                confidence = min(1.0, abs(diff) / (threshold * 1.5))
                rationale = f"Price exhausted below SMA by {-diff:.2f} (ATR: {atr:.2f}), triggering mean reversion buy"
                tags.append("exhaustion_buy")
            elif diff > threshold:
                direction = 'sell'
                confidence = min(1.0, diff / (threshold * 1.5))
                rationale = f"Price exhausted above SMA by {diff:.2f} (ATR: {atr:.2f}), triggering mean reversion sell"
                tags.append("exhaustion_sell")

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=direction,
                valid=True,
                confidence=float(confidence),
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
