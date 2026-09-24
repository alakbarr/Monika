from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_btcusd_db91cc(EdgeStrategy):
    strategy_id: str = "alpha_btcusd_db91cc"
    applicable_symbols: set = {"BTCUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.period = int(self.settings.get("period", 20))
        self.vol_period = int(self.settings.get("vol_period", 20))
        self.vol_mult = float(self.settings.get("vol_mult", 1.2))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe='H1', limit=100)
            if not candles or len(candles) < max(self.period, self.vol_period) + 5:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient historical data for Donchian expansion calculation",
                    tags=["insufficient_data"]
                )
            
            df = pd.DataFrame([{
                'high': float(c.high),
                'low': float(c.low),
                'close': float(c.close),
                'volume': float(c.volume)
            } for c in candles])
            
            df['donchian_high'] = df['high'].shift(1).rolling(window=self.period, min_periods=1).max()
            df['donchian_low'] = df['low'].shift(1).rolling(window=self.period, min_periods=1).min()
            df['vol_ma'] = df['volume'].rolling(window=self.vol_period, min_periods=1).mean()
            
            df = df.ffill().bfill().replace([np.inf, -np.inf], 0.0)
            
            latest = df.iloc[-1]
            close = float(latest['close'])
            donchian_high = float(latest['donchian_high'])
            donchian_low = float(latest['donchian_low'])
            volume = float(latest['volume'])
            vol_ma = float(latest['vol_ma'])
            
            direction = None
            confidence = 0.0
            rationale = "No volume-weighted Donchian breakout detected"
            tags = ["neutral"]
            
            vol_confirmed = volume > (vol_ma * self.vol_mult)
            
            if close > donchian_high and vol_confirmed:
                direction = 'buy'
                confidence = 0.80
                rationale = f"Bullish breakout above Donchian high ({donchian_high:.2f}) with volume expansion."
                tags = ["breakout", "volume_expansion", "buy"]
            elif close < donchian_low and vol_confirmed:
                direction = 'sell'
                confidence = 0.80
                rationale = f"Bearish breakout below Donchian low ({donchian_low:.2f}) with volume expansion."
                tags = ["breakout", "volume_expansion", "sell"]
            
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
