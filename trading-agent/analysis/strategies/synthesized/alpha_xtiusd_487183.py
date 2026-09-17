from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xtiusd_487183(EdgeStrategy):
    strategy_id: str = "alpha_xtiusd_487183"
    applicable_symbols: set = {"XTIUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.lookback = self.settings.get("lookback", 20)
        self.atr_period = self.settings.get("atr_period", 14)
        self.vol_period = self.settings.get("vol_period", 20)
        self.expansion_multiplier = self.settings.get("expansion_multiplier", 0.6)

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            if symbol not in self.applicable_symbols:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale=f"Symbol {symbol} is not supported by this strategy.",
                    tags=["unsupported_symbol"]
                )

            # Fetch historical candles (H1 timeframe is optimal for XTIUSD swing breakouts)
            candles = await self.get_historical_candles(
                session=session,
                symbol=symbol,
                timeframe='H1',
                limit=100
            )

            required_len = max(self.lookback, self.atr_period, self.vol_period) + 5
            if not candles or len(candles) < required_len:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale=f"Insufficient candle history. Required: {required_len}, Got: {len(candles) if candles else 0}",
                    tags=["insufficient_data"]
                )

            # Parse candles safely supporting both object and dict interfaces
            data = []
            for c in candles:
                try:
                    h = float(c.high)
                    l = float(c.low)
                    cl = float(c.close)
                    v = float(c.volume)
                except (AttributeError, TypeError, KeyError):
                    h = float(c['high'])
                    l = float(c['low'])
                    cl = float(c['close'])
                    v = float(c['volume'])
                data.append({'high': h, 'low': l, 'close': cl, 'volume': v})

            df = pd.DataFrame(data)
            df = df.ffill().bfill().fillna(0.0)

            # Calculate Average True Range (ATR)
            high = df['high']
            low = df['low']
            close = df['close']
            prev_close = close.shift(1)

            tr1 = high - low
            tr2 = (high - prev_close).abs()
            tr3 = (low - prev_close).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            df['atr'] = tr.rolling(window=self.atr_period, min_periods=1).mean()

            # Calculate Volume Moving Average
            df['vol_ma'] = df['volume'].rolling(window=self.vol_period, min_periods=1).mean()

            # Standard Donchian Channels (shifted to avoid lookahead bias)
            df['donchian_high'] = df['high'].shift(1).rolling(window=self.lookback, min_periods=1).max()
            df['donchian_low'] = df['low'].shift(1).rolling(window=self.lookback, min_periods=1).min()

            # Volume-weighted dynamic expansion factor
            df['vol_ratio'] = df['volume'] / (df['vol_ma'] + 1e-8)
            df['vol_ratio_clipped'] = df['vol_ratio'].clip(0.5, 3.0)

            # Dynamic Bands: Expand the Donchian channel when volume surges
            df['dynamic_upper'] = df['donchian_high'] + (df['atr'] * self.expansion_multiplier * df['vol_ratio_clipped'])
            df['dynamic_lower'] = df['donchian_low'] - (df['atr'] * self.expansion_multiplier * df['vol_ratio_clipped'])

            # Extract current metrics
            last_idx = df.index[-1]
            curr_close = df.loc[last_idx, 'close']
            curr_vol_ratio = df.loc[last_idx, 'vol_ratio']
            dynamic_upper = df.loc[last_idx, 'dynamic_upper']
            dynamic_lower = df.loc[last_idx, 'dynamic_lower']

            direction = None
            confidence = 0.0
            rationale = "Price remains within the dynamic volume-weighted Donchian boundaries."
            tags = ["neutral", "congestion"]

            # Breakout Logic
            if curr_close > dynamic_upper and curr_vol_ratio > 1.15:
                direction = 'buy'
                breakout_pct = (curr_close - dynamic_upper) / (curr_close + 1e-8)
                confidence = min(0.60 + (curr_vol_ratio - 1.15) * 0.12 + breakout_pct * 10.0, 0.95)
                rationale = (
                    f"Bullish dynamic Donchian expansion breakout. Close ({curr_close:.2f}) "
                    f"exceeded Upper Band ({dynamic_upper:.2f}) with elevated Volume Ratio ({curr_vol_ratio:.2f}x)."
                )
                tags = ["breakout", "bullish", "volume_expansion"]

            elif curr_close < dynamic_lower and curr_vol_ratio > 1.15:
                direction = 'sell'
                breakout_pct = (dynamic_lower - curr_close) / (curr_close + 1e-8)
                confidence = min(0.60 + (curr_vol_ratio - 1.15) * 0.12 + breakout_pct * 10.0, 0.95)
                rationale = (
                    f"Bearish dynamic Donchian expansion breakout. Close ({curr_close:.2f}) "
                    f"dropped below Lower Band ({dynamic_lower:.2f}) with elevated Volume Ratio ({curr_vol_ratio:.2f}x)."
                )
                tags = ["breakout", "bearish", "volume_expansion"]

            # Sanitize confidence
            confidence = float(np.nan_to_num(confidence, nan=0.0, posinf=0.0, neginf=0.0))

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
