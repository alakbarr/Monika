from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xbrusd_9e8436(EdgeStrategy):
    strategy_id: str = "alpha_xbrusd_9e8436"
    applicable_symbols: set = {"XBRUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.period = int(self.settings.get("period", 20))
        self.volume_ma_period = int(self.settings.get("volume_ma_period", 20))
        self.volume_mult = float(self.settings.get("volume_mult", 1.2))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe='H1', limit=100)
            if not candles or len(candles) < self.period + 5:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient candle history for analysis",
                    tags=["insufficient_data"]
                )

            df = pd.DataFrame([{
                'high': float(c.high if hasattr(c, 'high') else c.get('high', 0.0)),
                'low': float(c.low if hasattr(c, 'low') else c.get('low', 0.0)),
                'close': float(c.close if hasattr(c, 'close') else c.get('close', 0.0)),
                'volume': float(c.volume if hasattr(c, 'volume') else c.get('volume', 0.0))
            } for c in candles])

            df = df.replace([np.inf, -np.inf], np.nan).ffill().bfill().fillna(0.0)

            # Volume-weighted Donchian channels expansion setup
            df['donchian_high'] = df['high'].rolling(window=self.period, min_periods=1).max()
            df['donchian_low'] = df['low'].rolling(window=self.period, min_periods=1).min()
            df['vol_ma'] = df['volume'].rolling(window=self.volume_ma_period, min_periods=1).mean()

            df = df.replace([np.inf, -np.inf], np.nan).ffill().bfill().fillna(0.0)

            current_close = df['close'].iloc[-1]
            prev_upper = df['donchian_high'].iloc[-2]
            prev_lower = df['donchian_low'].iloc[-2]
            current_vol = df['volume'].iloc[-1]
            current_vol_ma = df['vol_ma'].iloc[-1]

            direction = None
            confidence = 0.0
            rationale = "Price is trading within the dynamic Donchian boundaries."
            tags = ["donchian", "volume_expansion", "xbrusd"]

            vol_condition = current_vol > (current_vol_ma * self.volume_mult) if current_vol_ma > 0 else True

            if current_close > prev_upper and vol_condition:
                direction = 'buy'
                confidence = 0.72
                rationale = f"Bullish breakout above upper Donchian band ({prev_upper:.2f}) confirmed by volume expansion ({current_vol:.1f} vs MA {current_vol_ma:.1f})."
                tags.append("breakout_buy")
            elif current_close < prev_lower and vol_condition:
                direction = 'sell'
                confidence = 0.72
                rationale = f"Bearish breakdown below lower Donchian band ({prev_lower:.2f}) confirmed by volume expansion ({current_vol:.1f} vs MA {current_vol_ma:.1f})."
                tags.append("breakout_sell")
            else:
                confidence = 0.40
                rationale = "No decisive volume-backed Donchian expansion detected."

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
