from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xauusd_5e8d45(EdgeStrategy):
    strategy_id: str = "alpha_xauusd_5e8d45"
    applicable_symbols: set = {"XAUUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        # Define hyperparameters here
        self.lookback_period = 20
        self.volume_ma_period = 10
        self.expansion_threshold = 1.5
        self.confidence_base = 0.5
        self.confidence_max = 0.95

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            # Fetch candle history
            candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe='H1', limit=100)
            
            if not candles or len(candles) < self.lookback_period + self.volume_ma_period:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient historical data",
                    tags=["insufficient_data"]
                )

            # Convert to DataFrame for easier manipulation
            df = pd.DataFrame([
                {
                    'high': c.high,
                    'low': c.low,
                    'close': c.close,
                    'volume': getattr(c, 'volume', 0.0)
                }
                for c in candles
            ])

            # Ensure numeric types
            for col in ['high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')

            # Handle NaNs
            df = df.ffill().bfill().fillna(0.0)

            # Calculate Donchian Channels
            df['donchian_high'] = df['high'].rolling(window=self.lookback_period, min_periods=1).max()
            df['donchian_low'] = df['low'].rolling(window=self.lookback_period, min_periods=1).min()
            df['donchian_mid'] = (df['donchian_high'] + df['donchian_low']) / 2
            df['donchian_width'] = df['donchian_high'] - df['donchian_low']

            # Calculate Volume Moving Average
            df['volume_ma'] = df['volume'].rolling(window=self.volume_ma_period, min_periods=1).mean()

            # Calculate Volume-Weighted Expansion Factor
            # Normalize volume to avoid scale issues
            max_vol = df['volume'].max()
            if max_vol > 0:
                df['volume_norm'] = df['volume'] / max_vol
            else:
                df['volume_norm'] = 0.0

            # Dynamic expansion: adjust threshold based on recent volatility
            # Use ATR-like measure for volatility context
            tr = pd.concat([
                df['high'] - df['low'],
                (df['high'] - df['close'].shift(1)).abs(),
                (df['low'] - df['close'].shift(1)).abs()
            ], axis=1).max(axis=1)
            df['atr'] = tr.rolling(window=self.lookback_period, min_periods=1).mean()

            # Volume-weighted dynamic threshold
            # Higher volume -> lower threshold (more sensitive)
            # Lower volume -> higher threshold (less sensitive)
            vol_factor = df['volume_norm'].iloc[-1]
            dynamic_threshold = self.expansion_threshold * (1.0 - 0.5 * vol_factor)

            # Current Donchian width vs average width
            avg_width = df['donchian_width'].rolling(window=self.lookback_period, min_periods=1).mean().iloc[-1]
            current_width = df['donchian_width'].iloc[-1]

            # Expansion ratio
            if avg_width > 0:
                expansion_ratio = current_width / avg_width
            else:
                expansion_ratio = 1.0

            # Signal logic
            current_close = df['close'].iloc[-1]
            current_high = df['high'].iloc[-1]
            current_low = df['low'].iloc[-1]
            donchian_high = df['donchian_high'].iloc[-1]
            donchian_low = df['donchian_low'].iloc[-1]
            donchian_mid = df['donchian_mid'].iloc[-1]

            direction = None
            confidence = self.confidence_base
            rationale = "No signal"
            tags = []

            # Check for expansion
            is_expanding = expansion_ratio > dynamic_threshold

            if is_expanding:
                # Price near upper Donchian -> potential breakout up
                if current_close > donchian_mid and current_close >= donchian_high * 0.999:
                    direction = 'buy'
                    confidence = min(self.confidence_max, self.confidence_base + 0.3 * vol_factor + 0.2 * (expansion_ratio - dynamic_threshold))
                    rationale = f"Volume-weighted Donchian expansion upward. Expansion ratio: {expansion_ratio:.2f}, Threshold: {dynamic_threshold:.2f}, Volume factor: {vol_factor:.2f}"
                    tags = ["donchian_expansion", "breakout_up", "volume_weighted"]
                # Price near lower Donchian -> potential breakout down
                elif current_close < donchian_mid and current_close <= donchian_low * 1.001:
                    direction = 'sell'
                    confidence = min(self.confidence_max, self.confidence_base + 0.3 * vol_factor + 0.2 * (expansion_ratio - dynamic_threshold))
                    rationale = f"Volume-weighted Donchian expansion downward. Expansion ratio: {expansion_ratio:.2f}, Threshold: {dynamic_threshold:.2f}, Volume factor: {vol_factor:.2f}"
                    tags = ["donchian_expansion", "breakout_down", "volume_weighted"]
                else:
                    rationale = f"Donchian expansion detected but price not at channel edge. Expansion ratio: {expansion_ratio:.2f}"
                    tags = ["donchian_expansion", "no_edge"]
            else:
                rationale = f"No significant Donchian expansion. Expansion ratio: {expansion_ratio:.2f}, Threshold: {dynamic_threshold:.2f}"
                tags = ["no_expansion"]

            # Additional filter: ATR sanity check
            if df['atr'].iloc[-1] <= 0:
                direction = None
                confidence = 0.0
                rationale = "Invalid ATR value"
                tags = ["invalid_atr"]

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=direction,
                valid=direction is not None,
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
