from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xbrusd_945526(EdgeStrategy):
    strategy_id: str = "alpha_xbrusd_945526"
    applicable_symbols: set = {"XBRUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.donchian_period = int(self.settings.get('donchian_period', 20))
        self.volume_multiplier = float(self.settings.get('volume_multiplier', 1.5))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe='H1', limit=100)
            if not candles or len(candles) < self.donchian_period + 5:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient historical candle data for volume-weighted Donchian calculation.",
                    tags=["insufficient_data"]
                )

            df = pd.DataFrame([{
                'high': float(c.high),
                'low': float(c.low),
                'close': float(c.close),
                'volume': float(c.volume) if hasattr(c, 'volume') and c.volume is not None else 1.0
            } for c in candles])

            # Calculate Donchian Channels
            df['donchian_high'] = df['high'].rolling(window=self.donchian_period, min_periods=1).max()
            df['donchian_low'] = df['low'].rolling(window=self.donchian_period, min_periods=1).min()
            df['donchian_mid'] = (df['donchian_high'] + df['donchian_low']) / 2.0
            
            # Channel expansion metrics
            df['channel_width'] = df['donchian_high'] - df['donchian_low']
            df['width_ma'] = df['channel_width'].rolling(window=self.donchian_period, min_periods=1).mean()

            # Volume weighting metrics
            df['vol_ma'] = df['volume'].rolling(window=self.donchian_period, min_periods=1).mean()
            df['vol_ratio'] = df['volume'] / df['vol_ma'].replace(0, np.nan)
            
            # Sanitize data to prevent NaNs or Infs
            df = df.ffill().bfill().fillna(0.0)
            df['vol_ratio'] = df['vol_ratio'].replace([np.inf, -np.inf], 1.0)

            latest = df.iloc[-1]
            prev = df.iloc[-2]

            close = float(latest['close'])
            donchian_high = float(latest['donchian_high'])
            donchian_low = float(latest['donchian_low'])
            donchian_mid = float(latest['donchian_mid'])
            channel_width = float(latest['channel_width'])
            width_ma = float(latest['width_ma'])
            vol_ratio = float(latest['vol_ratio'])
            prev_donchian_high = float(prev['donchian_high'])
            prev_donchian_low = float(prev['donchian_low'])

            direction = None
            confidence = 0.0
            rationale = "Market is trading within normal dynamic Donchian bounds."
            tags = ["donchian", "volume_weighted", "neutral"]

            # Breakout conditions with volume confirmation and channel expansion
            is_expanding = channel_width > width_ma
            has_volume = vol_ratio >= self.volume_multiplier

            if close > prev_donchian_high and is_expanding and has_volume:
                direction = 'buy'
                confidence = min(0.92, 0.6 + (vol_ratio - self.volume_multiplier) * 0.1)
                rationale = f"Bullish breakout above Donchian high with volume ratio {vol_ratio:.2f} and expanding channel width."
                tags = ["donchian", "volume_weighted", "breakout", "buy"]
            elif close < prev_donchian_low and is_expanding and has_volume:
                direction = 'sell'
                confidence = min(0.92, 0.6 + (vol_ratio - self.volume_multiplier) * 0.1)
                rationale = f"Bearish breakout below Donchian low with volume ratio {vol_ratio:.2f} and expanding channel width."
                tags = ["donchian", "volume_weighted", "breakout", "sell"]
            else:
                confidence = 0.4
                rationale = f"No valid expansion breakout detected. Vol ratio: {vol_ratio:.2f}, Width vs MA: {channel_width:.4f}/{width_ma:.4f}"

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
