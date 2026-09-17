from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xauusd_96d26b(EdgeStrategy):
    strategy_id: str = "alpha_xauusd_96d26b"
    applicable_symbols: set = {"XAUUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.atr_period: int = int(self.settings.get("atr_period", 14))
        self.ma_period: int = int(self.settings.get("ma_period", 20))
        self.exhaustion_multiplier: float = float(self.settings.get("exhaustion_multiplier", 2.4))
        self.rsi_period: int = int(self.settings.get("rsi_period", 14))
        self.timeframe: str = str(self.settings.get("timeframe", "H1"))
        self.min_history_required: int = max(self.atr_period, self.ma_period, self.rsi_period) + 10

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        if symbol not in self.applicable_symbols:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Symbol {symbol} not supported by this strategy.",
                tags=["unsupported_symbol"]
            )

        candles = await self.get_historical_candles(
            session=session,
            symbol=symbol,
            timeframe=self.timeframe,
            limit=100
        )

        if not candles or len(candles) < self.min_history_required:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale="Insufficient historical candle data for ATR exhaustion analysis.",
                tags=["insufficient_data"]
            )

        highs = np.array([float(c.high) for c in candles], dtype=np.float64)
        lows = np.array([float(c.low) for c in candles], dtype=np.float64)
        closes = np.array([float(c.close) for c in candles], dtype=np.float64)
        opens = np.array([float(c.open) for c in candles], dtype=np.float64)

        # Calculate True Range (TR)
        prev_closes = np.roll(closes, 1)
        prev_closes[0] = closes[0]
        tr1 = highs - lows
        tr2 = np.abs(highs - prev_closes)
        tr3 = np.abs(lows - prev_closes)
        true_range = np.maximum(tr1, np.maximum(tr2, tr3))

        # Smoothed ATR
        atr_series = pd.Series(true_range).rolling(window=self.atr_period).mean().to_numpy()
        current_atr = float(atr_series[-1])

        if math.isnan(current_atr) or current_atr <= 0.0:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale="Invalid ATR calculation.",
                tags=["calculation_error"]
            )

        # Calculate Moving Average of Close
        ma_series = pd.Series(closes).rolling(window=self.ma_period).mean().to_numpy()
        current_ma = float(ma_series[-1])

        if math.isnan(current_ma):
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale="Invalid MA calculation.",
                tags=["calculation_error"]
            )

        # Calculate RSI
        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0.0)
        losses = np.where(deltas < 0, -deltas, 0.0)
        avg_gain = pd.Series(gains).rolling(window=self.rsi_period).mean().to_numpy()
        avg_loss = pd.Series(losses).rolling(window=self.rsi_period).mean().to_numpy()
        
        current_avg_gain = float(avg_gain[-1])
        current_avg_loss = float(avg_loss[-1])
        
        if current_avg_loss == 0:
            rsi = 100.0
        else:
            rs = current_avg_gain / current_avg_loss
            rsi = 100.0 - (100.0 / (1.0 + rs))

        current_close = closes[-1]
        current_open = opens[-1]
        current_high = highs[-1]
        current_low = lows[-1]

        displacement = current_close - current_ma
        displacement_atr_units = displacement / current_atr

        upper_band = current_ma + (self.exhaustion_multiplier * current_atr)
        lower_band = current_ma - (self.exhaustion_multiplier * current_atr)

        direction: Optional[str] = None
        confidence: float = 0.0
        reasons: List[str] = []

        # Bullish Mean Reversion: Price exhausted downward
        if current_close < lower_band and displacement_atr_units <= -self.exhaustion_multiplier:
            # Rejection confirmation (bullish close or lower shadow/wick absorption)
            candle_range = max(current_high - current_low, 1e-5)
            lower_wick = min(current_open, current_close) - current_low
            wick_ratio = lower_wick / candle_range

            if current_close > current_open or wick_ratio >= 0.35 or rsi < 30.0:
                direction = "buy"
                oversold_depth = abs(displacement_atr_units) - self.exhaustion_multiplier
                base_conf = 0.65
                depth_boost = min(0.15, oversold_depth * 0.1)
                rsi_boost = 0.10 if rsi < 30.0 else 0.05
                confidence = round(min(0.92, base_conf + depth_boost + rsi_boost), 3)
                reasons.append(f"Oversold exhaustion: {displacement_atr_units:.2f} ATR below MA{self.ma_period}")
                reasons.append(f"RSI={rsi:.1f}, Wick Ratio={wick_ratio:.2f}")

        # Bearish Mean Reversion: Price exhausted upward
        elif current_close > upper_band and displacement_atr_units >= self.exhaustion_multiplier:
            # Rejection confirmation (bearish close or upper shadow/wick absorption)
            candle_range = max(current_high - current_low, 1e-5)
            upper_wick = current_high - max(current_open, current_close)
            wick_ratio = upper_wick / candle_range

            if current_close < current_open or wick_ratio >= 0.35 or rsi > 70.0:
                direction = "sell"
                overbought_depth = displacement_atr_units - self.exhaustion_multiplier
                base_conf = 0.65
                depth_boost = min(0.15, overbought_depth * 0.1)
                rsi_boost = 0.10 if rsi > 70.0 else 0.05
                confidence = round(min(0.92, base_conf + depth_boost + rsi_boost), 3)
                reasons.append(f"Overbought exhaustion: {displacement_atr_units:.2f} ATR above MA{self.ma_period}")
                reasons.append(f"RSI={rsi:.1f}, Wick Ratio={wick_ratio:.2f}")

        if direction is not None:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=direction,
                valid=True,
                confidence=confidence,
                rationale="; ".join(reasons),
                tags=["mean_reversion", "atr_exhaustion", "xauusd", f"rsi_{round(rsi, 1)}"]
            )

        return EdgeSignal(
            strategy_id=self.strategy_id,
            symbol=symbol,
            direction=None,
            valid=False,
            confidence=0.0,
            rationale=f"Price within normal range (Displacement: {displacement_atr_units:.2f} ATR, RSI: {rsi:.1f}). No exhaustion trigger.",
            tags=["neutral", "no_signal"]
        )