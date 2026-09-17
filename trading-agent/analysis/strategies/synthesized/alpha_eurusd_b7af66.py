from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_eurusd_b7af66(EdgeStrategy):
    strategy_id: str = "alpha_eurusd_b7af66"
    applicable_symbols: set = {"EURUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.lookback_period: int = int(self.settings.get("lookback_period", 24))
        self.vol_lookback: int = int(self.settings.get("vol_lookback", 20))
        self.atr_period: int = int(self.settings.get("atr_period", 14))
        self.vol_expansion_threshold: float = float(self.settings.get("vol_expansion_threshold", 1.25))
        self.min_confidence: float = float(self.settings.get("min_confidence", 0.65))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        if symbol not in self.applicable_symbols:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Symbol {symbol} not supported by strategy.",
                tags=["unsupported_symbol"]
            )

        candles = await self.get_historical_candles(
            session=session,
            symbol=symbol,
            timeframe='H1',
            limit=max(self.lookback_period, self.vol_lookback, self.atr_period) + 30
        )

        if not candles or len(candles) < self.lookback_period + self.atr_period:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale="Insufficient historical candle data.",
                tags=["insufficient_data"]
            )

        closes = np.array([float(c.close if hasattr(c, 'close') else c['close']) for c in candles], dtype=np.float64)
        highs = np.array([float(c.high if hasattr(c, 'high') else c['high']) for c in candles], dtype=np.float64)
        lows = np.array([float(c.low if hasattr(c, 'low') else c['low']) for c in candles], dtype=np.float64)
        volumes = np.array([float(c.volume if hasattr(c, 'volume') else c['volume']) for c in candles], dtype=np.float64)

        # True Range calculation
        tr_list = []
        for i in range(1, len(closes)):
            hl = highs[i] - lows[i]
            hc = abs(highs[i] - closes[i - 1])
            lc = abs(lows[i] - closes[i - 1])
            tr_list.append(max(hl, hc, lc))
        
        tr_series = np.array(tr_list, dtype=np.float64)
        if len(tr_series) < self.atr_period:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale="Insufficient range data for ATR calculation.",
                tags=["insufficient_atr_data"]
            )

        atr = float(np.mean(tr_series[-self.atr_period:]))
        if atr <= 0.0:
            atr = 0.0001

        # Current and historical slices
        current_close = closes[-1]
        current_volume = volumes[-1]
        
        # Volume moving average & expansion ratio
        past_volumes = volumes[-(self.vol_lookback + 1):-1]
        avg_volume = float(np.mean(past_volumes)) if len(past_volumes) > 0 else 1.0
        vol_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0

        # Donchian channel over previous N periods (excluding current bar)
        donchian_highs = highs[-(self.lookback_period + 1):-1]
        donchian_lows = lows[-(self.lookback_period + 1):-1]
        
        upper_channel = float(np.max(donchian_highs))
        lower_channel = float(np.min(donchian_lows))
        channel_mid = (upper_channel + lower_channel) / 2.0
        channel_width = upper_channel - lower_channel

        # Dynamic volume-weighted expansion multiplier
        dynamic_expansion_buffer = (vol_ratio - 1.0) * (atr * 0.2)
        adjusted_upper = upper_channel + max(0.0, dynamic_expansion_buffer)
        adjusted_lower = lower_channel - max(0.0, dynamic_expansion_buffer)

        direction: Optional[str] = None
        confidence: float = 0.0
        rationale: str = "No volume-weighted breakout detected."

        # Breakout criteria with volume expansion confirmation
        if current_close > upper_channel and vol_ratio >= self.vol_expansion_threshold:
            direction = 'buy'
            penetration_ratio = (current_close - upper_channel) / atr
            volume_boost = min(0.3, (vol_ratio - self.vol_expansion_threshold) * 0.15)
            confidence = min(0.95, 0.65 + volume_boost + min(0.15, penetration_ratio * 0.1))
            rationale = (
                f"Bullish Donchian expansion breakout. Close ({current_close:.5f}) > Upper ({upper_channel:.5f}), "
                f"Volume surge {vol_ratio:.2f}x avg, Penetration {penetration_ratio:.2f} ATR."
            )
        elif current_close < lower_channel and vol_ratio >= self.vol_expansion_threshold:
            direction = 'sell'
            penetration_ratio = (lower_channel - current_close) / atr
            volume_boost = min(0.3, (vol_ratio - self.vol_expansion_threshold) * 0.15)
            confidence = min(0.95, 0.65 + volume_boost + min(0.15, penetration_ratio * 0.1))
            rationale = (
                f"Bearish Donchian expansion breakdown. Close ({current_close:.5f}) < Lower ({lower_channel:.5f}), "
                f"Volume surge {vol_ratio:.2f}x avg, Penetration {penetration_ratio:.2f} ATR."
            )

        valid = direction is not None and confidence >= self.min_confidence

        tags = [
            "donchian_breakout",
            "volume_expansion",
            f"vol_ratio_{vol_ratio:.2f}",
            f"atr_{atr:.5f}"
        ]
        if valid:
            tags.append(f"signal_{direction}")

        return EdgeSignal(
            strategy_id=self.strategy_id,
            symbol=symbol,
            direction=direction,
            valid=valid,
            confidence=round(confidence, 4),
            rationale=rationale,
            tags=tags
        )