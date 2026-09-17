from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_eurusd_920843(EdgeStrategy):
    strategy_id: str = "alpha_eurusd_920843"
    applicable_symbols: set = {"EURUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        cfg = settings or {}
        self.timeframe: str = cfg.get("timeframe", "H1")
        self.limit: int = int(cfg.get("limit", 100))
        self.atr_period: int = int(cfg.get("atr_period", 14))
        self.baseline_period: int = int(cfg.get("baseline_period", 20))
        self.exhaustion_threshold: float = float(cfg.get("exhaustion_threshold", 2.2))
        self.rsi_period: int = int(cfg.get("rsi_period", 14))
        self.rsi_oversold: float = float(cfg.get("rsi_oversold", 30.0))
        self.rsi_overbought: float = float(cfg.get("rsi_overbought", 70.0))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        if symbol not in self.applicable_symbols:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Symbol {symbol} not applicable for this strategy.",
                tags=["ineligible_symbol"]
            )

        candles = await self.get_historical_candles(
            session=session,
            symbol=symbol,
            timeframe=self.timeframe,
            limit=self.limit
        )

        min_required = max(self.baseline_period, self.atr_period, self.rsi_period) + 10
        if not candles or len(candles) < min_required:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Insufficient candle history. Needed {min_required}, got {len(candles) if candles else 0}.",
                tags=["insufficient_data"]
            )

        highs = pd.Series([float(c.high) for c in candles], dtype=float)
        lows = pd.Series([float(c.low) for c in candles], dtype=float)
        closes = pd.Series([float(c.close) for c in candles], dtype=float)

        prev_closes = closes.shift(1)
        tr1 = highs - lows
        tr2 = (highs - prev_closes).abs()
        tr3 = (lows - prev_closes).abs()
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr_series = true_range.rolling(window=self.atr_period).mean()

        baseline = closes.rolling(window=self.baseline_period).mean()

        delta = closes.diff()
        gain = (delta.where(delta > 0, 0.0)).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(window=self.rsi_period).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi_series = 100.0 - (100.0 / (1.0 + rs))

        curr_close = closes.iloc[-1]
        curr_baseline = baseline.iloc[-1]
        curr_atr = atr_series.iloc[-1]
        curr_rsi = rsi_series.iloc[-1]

        if pd.isna(curr_baseline) or pd.isna(curr_atr) or curr_atr <= 0 or pd.isna(curr_rsi):
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale="Technical indicator computation returned NaN or invalid ATR values.",
                tags=["indicator_error"]
            )

        atr_deviation = (curr_close - curr_baseline) / curr_atr

        direction = None
        confidence = 0.0
        rationale = ""
        tags = ["mean_reversion", "atr_exhaustion"]

        # Oversold exhaustion: Price is significantly below baseline and RSI indicates oversold
        if atr_deviation <= -self.exhaustion_threshold and curr_rsi <= self.rsi_oversold:
            direction = "buy"
            excess = abs(atr_deviation) - self.exhaustion_threshold
            confidence = min(0.95, 0.65 + (excess * 0.1) + ((self.rsi_oversold - curr_rsi) * 0.005))
            rationale = (
                f"Long entry on ATR exhaustion: Close ({curr_close:.5f}) is {atr_deviation:.2f} ATRs "
                f"below baseline ({curr_baseline:.5f}) with RSI at {curr_rsi:.1f}."
            )
            tags.append("oversold_exhaustion")

        # Overbought exhaustion: Price is significantly above baseline and RSI indicates overbought
        elif atr_deviation >= self.exhaustion_threshold and curr_rsi >= self.rsi_overbought:
            direction = "sell"
            excess = atr_deviation - self.exhaustion_threshold
            confidence = min(0.95, 0.65 + (excess * 0.1) + ((curr_rsi - self.rsi_overbought) * 0.005))
            rationale = (
                f"Short entry on ATR exhaustion: Close ({curr_close:.5f}) is {atr_deviation:.2f} ATRs "
                f"above baseline ({curr_baseline:.5f}) with RSI at {curr_rsi:.1f}."
            )
            tags.append("overbought_exhaustion")

        if direction is not None:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=direction,
                valid=True,
                confidence=float(round(confidence, 4)),
                rationale=rationale,
                tags=tags
            )

        return EdgeSignal(
            strategy_id=self.strategy_id,
            symbol=symbol,
            direction=None,
            valid=False,
            confidence=0.0,
            rationale=f"No exhaustion threshold breached. Current ATR deviation: {atr_deviation:.2f}, RSI: {curr_rsi:.1f}.",
            tags=["no_signal"]
        )