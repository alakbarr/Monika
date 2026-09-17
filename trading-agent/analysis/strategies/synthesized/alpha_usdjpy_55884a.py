from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_usdjpy_55884a(EdgeStrategy):
    strategy_id: str = "alpha_usdjpy_55884a"
    applicable_symbols: set = {"USDJPY"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.donchian_period: int = int(self.settings.get("donchian_period", 20))
        self.volume_ma_period: int = int(self.settings.get("volume_ma_period", 20))
        self.atr_period: int = int(self.settings.get("atr_period", 14))
        self.min_volume_ratio: float = float(self.settings.get("min_volume_ratio", 1.20))
        self.expansion_factor: float = float(self.settings.get("expansion_factor", 0.35))
        self.clv_threshold: float = float(self.settings.get("clv_threshold", 0.25))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        if symbol not in self.applicable_symbols:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Symbol {symbol} not supported by {self.strategy_id}",
                tags=["symbol_mismatch"]
            )

        required_bars = max(self.donchian_period, self.volume_ma_period, self.atr_period) + 30
        candles = await self.get_historical_candles(
            session=session,
            symbol=symbol,
            timeframe="H1",
            limit=required_bars
        )

        if not candles or len(candles) < required_bars:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Insufficient history: received {len(candles) if candles else 0}, required {required_bars}",
                tags=["insufficient_data"]
            )

        closes = np.array([float(c.close) for c in candles], dtype=np.float64)
        highs = np.array([float(c.high) for c in candles], dtype=np.float64)
        lows = np.array([float(c.low) for c in candles], dtype=np.float64)
        volumes = np.array([float(c.volume) if c.volume is not None else 1.0 for c in candles], dtype=np.float64)

        # True Range Calculation
        tr1 = highs[1:] - lows[1:]
        tr2 = np.abs(highs[1:] - closes[:-1])
        tr3 = np.abs(lows[1:] - closes[:-1])
        true_ranges = np.maximum(tr1, np.maximum(tr2, tr3))

        atr_series = pd.Series(true_ranges).rolling(window=self.atr_period).mean().to_numpy()
        current_atr = atr_series[-1]
        baseline_atr = np.nanmean(atr_series[-self.atr_period:]) if len(atr_series) >= self.atr_period else current_atr

        # Volume Profile & Relative Volume (RVOL)
        volume_ma = pd.Series(volumes).rolling(window=self.volume_ma_period).mean().to_numpy()
        current_volume = volumes[-1]
        avg_volume = volume_ma[-1]
        rvol = current_volume / avg_volume if avg_volume > 0 else 1.0

        # Donchian Channels (Prior to current bar to detect breakout)
        prior_highs = highs[-self.donchian_period - 1:-1]
        prior_lows = lows[-self.donchian_period - 1:-1]
        raw_upper_donchian = np.max(prior_highs)
        raw_lower_donchian = np.min(prior_lows)

        # Volume-Weighted Dynamic Expansion Multiplier
        # Higher volume expands the breakout band requirement to filter false penetrations
        dynamic_expansion = current_atr * self.expansion_factor * max(0.0, rvol - 1.0)
        dynamic_upper = raw_upper_donchian + dynamic_expansion
        dynamic_lower = raw_lower_donchian - dynamic_expansion

        # Close Location Value (CLV) to measure bar closing pressure: ((C - L) - (H - C)) / (H - L)
        bar_range = highs[-1] - lows[-1]
        clv = ((closes[-1] - lows[-1]) - (highs[-1] - closes[-1])) / bar_range if bar_range > 0 else 0.0

        current_close = closes[-1]
        direction: Optional[str] = None
        confidence: float = 0.0
        rationale_items: List[str] = []
        tags: List[str] = ["vw_donchian", "breakout"]

        # Signal Logic
        bullish_breakout = (current_close > raw_upper_donchian) and (rvol >= self.min_volume_ratio) and (clv >= self.clv_threshold)
        bearish_breakout = (current_close < raw_lower_donchian) and (rvol >= self.min_volume_ratio) and (clv <= -self.clv_threshold)

        if bullish_breakout:
            direction = "buy"
            # Base confidence scaled by volume surge and CLV strength
            vol_boost = min(0.20, (rvol - self.min_volume_ratio) * 0.15)
            clv_boost = max(0.0, (clv - self.clv_threshold) * 0.20)
            atr_expansion_boost = 0.05 if current_atr > baseline_atr else 0.0
            confidence = min(0.92, 0.65 + vol_boost + clv_boost + atr_expansion_boost)

            rationale_items.append(f"Bullish Donchian expansion breakout above {raw_upper_donchian:.3f}")
            rationale_items.append(f"Close: {current_close:.3f}")
            rationale_items.append(f"RVOL: {rvol:.2f} (Threshold: {self.min_volume_ratio})")
            rationale_items.append(f"CLV: {clv:.2f}")
            tags.extend(["expansion_long", "volume_surge"])

        elif bearish_breakout:
            direction = "sell"
            vol_boost = min(0.20, (rvol - self.min_volume_ratio) * 0.15)
            clv_boost = max(0.0, (-clv - self.clv_threshold) * 0.20)
            atr_expansion_boost = 0.05 if current_atr > baseline_atr else 0.0
            confidence = min(0.92, 0.65 + vol_boost + clv_boost + atr_expansion_boost)

            rationale_items.append(f"Bearish Donchian expansion breakdown below {raw_lower_donchian:.3f}")
            rationale_items.append(f"Close: {current_close:.3f}")
            rationale_items.append(f"RVOL: {rvol:.2f} (Threshold: {self.min_volume_ratio})")
            rationale_items.append(f"CLV: {clv:.2f}")
            tags.extend(["expansion_short", "volume_surge"])

        else:
            rationale_items.append(
                f"No breakout detected. Close: {current_close:.3f}, "
                f"Upper: {raw_upper_donchian:.3f}, Lower: {raw_lower_donchian:.3f}, "
                f"RVOL: {rvol:.2f}, CLV: {clv:.2f}"
            )
            tags.append("neutral")

        return EdgeSignal(
            strategy_id=self.strategy_id,
            symbol=symbol,
            direction=direction,
            valid=direction is not None,
            confidence=round(confidence, 4),
            rationale="; ".join(rationale_items),
            tags=tags
        )