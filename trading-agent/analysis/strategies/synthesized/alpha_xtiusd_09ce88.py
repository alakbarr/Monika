from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xtiusd_09ce88(EdgeStrategy):
    strategy_id: str = "alpha_xtiusd_09ce88"
    applicable_symbols: set = {"XTIUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        # Define hyperparameters
        self.ema_period = self.settings.get("ema_period", 20)
        self.atr_period = self.settings.get("atr_period", 14)
        self.atr_multiplier = self.settings.get("atr_multiplier", 2.2)
        self.rsi_period = self.settings.get("rsi_period", 14)

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            # Fetch H1 candles for robust intraday mean reversion signals
            candles = await self.get_historical_candles(
                session=session, 
                symbol=symbol, 
                timeframe='H1', 
                limit=100
            )
            
            required_len = max(self.ema_period, self.atr_period, self.rsi_period) + 10
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

            # Parse candles into a structured DataFrame
            data = []
            for c in candles:
                try:
                    close_val = float(c.close)
                    high_val = float(c.high)
                    low_val = float(c.low)
                    open_val = float(c.open)
                except AttributeError:
                    close_val = float(c['close'])
                    high_val = float(c['high'])
                    low_val = float(c['low'])
                    open_val = float(c['open'])
                
                data.append({
                    'open': open_val,
                    'high': high_val,
                    'low': low_val,
                    'close': close_val
                })
            
            df = pd.DataFrame(data)

            # Calculate Indicators
            # 1. EMA
            df['ema'] = df['close'].ewm(span=self.ema_period, adjust=False).mean()

            # 2. ATR (Average True Range)
            tr1 = df['high'] - df['low']
            tr2 = (df['high'] - df['close'].shift(1)).abs()
            tr3 = (df['low'] - df['close'].shift(1)).abs()
            df['tr'] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            df['atr'] = df['tr'].rolling(window=self.atr_period).mean()

            # 3. RSI (Relative Strength Index)
            delta = df['close'].diff()
            gain = (delta.clip(lower=0)).rolling(window=self.rsi_period).mean()
            loss = (-delta.clip(upper=0)).rolling(window=self.rsi_period).mean()
            rs = gain / loss.replace(0, 1e-9)
            df['rsi'] = 100 - (100 / (1 + rs))

            # Sanitize NaNs/Infs
            df = df.ffill().bfill().fillna(0.0)

            # Calculate Exhaustion Bands
            df['upper_band'] = df['ema'] + (self.atr_multiplier * df['atr'])
            df['lower_band'] = df['ema'] - (self.atr_multiplier * df['atr'])

            if len(df) < 2:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Failed to generate sufficient indicator rows.",
                    tags=["calculation_error"]
                )

            # Extract current and previous states
            curr = df.iloc[-1]
            prev = df.iloc[-2]

            curr_close = curr['close']
            curr_low = curr['low']
            curr_high = curr['high']
            curr_atr = curr['atr']
            curr_rsi = curr['rsi']
            curr_upper = curr['upper_band']
            curr_lower = curr['lower_band']

            prev_low = prev['low']
            prev_high = prev['high']
            prev_upper = prev['upper_band']
            prev_lower = prev['lower_band']

            direction = None
            confidence = 0.0
            rationale = ""
            tags = ["mean_reversion", "atr_exhaustion"]

            # Buy Signal: Price pierced the lower ATR band (exhaustion) and closed back above it, with RSI oversold
            if (prev_low < prev_lower or curr_low < curr_lower) and curr_close > curr_lower:
                if curr_rsi < 35:
                    direction = "buy"
                    rsi_factor = min(1.0, (35 - curr_rsi) / 20.0)
                    stretch_factor = min(1.0, (curr_lower - curr_low) / (curr_atr + 1e-9))
                    confidence = 0.6 + 0.2 * rsi_factor + 0.15 * stretch_factor
                    confidence = min(0.95, max(0.5, confidence))
                    rationale = (
                        f"XTIUSD oversold exhaustion. Low pierced lower ATR band ({curr_lower:.2f}), "
                        f"closed above at {curr_close:.2f} with RSI {curr_rsi:.1f}."
                    )
                    tags.append("bullish_exhaustion")

            # Sell Signal: Price pierced the upper ATR band (exhaustion) and closed back below it, with RSI overbought
            elif (prev_high > prev_upper or curr_high > curr_upper) and curr_close < curr_upper:
                if curr_rsi > 65:
                    direction = "sell"
                    rsi_factor = min(1.0, (curr_rsi - 65) / 20.0)
                    stretch_factor = min(1.0, (curr_high - curr_upper) / (curr_atr + 1e-9))
                    confidence = 0.6 + 0.2 * rsi_factor + 0.15 * stretch_factor
                    confidence = min(0.95, max(0.5, confidence))
                    rationale = (
                        f"XTIUSD overbought exhaustion. High pierced upper ATR band ({curr_upper:.2f}), "
                        f"closed below at {curr_close:.2f} with RSI {curr_rsi:.1f}."
                    )
                    tags.append("bearish_exhaustion")

            if direction is not None:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=direction,
                    valid=True,
                    confidence=round(confidence, 2),
                    rationale=rationale,
                    tags=tags
                )
            else:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="No ATR exhaustion or RSI confirmation detected.",
                    tags=["neutral"]
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
