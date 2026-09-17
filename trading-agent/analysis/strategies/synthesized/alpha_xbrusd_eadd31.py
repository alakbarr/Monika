from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xbrusd_eadd31(EdgeStrategy):
    strategy_id: str = "alpha_xbrusd_eadd31"
    applicable_symbols: set = {"XBRUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.timeframe: str = self.settings.get("timeframe", "H1")
        self.lookback: int = self.settings.get("lookback", 100)
        self.ema_period: int = self.settings.get("ema_period", 20)
        self.atr_period: int = self.settings.get("atr_period", 14)
        self.rsi_period: int = self.settings.get("rsi_period", 14)
        self.exhaustion_multiplier: float = float(self.settings.get("exhaustion_multiplier", 2.5))
        self.rsi_overbought: float = float(self.settings.get("rsi_overbought", 70.0))
        self.rsi_oversold: float = float(self.settings.get("rsi_oversold", 30.0))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        if symbol not in self.applicable_symbols:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Symbol {symbol} not supported by strategy {self.strategy_id}",
                tags=["error", "unsupported_symbol"]
            )

        candles = await self.get_historical_candles(
            session=session,
            symbol=symbol,
            timeframe=self.timeframe,
            limit=self.lookback
        )

        min_required = max(self.ema_period, self.atr_period, self.rsi_period) + 10
        if not candles or len(candles) < min_required:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Insufficient candle history ({len(candles) if candles else 0}/{min_required})",
                tags=["insufficient_data", "mean_reversion"]
            )

        highs = np.array([c.high if hasattr(c, "high") else c["high"] for c in candles], dtype=float)
        lows = np.array([c.low if hasattr(c, "low") else c["low"] for c in candles], dtype=float)
        closes = np.array([c.close if hasattr(c, "close") else c["close"] for c in candles], dtype=float)

        # 1. Calculate EMA
        close_series = pd.Series(closes)
        ema_series = close_series.ewm(span=self.ema_period, adjust=False).mean()
        current_ema = ema_series.iloc[-1]

        # 2. Calculate ATR
        tr1 = highs[1:] - lows[1:]
        tr2 = np.abs(highs[1:] - closes[:-1])
        tr3 = np.abs(lows[1:] - closes[:-1])
        true_range = np.maximum(tr1, np.maximum(tr2, tr3))
        atr_series = pd.Series(true_range).rolling(window=self.atr_period).mean()
        current_atr = atr_series.iloc[-1]

        if np.isnan(current_atr) or current_atr <= 0.0:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale="Invalid ATR calculation",
                tags=["error", "atr_computation"]
            )

        # 3. Calculate RSI
        delta = close_series.diff()
        gain = delta.clip(lower=0.0)
        loss = -delta.clip(upper=0.0)
        avg_gain = gain.rolling(window=self.rsi_period).mean()
        avg_loss = loss.rolling(window=self.rsi_period).mean()
        
        rs = avg_gain / (avg_loss + 1e-10)
        rsi_series = 100.0 - (100.0 / (1.0 + rs))
        current_rsi = rsi_series.iloc[-1]

        # 4. Exhaustion Metrics
        current_close = closes[-1]
        distance_from_ema = current_close - current_ema
        atr_distance = distance_from_ema / current_atr

        direction = None
        confidence = 0.0
        rationale_items: List[str] = []
        tags: List[str] = ["mean_reversion", "atr_exhaustion", "xbrusd"]

        # Long Mean Reversion: Price exhausted to the downside
        if atr_distance <= -self.exhaustion_multiplier and current_rsi <= self.rsi_oversold:
            direction = "buy"
            reversion_depth = abs(atr_distance)
            base_conf = min(0.95, 0.60 + (reversion_depth - self.exhaustion_multiplier) * 0.15)
            rsi_factor = min(0.10, (self.rsi_oversold - current_rsi) / 100.0)
            confidence = round(min(0.95, base_conf + rsi_factor), 2)

            rationale_items.append(f"Price extended {abs(atr_distance):.2f}x ATR below EMA{self.ema_period}")
            rationale_items.append(f"RSI oversold at {current_rsi:.2f}")
            tags.extend(["oversold_exhaustion", "buy_reversion"])

        # Short Mean Reversion: Price exhausted to the upside
        elif atr_distance >= self.exhaustion_multiplier and current_rsi >= self.rsi_overbought:
            direction = "sell"
            reversion_depth = atr_distance
            base_conf = min(0.95, 0.60 + (reversion_depth - self.exhaustion_multiplier) * 0.15)
            rsi_factor = min(0.10, (current_rsi - self.rsi_overbought) / 100.0)
            confidence = round(min(0.95, base_conf + rsi_factor), 2)

            rationale_items.append(f"Price extended {atr_distance:.2f}x ATR above EMA{self.ema_period}")
            rationale_items.append(f"RSI overbought at {current_rsi:.2f}")
            tags.extend(["overbought_exhaustion", "sell_reversion"])

        if direction is not None:
            rationale = " | ".join(rationale_items)
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=direction,
                valid=True,
                confidence=confidence,
                rationale=rationale,
                tags=tags
            )

        return EdgeSignal(
            strategy_id=self.strategy_id,
            symbol=symbol,
            direction=None,
            valid=False,
            confidence=0.0,
            rationale=f"Within normal dynamic range. ATR Distance: {atr_distance:.2f}x, RSI: {current_rsi:.2f}",
            tags=tags
        )