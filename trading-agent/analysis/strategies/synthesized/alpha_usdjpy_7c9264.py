from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_usdjpy_7c9264(EdgeStrategy):
    strategy_id: str = "alpha_usdjpy_7c9264"
    applicable_symbols: set = {"USDJPY"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        # Define hyperparameters here
        self.lookback_period = 20
        self.volume_lookback = 10
        self.expansion_threshold = 1.5
        self.confidence_base = 0.5
        self.confidence_max = 0.95

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            # Fetch candle history
            candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe='H1', limit=100)
            
            if not candles or len(candles) < self.lookback_period + self.volume_lookback:
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

            # Ensure numeric types and handle NaNs
            for col in ['high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            df = df.replace([np.inf, -np.inf], np.nan)
            df = df.ffill().bfill().fillna(0.0)

            # Calculate Donchian Channels
            df['donchian_high'] = df['high'].rolling(window=self.lookback_period, min_periods=1).max()
            df['donchian_low'] = df['low'].rolling(window=self.lookback_period, min_periods=1).min()
            df['donchian_mid'] = (df['donchian_high'] + df['donchian_low']) / 2
            df['donchian_width'] = df['donchian_high'] - df['donchian_low']

            # Calculate Volume-Weighted Average Price (VWAP) approximation for recent period
            # Using simple volume-weighted close for the lookback period
            df['vol_weighted_close'] = (df['close'] * df['volume']).rolling(window=self.volume_lookback, min_periods=1).sum() / \
                                       df['volume'].rolling(window=self.volume_lookback, min_periods=1).sum().replace(0, np.nan)
            df['vol_weighted_close'] = df['vol_weighted_close'].ffill().bfill().fillna(df['close'])

            # Calculate dynamic expansion factor based on volume
            # Higher volume should allow for wider Donchian bands to be considered significant
            avg_volume = df['volume'].rolling(window=self.volume_lookback, min_periods=1).mean()
            current_volume = df['volume'].iloc[-1]
            volume_ratio = current_volume / avg_volume.iloc[-1] if avg_volume.iloc[-1] > 0 else 1.0
            
            # Dynamic threshold: higher volume means we need more expansion to trigger
            dynamic_threshold = self.expansion_threshold * (1 + 0.1 * (volume_ratio - 1))
            dynamic_threshold = max(1.0, min(3.0, dynamic_threshold))  # Clamp between 1.0 and 3.0

            # Get latest values
            latest_close = df['close'].iloc[-1]
            latest_donchian_high = df['donchian_high'].iloc[-1]
            latest_donchian_low = df['donchian_low'].iloc[-1]
            latest_donchian_mid = df['donchian_mid'].iloc[-1]
            latest_donchian_width = df['donchian_width'].iloc[-1]
            latest_vwap = df['vol_weighted_close'].iloc[-1]

            # Previous Donchian width for comparison
            prev_donchian_width = df['donchian_width'].iloc[-2] if len(df) > 1 else latest_donchian_width

            # Calculate expansion ratio
            if prev_donchian_width > 0:
                expansion_ratio = latest_donchian_width / prev_donchian_width
            else:
                expansion_ratio = 1.0

            # Determine signal based on Donchian breakout and volume-weighted confirmation
            direction = None
            confidence = self.confidence_base
            rationale = "No signal generated"
            tags = ["neutral"]

            # Check for upward breakout
            if latest_close > latest_donchian_high and expansion_ratio > dynamic_threshold:
                direction = 'buy'
                # Confidence based on strength of breakout and volume
                breakout_strength = (latest_close - latest_donchian_high) / latest_donchian_width if latest_donchian_width > 0 else 0
                volume_confidence = min(1.0, volume_ratio / 2.0)
                confidence = self.confidence_base + 0.3 * min(1.0, breakout_strength * 2) + 0.15 * volume_confidence
                confidence = min(self.confidence_max, confidence)
                rationale = f"Upward Donchian breakout with {expansion_ratio:.2f}x expansion (threshold: {dynamic_threshold:.2f}), volume ratio: {volume_ratio:.2f}"
                tags = ["donchian_breakout", "volume_confirmed", "expansion"]

            # Check for downward breakout
            elif latest_close < latest_donchian_low and expansion_ratio > dynamic_threshold:
                direction = 'sell'
                breakout_strength = (latest_donchian_low - latest_close) / latest_donchian_width if latest_donchian_width > 0 else 0
                volume_confidence = min(1.0, volume_ratio / 2.0)
                confidence = self.confidence_base + 0.3 * min(1.0, breakout_strength * 2) + 0.15 * volume_confidence
                confidence = min(self.confidence_max, confidence)
                rationale = f"Downward Donchian breakout with {expansion_ratio:.2f}x expansion (threshold: {dynamic_threshold:.2f}), volume ratio: {volume_ratio:.2f}"
                tags = ["donchian_breakout", "volume_confirmed", "expansion"]

            # Check for mean reversion within expanding channel
            elif expansion_ratio > dynamic_threshold:
                # If channel is expanding but no breakout, check position relative to VWAP
                if latest_close > latest_vwap and latest_close > latest_donchian_mid:
                    direction = 'buy'
                    confidence = self.confidence_base + 0.1 * min(1.0, volume_ratio / 2.0)
                    rationale = f"Channel expansion ({expansion_ratio:.2f}x) with price above VWAP and midline, volume ratio: {volume_ratio:.2f}"
                    tags = ["channel_expansion", "vwap_bullish"]
                elif latest_close < latest_vwap and latest_close < latest_donchian_mid:
                    direction = 'sell'
                    confidence = self.confidence_base + 0.1 * min(1.0, volume_ratio / 2.0)
                    rationale = f"Channel expansion ({expansion_ratio:.2f}x) with price below VWAP and midline, volume ratio: {volume_ratio:.2f}"
                    tags = ["channel_expansion", "vwap_bearish"]

            # Ensure confidence is within valid range
            confidence = max(0.0, min(1.0, confidence))

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
