from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_usdjpy_159711(EdgeStrategy):
    strategy_id: str = "alpha_usdjpy_159711"
    applicable_symbols: set = {"USDJPY"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        # Define hyperparameters
        self.atr_period: int = self.settings.get("atr_period", 14)
        self.ma_period: int = self.settings.get("ma_period", 20)
        self.atr_multiplier: float = self.settings.get("atr_multiplier", 2.5)
        self.rsi_period: int = self.settings.get("rsi_period", 14)

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        # Fetch H1 candles for USDJPY
        candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe='H1', limit=100)
        
        if not candles or len(candles) < max(self.atr_period, self.ma_period, self.rsi_period) + 5:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale="Insufficient candle history for indicator calculation.",
                tags=["insufficient_data"]
            )

        # Parse candles safely into a DataFrame
        data = []
        for c in candles:
            if hasattr(c, 'high'):
                data.append({
                    'high': float(c.high),
                    'low': float(c.low),
                    'close': float(c.close),
                    'open': float(c.open)
                })
            elif isinstance(c, dict):
                data.append({
                    'high': float(c.get('high', 0)),
                    'low': float(c.get('low', 0)),
                    'close': float(c.get('close', 0)),
                    'open': float(c.get('open', 0))
                })
        
        df = pd.DataFrame(data)

        # Calculate ATR (Average True Range)
        high = df['high']
        low = df['low']
        close = df['close']
        prev_close = close.shift(1)
        
        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=self.atr_period).mean()

        # Calculate Basis (EMA)
        ema = close.ewm(span=self.ma_period, adjust=False).mean()

        # Calculate RSI for exhaustion confirmation
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(window=self.rsi_period).mean()
        avg_loss = loss.rolling(window=self.rsi_period).mean()
        rs = avg_gain / (avg_loss + 1e-9)
        rsi = 100 - (100 / (1 + rs))

        # Extract current and previous values
        curr_close = close.iloc[-1]
        prev_close_val = close.iloc[-2]
        curr_ema = ema.iloc[-1]
        prev_ema = ema.iloc[-2]
        curr_atr = atr.iloc[-1]
        prev_atr = atr.iloc[-2]
        curr_rsi = rsi.iloc[-1]

        # Calculate exhaustion bands
        upper_band_curr = curr_ema + (self.atr_multiplier * curr_atr)
        upper_band_prev = prev_ema + (self.atr_multiplier * prev_atr)
        lower_band_curr = curr_ema - (self.atr_multiplier * curr_atr)
        lower_band_prev = prev_ema - (self.atr_multiplier * prev_atr)

        direction = None
        confidence = 0.0
        rationale = "Price action within normal ATR bands."
        tags = ["mean_reversion", "atr_exhaustion"]

        # Check for Bearish Reversion (Short)
        # Previous close was above the upper band (exhaustion), current close reverted back below
        if prev_close_val > upper_band_prev and curr_close < upper_band_curr and curr_rsi > 65:
            direction = "sell"
            confidence = float(min(0.90, 0.5 + (curr_rsi - 65) / 70))
            rationale = (
                f"USDJPY ATR exhaustion short triggered. Prev close ({prev_close_val:.3f}) "
                f"was above Upper Band ({upper_band_prev:.3f}), current close ({curr_close:.3f}) "
                f"reverted inside. RSI: {curr_rsi:.1f}."
            )
            tags.append("bearish_exhaustion")

        # Check for Bullish Reversion (Long)
        # Previous close was below the lower band (exhaustion), current close reverted back above
        elif prev_close_val < lower_band_prev and curr_close > lower_band_curr and curr_rsi < 35:
            direction = "buy"
            confidence = float(min(0.90, 0.5 + (35 - curr_rsi) / 70))
            rationale = (
                f"USDJPY ATR exhaustion long triggered. Prev close ({prev_close_val:.3f}) "
                f"was below Lower Band ({lower_band_prev:.3f}), current close ({curr_close:.3f}) "
                f"reverted inside. RSI: {curr_rsi:.1f}."
            )
            tags.append("bullish_exhaustion")

        valid = direction is not None

        return EdgeSignal(
            strategy_id=self.strategy_id,
            symbol=symbol,
            direction=direction,
            valid=valid,
            confidence=confidence if valid else 0.0,
            rationale=rationale,
            tags=tags
        )