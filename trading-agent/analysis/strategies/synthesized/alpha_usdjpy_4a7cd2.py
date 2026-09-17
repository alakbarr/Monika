from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_usdjpy_4a7cd2(EdgeStrategy):
    strategy_id: str = "alpha_usdjpy_4a7cd2"
    applicable_symbols: set = {"USDJPY"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.atr_period: int = self.settings.get("atr_period", 14)
        self.ema_period: int = self.settings.get("ema_period", 20)
        self.exhaustion_multiplier: float = self.settings.get("exhaustion_multiplier", 2.6)
        self.rsi_period: int = self.settings.get("rsi_period", 14)
        self.timeframe: str = self.settings.get("timeframe", "H1")
        self.min_history: int = 60

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        if symbol not in self.applicable_symbols:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale="Symbol not applicable for USDJPY ATR exhaustion strategy.",
                tags=["inapplicable_symbol"]
            )

        candles = await self.get_historical_candles(
            session=session,
            symbol=symbol,
            timeframe=self.timeframe,
            limit=100
        )

        if not candles or len(candles) < self.min_history:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale="Insufficient historical candle data.",
                tags=["insufficient_data"]
            )

        opens = np.array([float(c.open if hasattr(c, 'open') else c['open']) for c in candles], dtype=np.float64)
        highs = np.array([float(c.high if hasattr(c, 'high') else c['high']) for c in candles], dtype=np.float64)
        lows = np.array([float(c.low if hasattr(c, 'low') else c['low']) for c in candles], dtype=np.float64)
        closes = np.array([float(c.close if hasattr(c, 'close') else c['close']) for c in candles], dtype=np.float64)

        # Compute True Range and ATR
        tr1 = highs[1:] - lows[1:]
        tr2 = np.abs(highs[1:] - closes[:-1])
        tr3 = np.abs(lows[1:] - closes[:-1])
        tr = np.maximum(tr1, np.maximum(tr2, tr3))

        atr_series = pd.Series(tr).rolling(window=self.atr_period).mean().to_numpy()
        current_atr = float(atr_series[-1])

        if np.isnan(current_atr) or current_atr <= 0.0:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale="Invalid ATR calculation.",
                tags=["calculation_error"]
            )

        # Compute Central Trend Baseline (EMA)
        ema_series = pd.Series(closes).ewm(span=self.ema_period, adjust=False).mean().to_numpy()
        current_ema = float(ema_series[-1])

        # Compute RSI
        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0.0)
        losses = np.where(deltas < 0, -deltas, 0.0)
        avg_gain = pd.Series(gains).rolling(window=self.rsi_period).mean().to_numpy()
        avg_loss = pd.Series(losses).rolling(window=self.rsi_period).mean().to_numpy()
        
        last_gain = float(avg_gain[-1])
        last_loss = float(avg_loss[-1])
        if last_loss == 0.0:
            current_rsi = 100.0
        else:
            rs = last_gain / last_loss
            current_rsi = 100.0 - (100.0 / (1.0 + rs))

        current_close = closes[-1]
        current_high = highs[-1]
        current_low = lows[-1]
        current_open = opens[-1]

        upper_exhaustion = current_ema + (self.exhaustion_multiplier * current_atr)
        lower_exhaustion = current_ema - (self.exhaustion_multiplier * current_atr)

        distance_from_ema = current_close - current_ema
        normalized_distance = abs(distance_from_ema) / current_atr

        direction: Optional[str] = None
        confidence: float = 0.0
        rationale: str = "Price within normal ATR boundaries."
        tags: List[str] = ["mean_reversion", "atr_exhaustion", "usdjpy"]

        # Mean Reversion Sell Condition (Upper Exhaustion breached, rejection wick/reversal confirmation)
        if current_high >= upper_exhaustion and current_rsi >= 68.0:
            # Rejection wick or bearish close
            upper_wick = current_high - max(current_open, current_close)
            candle_range = current_high - current_low
            wick_ratio = upper_wick / candle_range if candle_range > 0 else 0.0

            if current_close < current_high and (wick_ratio >= 0.35 or current_close < current_open):
                direction = "sell"
                confidence = min(0.92, 0.55 + 0.10 * (normalized_distance - self.exhaustion_multiplier) + 0.05 * (current_rsi - 68.0) / 10.0)
                confidence = max(0.50, float(confidence))
                rationale = (
                    f"USDJPY overextended to upside: Price touched {current_high:.3f} (Upper Exhaustion: {upper_exhaustion:.3f}, "
                    f"Normalized Distance: {normalized_distance:.2f} ATR, RSI: {current_rsi:.1f}). Bearish rejection detected."
                )
                tags.extend(["overbought_exhaustion", "rejection_wick"])

        # Mean Reversion Buy Condition (Lower Exhaustion breached, rejection wick/reversal confirmation)
        elif current_low <= lower_exhaustion and current_rsi <= 32.0:
            # Rejection wick or bullish close
            lower_wick = min(current_open, current_close) - current_low
            candle_range = current_high - current_low
            wick_ratio = lower_wick / candle_range if candle_range > 0 else 0.0

            if current_close > current_low and (wick_ratio >= 0.35 or current_close > current_open):
                direction = "buy"
                confidence = min(0.92, 0.55 + 0.10 * (normalized_distance - self.exhaustion_multiplier) + 0.05 * (32.0 - current_rsi) / 10.0)
                confidence = max(0.50, float(confidence))
                rationale = (
                    f"USDJPY overextended to downside: Price touched {current_low:.3f} (Lower Exhaustion: {lower_exhaustion:.3f}, "
                    f"Normalized Distance: {normalized_distance:.2f} ATR, RSI: {current_rsi:.1f}). Bullish bounce detected."
                )
                tags.extend(["oversold_exhaustion", "rejection_wick"])

        valid = direction is not None

        return EdgeSignal(
            strategy_id=self.strategy_id,
            symbol=symbol,
            direction=direction,
            valid=valid,
            confidence=confidence,
            rationale=rationale,
            tags=tags
        )