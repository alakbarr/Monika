from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xbrusd_87e8fa(EdgeStrategy):
    strategy_id: str = "alpha_xbrusd_87e8fa"
    applicable_symbols: set = {"XBRUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.htf_timeframe: str = self.settings.get("htf_timeframe", "H1")
        self.ltf_timeframe: str = self.settings.get("ltf_timeframe", "M15")
        self.htf_swing_window: int = int(self.settings.get("htf_swing_window", 5))
        self.ltf_swing_window: int = int(self.settings.get("ltf_swing_window", 3))
        self.sweep_lookback: int = int(self.settings.get("sweep_lookback", 12))
        self.displacement_multiplier: float = float(self.settings.get("displacement_multiplier", 1.4))
        self.min_confidence: float = float(self.settings.get("min_confidence", 0.65))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        if symbol not in self.applicable_symbols:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Symbol {symbol} not supported by this strategy.",
                tags=["ineligible_symbol"]
            )

        htf_candles = await self.get_historical_candles(
            session=session,
            symbol=symbol,
            timeframe=self.htf_timeframe,
            limit=120
        )
        ltf_candles = await self.get_historical_candles(
            session=session,
            symbol=symbol,
            timeframe=self.ltf_timeframe,
            limit=150
        )

        if not htf_candles or len(htf_candles) < 40 or not ltf_candles or len(ltf_candles) < 40:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale="Insufficient candle history on HTF or LTF.",
                tags=["insufficient_data"]
            )

        htf_df = pd.DataFrame([{
            'open': float(c.open if hasattr(c, 'open') else c['open']),
            'high': float(c.high if hasattr(c, 'high') else c['high']),
            'low': float(c.low if hasattr(c, 'low') else c['low']),
            'close': float(c.close if hasattr(c, 'close') else c['close']),
            'volume': float(c.volume if hasattr(c, 'volume') else c.get('volume', 1.0))
        } for c in htf_candles])

        ltf_df = pd.DataFrame([{
            'open': float(c.open if hasattr(c, 'open') else c['open']),
            'high': float(c.high if hasattr(c, 'high') else c['high']),
            'low': float(c.low if hasattr(c, 'low') else c['low']),
            'close': float(c.close if hasattr(c, 'close') else c['close']),
            'volume': float(c.volume if hasattr(c, 'volume') else c.get('volume', 1.0))
        } for c in ltf_candles])

        htf_highs = htf_df['high'].values
        htf_lows = htf_df['low'].values
        
        sw_h = self.htf_swing_window
        swing_high_levels = []
        swing_low_levels = []
        
        for i in range(sw_h, len(htf_highs) - sw_h):
            if np.all(htf_highs[i] >= htf_highs[i - sw_h:i]) and np.all(htf_highs[i] >= htf_highs[i + 1:i + sw_h + 1]):
                swing_high_levels.append(htf_highs[i])
            if np.all(htf_lows[i] <= htf_lows[i - sw_h:i]) and np.all(htf_lows[i] <= htf_lows[i + 1:i + sw_h + 1]):
                swing_low_levels.append(htf_lows[i])

        if not swing_high_levels or not swing_low_levels:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale="No clear HTF swing levels detected.",
                tags=["no_htf_levels"]
            )

        recent_htf_high = swing_high_levels[-1]
        recent_htf_low = swing_low_levels[-1]

        ltf_highs = ltf_df['high'].values
        ltf_lows = ltf_df['low'].values
        ltf_opens = ltf_df['open'].values
        ltf_closes = ltf_df['close'].values

        ltf_ranges = np.maximum(ltf_highs[1:] - ltf_lows[1:], np.abs(ltf_highs[1:] - ltf_closes[:-1]))
        ltf_atr = np.mean(ltf_ranges[-20:]) if len(ltf_ranges) >= 20 else np.mean(ltf_ranges)
        avg_body = np.mean(np.abs(ltf_closes[-20:] - ltf_opens[-20:]))

        lookback_slice = slice(-self.sweep_lookback, None)
        recent_ltf_high_max = np.max(ltf_highs[lookback_slice])
        recent_ltf_low_min = np.min(ltf_lows[lookback_slice])

        swept_high = recent_ltf_high_max > recent_htf_high and ltf_closes[-1] < recent_htf_high
        swept_low = recent_ltf_low_min < recent_htf_low and ltf_closes[-1] > recent_htf_low

        direction = None
        confidence = 0.0
        rationale = ""
        tags = ["xbrusd", "liquidity_sweep"]

        curr_open = ltf_opens[-1]
        curr_close = ltf_closes[-1]
        curr_high = ltf_highs[-1]
        curr_low = ltf_lows[-1]
        curr_body = abs(curr_close - curr_open)

        # Bullish displacement: HTF liquidity swept below, followed by an aggressive LTF bullish displacement
        if swept_low:
            is_bullish_displacement = (curr_close > curr_open) and (curr_body >= avg_body * self.displacement_multiplier)
            broke_local_structure = curr_close > np.max(ltf_highs[-self.ltf_swing_window - 1:-1])
            if is_bullish_displacement or broke_local_structure:
                direction = "buy"
                sweep_magnitude = (recent_htf_low - recent_ltf_low_min) / (ltf_atr + 1e-6)
                body_ratio = curr_body / (avg_body + 1e-6)
                confidence = min(0.95, 0.60 + 0.15 * min(1.0, sweep_magnitude) + 0.20 * min(1.0, body_ratio / 2.0))
                rationale = (f"XBRUSD swept HTF swing low ({recent_htf_low:.2f}) by "
                             f"{recent_htf_low - recent_ltf_low_min:.2f} pts, confirmed by LTF bullish displacement.")
                tags.extend(["bullish_sweep", "displacement_reversal"])

        # Bearish displacement: HTF liquidity swept above, followed by an aggressive LTF bearish displacement
        elif swept_high:
            is_bearish_displacement = (curr_close < curr_open) and (curr_body >= avg_body * self.displacement_multiplier)
            broke_local_structure = curr_close < np.min(ltf_lows[-self.ltf_swing_window - 1:-1])
            if is_bearish_displacement or broke_local_structure:
                direction = "sell"
                sweep_magnitude = (recent_ltf_high_max - recent_htf_high) / (ltf_atr + 1e-6)
                body_ratio = curr_body / (avg_body + 1e-6)
                confidence = min(0.95, 0.60 + 0.15 * min(1.0, sweep_magnitude) + 0.20 * min(1.0, body_ratio / 2.0))
                rationale = (f"XBRUSD swept HTF swing high ({recent_htf_high:.2f}) by "
                             f"{recent_ltf_high_max - recent_htf_high:.2f} pts, confirmed by LTF bearish displacement.")
                tags.extend(["bearish_sweep", "displacement_reversal"])

        valid = direction is not None and confidence >= self.min_confidence

        if not valid and not direction:
            rationale = "No validated multi-timeframe liquidity sweep displacement pattern detected."
            tags.append("neutral_conditions")

        return EdgeSignal(
            strategy_id=self.strategy_id,
            symbol=symbol,
            direction=direction,
            valid=valid,
            confidence=round(confidence, 4),
            rationale=rationale,
            tags=tags
        )