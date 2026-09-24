from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_gbpusd_e73efc(EdgeStrategy):
    strategy_id: str = "alpha_gbpusd_e73efc"
    applicable_symbols: set = {"GBPUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.lookback_period = int(self.settings.get("lookback_period", 20))
        self.volume_ma_period = int(self.settings.get("volume_ma_period", 20))
        self.atr_period = int(self.settings.get("atr_period", 14))
        self.confidence_threshold = float(self.settings.get("confidence_threshold", 0.65))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe='H1', limit=100)
            if not candles or len(candles) < max(self.lookback_period, self.volume_ma_period, self.atr_period) + 5:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient historical data for indicator calculation",
                    tags=["insufficient_data"]
                )

            df = pd.DataFrame([{
                'open': float(c.open),
                'high': float(c.high),
                'low': float(c.low),
                'close': float(c.close),
                'volume': float(getattr(c, 'volume', 1.0) or 1.0)
            } for c in candles])

            df['high'] = df['high'].ffill().bfill()
            df['low'] = df['low'].ffill().bfill()
            df['close'] = df['close'].ffill().bfill()
            df['volume'] = df['volume'].ffill().bfill().replace(0, 1.0)

            # Volume-weighted Donchian expansion concept
            df['donchian_upper'] = df['high'].rolling(window=self.lookbacked_period if hasattr(self, 'lookbacked_period') else self.lookback_period, min_periods=1).max()
            df['donchian_lower'] = df['low'].rolling(window=self.lookback_period, min_periods=1).min()
            df['donchian_mid'] = (df['donchian_upper'] + df['donchian_lower']) / 2.0

            df['vol_ma'] = df['volume'].rolling(window=self.volume_ma_period, min_periods=1).mean()
            df['vol_ratio'] = df['volume'] / df['vol_ma']
            df['vol_ratio'] = df['vol_ratio'].replace([np.inf, -np.inf], 1.0).fillna(1.0)

            # ATR calculation
            prev_close = df['close'].shift(1)
            tr1 = df['high'] - df['low']
            tr2 = (df['high'] - prev_close).abs()
            tr3 = (df['low'] - prev_close).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            df['atr'] = tr.rolling(window=self.atr_period, min_periods=1).mean().ffill().bfill()

            latest = df.iloc[-1]
            donchian_upper = float(latest['donchian_upper'])
            donchian_lower = float(latest['donchian_lower'])
            donchian_mid = float(latest['donchian_mid'])
            vol_ratio = float(latest['vol_ratio'])
            atr = float(latest['atr'])
            close_val = float(latest['close'])

            band_width = donchian_upper - donchian_lower
            if band_width <= 0:
                band_width = 0.0001

            direction = None
            confidence = 0.0
            rationale = "Market within normal Donchian bounds with neutral volume"
            tags = ["neutral", "volume_weighted_donchian"]

            # Breakout logic with volume weighting
            if close_val >= donchian_upper * 0.999 and vol_ratio > 1.2:
                direction = 'buy'
                confidence = min(0.95, 0.5 + (vol_ratio - 1.0) * 0.2)
                rationale = f"Bullish breakout above upper Donchian band with high volume ratio {vol_ratio:.2f}"
                tags = ["breakout", "buy", "volume_expansion"]
            elif close_val <= donchian_lower * 1.001 and vol_ratio > 1.2:
                direction = 'sell'
                confidence = min(0.95, 0.5 + (vol_ratio - 1.0) * 0.2)
                rationale = f"Bearish breakout below lower Donchian band with high volume ratio {vol_ratio:.2f}"
                tags = ["breakout", "sell", "volume_expansion"]
            else:
                if close_val > donchian_mid:
                    confidence = 0.45
                    rationale = "Price above Donchian midpoint, weak bullish bias"
                    tags = ["neutral_bullish"]
                else:
                    confidence = 0.45
                    rationale = "Price below Donchian midpoint, weak bearish bias"
                    tags = ["neutral_bearish"]

            valid = confidence >= self.confidence_threshold or direction is not None

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=direction,
                valid=bool(valid),
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
