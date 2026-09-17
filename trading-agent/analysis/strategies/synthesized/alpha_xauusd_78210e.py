from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xauusd_78210e(EdgeStrategy):
    strategy_id: str = "alpha_xauusd_78210e"
    applicable_symbols: set = {"XAUUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        # Define hyperparameters here
        self.atr_period = 14
        self.exhaustion_threshold = 1.5  # ATR exhaustion threshold (multiple of rolling mean ATR)
        self.rolling_window = 20  # Rolling window for ATR mean
        self.price_deviation_threshold = 0.5  # Price deviation from rolling mean (in ATR units)
        self.min_confidence = 0.6  # Minimum confidence to generate a signal

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            # Fetch candle history
            candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe='H1', limit=100)
            
            if not candles or len(candles) < self.rolling_window + self.atr_period:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient historical data for ATR calculation",
                    tags=["insufficient_data"]
                )
            
            # Convert to DataFrame
            df = pd.DataFrame([
                {
                    'high': c.high,
                    'low': c.low,
                    'close': c.close,
                    'open': c.open
                } for c in candles
            ])
            
            # Calculate True Range
            df['tr'] = np.maximum(
                df['high'] - df['low'],
                np.maximum(
                    abs(df['high'] - df['close'].shift(1)),
                    abs(df['low'] - df['close'].shift(1))
                )
            )
            
            # Calculate ATR
            df['atr'] = df['tr'].rolling(window=self.atr_period, min_periods=1).mean()
            
            # Calculate rolling mean of ATR
            df['atr_mean'] = df['atr'].rolling(window=self.rolling_window, min_periods=1).mean()
            
            # Calculate ATR exhaustion ratio
            df['atr_ratio'] = df['atr'] / df['atr_mean'].replace(0, np.nan)
            
            # Calculate rolling mean of close price
            df['close_mean'] = df['close'].rolling(window=self.rolling_window, min_periods=1).mean()
            
            # Calculate price deviation in ATR units
            df['price_deviation'] = (df['close'] - df['close_mean']) / df['atr'].replace(0, np.nan)
            
            # Sanitize NaNs and Infs
            df['atr_ratio'] = df['atr_ratio'].replace([np.inf, -np.inf], np.nan).ffill().bfill().fillna(1.0)
            df['price_deviation'] = df['price_deviation'].replace([np.inf, -np.inf], np.nan).ffill().bfill().fillna(0.0)
            
            # Get latest values
            latest_atr_ratio = df['atr_ratio'].iloc[-1]
            latest_price_deviation = df['price_deviation'].iloc[-1]
            latest_close = df['close'].iloc[-1]
            latest_close_mean = df['close_mean'].iloc[-1]
            
            # Check for ATR exhaustion (low volatility)
            atr_exhausted = latest_atr_ratio < (1.0 / self.exhaustion_threshold)
            
            # Determine direction based on price deviation from mean
            if atr_exhausted:
                if latest_price_deviation < -self.price_deviation_threshold:
                    # Price is below mean, expect mean reversion upward
                    direction = 'buy'
                    confidence = min(1.0, abs(latest_price_deviation) / (self.price_deviation_threshold * 2))
                elif latest_price_deviation > self.price_deviation_threshold:
                    # Price is above mean, expect mean reversion downward
                    direction = 'sell'
                    confidence = min(1.0, abs(latest_price_deviation) / (self.price_deviation_threshold * 2))
                else:
                    direction = None
                    confidence = 0.0
            else:
                direction = None
                confidence = 0.0
            
            # Ensure confidence meets minimum threshold
            if direction is not None and confidence < self.min_confidence:
                direction = None
                confidence = 0.0
            
            rationale = (
                f"ATR exhaustion detected: ATR ratio={latest_atr_ratio:.3f} "
                f"(threshold={1.0/self.exhaustion_threshold:.3f}), "
                f"Price deviation={latest_price_deviation:.3f} ATR units "
                f"(threshold=±{self.price_deviation_threshold})"
            )
            
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=direction,
                valid=direction is not None,
                confidence=confidence,
                rationale=rationale,
                tags=["mean_reversion", "atr_exhaustion"]
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
