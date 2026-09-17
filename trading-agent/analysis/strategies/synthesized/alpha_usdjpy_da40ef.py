from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_usdjpy_da40ef(EdgeStrategy):
    strategy_id: str = "alpha_usdjpy_da40ef"
    applicable_symbols: set = {"USDJPY"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        cfg = settings or {}
        self.htf_lookback: int = int(cfg.get("htf_lookback", 24))
        self.ltf_lookback: int = int(cfg.get("ltf_lookback", 30))
        self.displacement_mult: float = float(cfg.get("displacement_mult", 1.4))
        self.min_confidence: float = float(cfg.get("min_confidence", 0.60))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        if symbol not in self.applicable_symbols:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale="Symbol not applicable for USDJPY liquidity sweep strategy.",
                tags=["inapplicable_symbol"]
            )

        # 1. Fetch multi-timeframe candles: H1 for key liquidity levels, M15 for execution/displacement
        htf_candles = await self.get_historical_candles(
            session=session,
            symbol=symbol,
            timeframe="H1",
            limit=self.htf_lookback + 10
        )
        ltf_candles = await self.get_historical_candles(
            session=session,
            symbol=symbol,
            timeframe="M15",
            limit=self.ltf_lookback + 10
        )

        if not htf_candles or len(htf_candles) < self.htf_lookback or not ltf_candles or len(ltf_candles) < 15:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale="Insufficient historical multi-timeframe candle data.",
                tags=["insufficient_data"]
            )

        # 2. Extract HTF liquidity pools (Swing Highs and Swing Lows)
        htf_highs = [float(c.high) for c in htf_candles[:-1]]
        htf_lows = [float(c.low) for c in htf_candles[:-1]]

        htf_sweep_high = max(htf_highs[-self.htf_lookback:])
        htf_sweep_low = min(htf_lows[-self.htf_lookback:])

        # 3. Calculate LTF ATR for volatility-adjusted displacement measurement
        ltf_closes = [float(c.close) for c in ltf_candles]
        ltf_highs = [float(c.high) for c in ltf_candles]
        ltf_lows = [float(c.low) for c in ltf_candles]
        ltf_opens = [float(c.open) for c in ltf_candles]

        tr_list: List[float] = []
        for i in range(1, len(ltf_candles)):
            hl = ltf_highs[i] - ltf_lows[i]
            hc = abs(ltf_highs[i] - ltf_closes[i - 1])
            lc = abs(ltf_lows[i] - ltf_closes[i - 1])
            tr_list.append(max(hl, hc, lc))

        ltf_atr = float(np.mean(tr_list[-14:])) if len(tr_list) >= 14 else 0.10
        if ltf_atr <= 0:
            ltf_atr = 0.10

        # Current and recent LTF candles
        current_candle = ltf_candles[-1]
        c_open = float(current_candle.open)
        c_high = float(current_candle.high)
        c_low = float(current_candle.low)
        c_close = float(current_candle.close)
        c_body = abs(c_close - c_open)

        recent_lows = ltf_lows[-4:]
        recent_highs = ltf_highs[-4:]

        direction: Optional[str] = None
        confidence: float = 0.0
        rationale: str = ""
        tags: List[str] = ["usdjpy", "liquidity_sweep", "displacement"]

        # 4. Bearish Liquidity Sweep & Displacement:
        # Condition: Price swept above HTF Swing High in recent LTF candles, followed by strong bearish displacement
        swept_high = any(h > htf_sweep_high for h in recent_highs)
        is_bearish_displacement = (
            c_close < c_open and
            c_close < htf_sweep_high and
            c_body >= (self.displacement_mult * ltf_atr) and
            (c_high - max(c_open, c_close)) <= (c_body * 0.8)
        )

        # 5. Bullish Liquidity Sweep & Displacement:
        # Condition: Price swept below HTF Swing Low in recent LTF candles, followed by strong bullish displacement
        swept_low = any(l < htf_sweep_low for l in recent_lows)
        is_bullish_displacement = (
            c_close > c_open and
            c_close > htf_sweep_low and
            c_body >= (self.displacement_mult * ltf_atr) and
            (min(c_open, c_close) - c_low) <= (c_body * 0.8)
        )

        if swept_high and is_bearish_displacement:
            direction = "sell"
            displacement_ratio = c_body / ltf_atr
            base_conf = 0.65 + min(0.25, (displacement_ratio - self.displacement_mult) * 0.15)
            confidence = min(0.92, max(self.min_confidence, base_conf))
            rationale = (
                f"Bearish liquidity sweep of H1 high ({htf_sweep_high:.3f}) detected. "
                f"Strong M15 displacement candle printed with body {c_body:.3f} >= {self.displacement_mult}x ATR ({ltf_atr:.3f})."
            )
            tags.extend(["bearish_displacement", "buyside_liquidity_cleared"])

        elif swept_low and is_bullish_displacement:
            direction = "buy"
            displacement_ratio = c_body / ltf_atr
            base_conf = 0.65 + min(0.25, (displacement_ratio - self.displacement_mult) * 0.15)
            confidence = min(0.92, max(self.min_confidence, base_conf))
            rationale = (
                f"Bullish liquidity sweep of H1 low ({htf_sweep_low:.3f}) detected. "
                f"Strong M15 displacement candle printed with body {c_body:.3f} >= {self.displacement_mult}x ATR ({ltf_atr:.3f})."
            )
            tags.extend(["bullish_displacement", "sellside_liquidity_cleared"])

        else:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale="No liquidity sweep displacement pattern confirmed on USDJPY.",
                tags=["no_setup"]
            )

        return EdgeSignal(
            strategy_id=self.strategy_id,
            symbol=symbol,
            direction=direction,
            valid=True,
            confidence=round(confidence, 4),
            rationale=rationale,
            tags=tags
        )