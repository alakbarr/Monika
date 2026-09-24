from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_btcusd_8b05ec(EdgeStrategy):
    strategy_id: str = "alpha_btcusd_8b05ec"
    applicable_symbols: set = {"BTCUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.period = int(self.settings.get("period", 20))
        self.vol_threshold = float(self.settings.get("vol_threshold", 1.2))

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
                    rationale="Insufficient candle history for calculation",
                    tags=["insufficient_data"]
                )

            df = pd.DataFrame([{
                'high': float(c.high if hasattr(c, 'high') else c.get('high', 0.0)),
                'low': float(c.low if hasattr(c, 'low') else c.get('low', 0.0)),
                'close': float(c.close if hasattr(c, 'close') else c.get('close', 0.0)),
                'volume': float(c.volume if hasattr(c, 'volume') else c.get('volume', 0.0))
            } for c in candles])

            # Sanitize data
            df = df.replace([np.inf, -np.inf], np.nan).ffill().bfill().fillna(0.0)

            # Indicator calculations
            df['donchian_upper'] = df['high'].rolling(window=self.period, min_periods=1).max()
            df['donchian_lower'] = df['low'].rolling(window=self.period, min_periods=1).min()
            df['donchian_mid'] = (df['donchian_upper'] + df['donchian_lower']) / 2.0
            
            df['vol_sma'] = df['volume'].rolling(window=self.period, min_periods=1).mean()
            df['vol_sma'] = df['vol_sma'].replace(0.0, 1.0)
            df['vol_ratio'] = df['volume'] / df['vol_sma']
            df['vol_ratio'] = df['vol_ratio'].replace([np.inf, -np.inf], np.nan).fillna(1.0)

            df['prev_upper'] = df['donchian_upper'].shift(1).fillna(df['donchian_upper'])
            df['prev_lower'] = df['donchian_lower'].shift(1).fillna(df['donchian_lower'])

            latest = df.iloc[-1]
            close = float(latest['close'])
            donchian_upper = float(latest['donchian_upper'])
            donchian_lower = float(latest['donchian_lower'])
            donchian_mid = float(latest['donchian_mid'])
            vol_ratio = float(latest['vol_ratio'])
            prev_upper = float(latest['prev_upper'])
            prev_lower = float(latest['prev_lower'])

            direction = None
            confidence = 0.5
            rationale = "Price is within Donchian channel bounds."
            tags = ["donchian", "volume_weighted"]

            if close > prev_upper and vol_ratio >= self.vol_threshold:
                direction = 'buy'
                confidence = min(0.95, 0.5 + (vol_ratio - self.vol_threshold) * 0.15)
                rationale = f"Bullish volume-weighted Donchian breakout. Close: {close}, Upper: {prev_upper}, VolRatio: {vol_ratio:.2f}"
                tags.append("breakout_buy")
            elif close < prev_lower and vol_ratio >= self.vol_threshold:
                direction = 'sell'
                confidence = min(0.95, 0.5 + (vol_ratio - self.vol_threshold) * 0.15)
                rationale = f"Bearish volume-weighted Donchian breakout. Close: {close}, Lower: {prev_lower}, VolRatio: {vol_ratio:.2f}"
                tags.append("breakout_sell")

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
