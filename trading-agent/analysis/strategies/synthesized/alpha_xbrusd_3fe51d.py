from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xbrusd_3fe51d(EdgeStrategy):
    strategy_id: str = "alpha_xbrusd_3fe51d"
    applicable_symbols: set = {"XBRUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.htf_lookback: int = int(self.settings.get("htf_lookback", 48))
        self.ltf_lookback: int = int(self.settings.get("ltf_lookback", 60))
        self.swing_window: int = int(self.settings.get("swing_window", 5))
        self.displacement_mult: float = float(self.settings.get("displacement_mult", 1.4))
        self.min_confidence: float = float(self.settings.get("min_confidence", 0.65))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        if symbol not in self.applicable_symbols:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale="Symbol not applicable for this strategy.",
                tags=["xbrusd", "liquidity_sweep", "incompatible_symbol"]
            )

        # Fetch HTF (H1) and LTF (M15) candles
        htf_candles = await self.get_historical_candles(
            session=session, symbol=symbol, timeframe='H1', limit=self.htf_lookback
        )
        ltf_candles = await self.get_historical_candles(
            session=session, symbol=symbol, timeframe='M15', limit=self.ltf_lookback
        )

        if not htf_candles or len(htf_candles) < self.swing_window * 2 + 5:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale="Insufficient HTF candle data.",
                tags=["xbrusd", "liquidity_sweep", "data_insufficient"]
            )

        if not ltf_candles or len(ltf_candles) < 20:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale="Insufficient LTF candle data.",
                tags=["xbrusd", "liquidity_sweep", "data_insufficient"]
            )

        # Process HTF Swing Highs (Buy-Side Liquidity) and Swing Lows (Sell-Side Liquidity)
        htf_highs = [float(c.high) for c in htf_candles]
        htf_lows = [float(c.low) for c in htf_candles]

        bsl_levels: List[float] = []
        ssl_levels: List[float] = []

        w = self.swing_window
        for i in range(w, len(htf_candles) - w):
            current_h = htf_highs[i]
            current_l = htf_lows[i]
            if all(current_h >= htf_highs[i - j] for j in range(1, w + 1)) and all(current_h >= htf_highs[i + j] for j in range(1, w + 1)):
                bsl_levels.append(current_h)
            if all(current_l <= htf_lows[i - j] for j in range(1, w + 1)) and all(current_l <= htf_lows[i + j] for j in range(1, w + 1)):
                ssl_levels.append(current_l)

        if not bsl_levels and not ssl_levels:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale="No distinct HTF liquidity pools detected.",
                tags=["xbrusd", "liquidity_sweep", "no_levels"]
            )

        # LTF Metrics
        ltf_opens = np.array([float(c.open) for c in ltf_candles])
        ltf_highs = np.array([float(c.high) for c in ltf_candles])
        ltf_lows = np.array([float(c.low) for c in ltf_candles])
        ltf_closes = np.array([float(c.close) for c in ltf_candles])

        # Compute LTF ATR (14 period)
        tr = np.maximum(
            ltf_highs[1:] - ltf_lows[1:],
            np.maximum(
                np.abs(ltf_highs[1:] - ltf_closes[:-1]),
                np.abs(ltf_lows[1:] - ltf_closes[:-1])
            )
        )
        atr = float(np.mean(tr[-14:])) if len(tr) >= 14 else float(np.mean(tr))
        if atr <= 0:
            atr = 0.01

        last_ltf = ltf_candles[-1]
        prev_ltf = ltf_candles[-2]

        last_open = float(last_ltf.open)
        last_high = float(last_ltf.high)
        last_low = float(last_ltf.low)
        last_close = float(last_ltf.close)
        last_body = abs(last_close - last_open)

        # Recent price exploration window (last 6 LTF candles = 1.5 hours)
        recent_window_low = float(np.min(ltf_lows[-6:]))
        recent_window_high = float(np.max(ltf_highs[-6:]))

        direction: Optional[str] = None
        confidence: float = 0.0
        rationale: str = "Neutral market conditions; no displacement sweep found."
        tags: List[str] = ["xbrusd", "liquidity_sweep"]

        # Check Bullish Setup: SSL Sweep followed by Bullish Displacement
        valid_ssl = [lvl for lvl in ssl_levels if lvl > recent_window_low]
        if valid_ssl:
            key_ssl = max(valid_ssl)
            # Conditions:
            # 1. Price swept below key SSL level in recent candles
            # 2. Latest candle closed back above the swept level
            # 3. Latest candle exhibits strong bullish displacement (body > displacement_mult * ATR and close > open)
            is_bullish_displacement = (last_close > last_open) and (last_body >= self.displacement_mult * atr) and (last_close > key_ssl)
            swept = recent_window_low < key_ssl

            if swept and is_bullish_displacement:
                direction = "buy"
                body_ratio = last_body / (last_high - last_low) if (last_high - last_low) > 0 else 0.5
                disp_ratio = min(last_body / (atr * 2.0), 1.0)
                confidence = float(np.clip(0.60 + 0.20 * body_ratio + 0.20 * disp_ratio, 0.0, 0.95))
                rationale = f"Bullish displacement confirmed after SSL sweep at {key_ssl:.2f}. LTF Body/ATR: {last_body/atr:.2f}."
                tags.extend(["ssl_sweep", "bullish_displacement", "long"])

        # Check Bearish Setup: BSL Sweep followed by Bearish Displacement
        if direction is None:
            valid_bsl = [lvl for lvl in bsl_levels if lvl < recent_window_high]
            if valid_bsl:
                key_bsl = min(valid_bsl)
                # Conditions:
                # 1. Price swept above key BSL level in recent candles
                # 2. Latest candle closed back below the swept level
                # 3. Latest candle exhibits strong bearish displacement (body > displacement_mult * ATR and close < open)
                is_bearish_displacement = (last_close < last_open) and (last_body >= self.displacement_mult * atr) and (last_close < key_bsl)
                swept = recent_window_high > key_bsl

                if swept and is_bearish_displacement:
                    direction = "sell"
                    body_ratio = last_body / (last_high - last_low) if (last_high - last_low) > 0 else 0.5
                    disp_ratio = min(last_body / (atr * 2.0), 1.0)
                    confidence = float(np.clip(0.60 + 0.20 * body_ratio + 0.20 * disp_ratio, 0.0, 0.95))
                    rationale = f"Bearish displacement confirmed after BSL sweep at {key_bsl:.2f}. LTF Body/ATR: {last_body/atr:.2f}."
                    tags.extend(["bsl_sweep", "bearish_displacement", "short"])

        is_valid = direction is not None and confidence >= self.min_confidence

        return EdgeSignal(
            strategy_id=self.strategy_id,
            symbol=symbol,
            direction=direction if is_valid else None,
            valid=is_valid,
            confidence=confidence if is_valid else 0.0,
            rationale=rationale,
            tags=tags
        )