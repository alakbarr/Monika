from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xbrusd_3e1575(EdgeStrategy):
    strategy_id: str = "alpha_xbrusd_3e1575"
    applicable_symbols: set = {"XBRUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.lookback = int(self.settings.get("lookback", 20))
        self.volume_threshold = float(self.settings.get("volume_threshold", 1.2))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe='H1', limit=100)
            if not candles or len(candles) < self.lookback:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient candle history for Donchian expansion calculation",
                    tags=["insufficient_data"]
                )

            data = []
            for c in candles:
                data.append({
                    "high": float(c.high if hasattr(c, 'high') else c.get('high', 0.0)),
                    "low": float(c.low if hasattr(c, 'low') else c.get('low', 0.0)),
                    "close": float(c.close if hasattr(c, 'close') else c.get('close', 0.0)),
                    "volume": float(c.volume if hasattr(c, 'volume') else c.get('volume', 0.0))
                })

            df = pd.DataFrame(data)
            df = df.ffill().bfill()

            df['donchian_upper'] = df['high'].rolling(window=self.lookback, min_periods=1).max()
            df['donchian_lower'] = df['low'].rolling(window=self.lookback, min_periods=1).min()
            df['donchian_mid'] = (df['donchian_upper'] + df['donchian_lower']) / 2.0

            df['vol_ma'] = df['volume'].rolling(window=self.lookback, min_periods=1).mean()
            df['vol_ratio'] = df['volume'] / df['vol_ma'].replace(0, np.nan)
            df['vol_ratio'] = df['vol_ratio'].ffill().bfill().fillna(1.0).replace([np.inf, -np.inf], 1.0)

            df['bandwidth'] = (df['donchian_upper'] - df['donchian_lower']) / df['donchian_mid'].replace(0, np.nan)
            df['bandwidth'] = df['bandwidth'].ffill().bfill().fillna(0.0).replace([np.inf, -np.inf], 0.0)

            latest = df.iloc[-1]
            prev = df.iloc[-2] if len(df) > 1 else latest

            close = float(latest['close'])
            donchian_upper = float(latest['donchian_upper'])
            donchian_lower = float(latest['donchian_lower'])
            donchian_mid = float(latest['donchian_mid'])
            vol_ratio = float(latest['vol_ratio'])
            bandwidth = float(latest['bandwidth'])
            prev_upper = float(prev['donchian_upper'])
            prev_lower = float(prev['donchian_lower'])

            direction = None
            confidence = 0.0
            rationale = "Market within normal Donchian bounds"
            tags = ["neutral"]

            if close > prev_upper and vol_ratio >= self.volume_threshold:
                direction = "buy"
                confidence = min(0.95, 0.5 + (vol_ratio - self.volume_threshold) * 0.2 + bandwidth * 0.1)
                rationale = f"Bullish volume-weighted Donchian breakout. Close: {close}, Upper: {prev_upper}, VolRatio: {vol_ratio:.2f}"
                tags = ["breakout", "volume_expansion", "bullish"]
            elif close < prev_lower and vol_ratio >= self.volume_threshold:
                direction = "sell"
                confidence = min(0.95, 0.5 + (vol_ratio - self.volume_threshold) * 0.2 + bandwidth * 0.1)
                rationale = f"Bearish volume-weighted Donchian breakdown. Close: {close}, Lower: {prev_lower}, VolRatio: {vol_ratio:.2f}"
                tags = ["breakdown", "volume_expansion", "bearish"]
            else:
                confidence = 0.3
                rationale = f"No expansion trigger. Close: {close}, VolRatio: {vol_ratio:.2f}"
                tags = ["range_bound"]

            valid = direction is not None
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=direction,
                valid=valid,
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
