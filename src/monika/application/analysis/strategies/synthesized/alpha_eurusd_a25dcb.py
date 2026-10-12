from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_eurusd_a25dcb(EdgeStrategy):
    strategy_id: str = "alpha_eurusd_a25dcb"
    applicable_symbols: set = {"EURUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.htf_timeframe: str = self.settings.get("htf_timeframe", "H1")
        self.ltf_timeframe: str = self.settings.get("ltf_timeframe", "M5")
        self.swing_lookback: int = int(self.settings.get("swing_lookback", 24))
        self.sweep_tolerance_pips: float = float(self.settings.get("sweep_tolerance_pips", 1.5))
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
                rationale="Symbol not applicable for EURUSD liquidity sweep strategy.",
                tags=["liquidity_sweep", "ineligible_symbol"]
            )

        htf_candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe=self.htf_timeframe, limit=80)
        ltf_candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe=self.ltf_timeframe, limit=80)

        if not htf_candles or len(htf_candles) < self.swing_lookback + 5 or not ltf_candles or len(ltf_candles) < 30:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale="Insufficient historical candle data for multi-timeframe evaluation.",
                tags=["liquidity_sweep", "insufficient_data"]
            )

        htf_df = pd.DataFrame([
            {
                "open": float(c.open),
                "high": float(c.high),
                "low": float(c.low),
                "close": float(c.close),
                "volume": float(c.volume) if hasattr(c, "volume") and c.volume is not None else 0.0,
                "timestamp": c.timestamp if hasattr(c, "timestamp") else None
            }
            for c in htf_candles
        ])

        ltf_df = pd.DataFrame([
            {
                "open": float(c.open),
                "high": float(c.high),
                "low": float(c.low),
                "close": float(c.close),
                "volume": float(c.volume) if hasattr(c, "volume") and c.volume is not None else 0.0,
                "timestamp": c.timestamp if hasattr(c, "timestamp") else None
            }
            for c in ltf_candles
        ])

        # Step 1: Detect HTF Key Swing Highs & Lows (prior to the most recent completed HTF bars)
        eval_window = htf_df.iloc[-(self.swing_lookback + 5):-3]
        swing_high = eval_window["high"].max()
        swing_low = eval_window["low"].min()

        recent_htf = htf_df.iloc[-3:]
        pip_size = 0.0001
        tolerance = self.sweep_tolerance_pips * pip_size

        bullish_sweep = False
        bearish_sweep = False
        htf_sweep_level = 0.0
        sweep_depth = 0.0

        for _, row in recent_htf.iterrows():
            # Bearish liquidity sweep: Price sweeps swing high, rejects, and closes back below the level
            if row["high"] >= swing_high - tolerance and row["close"] < swing_high:
                bearish_sweep = True
                htf_sweep_level = swing_high
                sweep_depth = max(sweep_depth, row["high"] - swing_high)

            # Bullish liquidity sweep: Price sweeps swing low, rejects, and closes back above the level
            if row["low"] <= swing_low + tolerance and row["close"] > swing_low:
                bullish_sweep = True
                htf_sweep_level = swing_low
                sweep_depth = max(sweep_depth, swing_low - row["low"])

        if not bullish_sweep and not bearish_sweep:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"No HTF liquidity sweep identified near swing high ({swing_high:.5f}) or swing low ({swing_low:.5f}).",
                tags=["liquidity_sweep", "no_htf_sweep"]
            )

        # Step 2: LTF True Range & Displacement Analysis
        ltf_df["tr0"] = ltf_df["high"] - ltf_df["low"]
        ltf_df["tr1"] = (ltf_df["high"] - ltf_df["close"].shift(1)).abs()
        ltf_df["tr2"] = (ltf_df["low"] - ltf_df["close"].shift(1)).abs()
        ltf_df["tr"] = ltf_df[["tr0", "tr1", "tr2"]].max(axis=1)
        ltf_df["atr"] = ltf_df["tr"].rolling(window=14).mean()

        recent_ltf = ltf_df.iloc[-6:].copy()
        current_atr = ltf_df["atr"].iloc[-1]

        if current_atr <= 0 or math.isnan(current_atr):
            current_atr = pip_size * 5.0

        signal_direction = None
        displacement_found = False
        displacement_score = 0.0

        # Look for market structure displacement in the opposite direction of the sweep
        if bearish_sweep:
            for i in range(len(recent_ltf)):
                bar = recent_ltf.iloc[i]
                body = bar["open"] - bar["close"]  # Bearish body
                total_range = bar["high"] - bar["low"]
                
                # Displacement criteria: Large bearish body, high body-to-range ratio, expansion over ATR
                if body > 0 and body >= (self.displacement_multiplier * current_atr) and (body / (total_range + 1e-8)) > 0.60:
                    displacement_found = True
                    signal_direction = "sell"
                    displacement_score = min(1.0, body / (2.0 * current_atr))
                    break

        if bullish_sweep and not displacement_found:
            for i in range(len(recent_ltf)):
                bar = recent_ltf.iloc[i]
                body = bar["close"] - bar["open"]  # Bullish body
                total_range = bar["high"] - bar["low"]

                # Displacement criteria: Large bullish body, high body-to-range ratio, expansion over ATR
                if body > 0 and body >= (self.displacement_multiplier * current_atr) and (body / (total_range + 1e-8)) > 0.60:
                    displacement_found = True
                    signal_direction = "buy"
                    displacement_score = min(1.0, body / (2.0 * current_atr))
                    break

        if not displacement_found or signal_direction is None:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale="HTF liquidity swept but lacks confirmatory LTF impulse displacement.",
                tags=["liquidity_sweep", "no_ltf_displacement"]
            )

        # Step 3: Confidence Calibration
        sweep_quality = min(1.0, max(0.5, sweep_depth / (current_atr + 1e-8)))
        confidence = float(np.clip(0.50 + (0.30 * displacement_score) + (0.20 * sweep_quality), 0.0, 0.95))
        is_valid = confidence >= self.min_confidence

        rationale = (
            f"HTF {self.htf_timeframe} liquidity sweep at {htf_sweep_level:.5f} confirmed with "
            f"LTF {self.ltf_timeframe} {signal_direction.upper()} displacement (ATR Multiplier: {displacement_score:.2f})."
        )

        return EdgeSignal(
            strategy_id=self.strategy_id,
            symbol=symbol,
            direction=signal_direction,
            valid=is_valid,
            confidence=round(confidence, 4),
            rationale=rationale,
            tags=["liquidity_sweep", "displacement", "multi_timeframe", signal_direction]
        )