from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math
import numpy as np
import pandas as pd
import datetime
import logging
import decimal

logger = logging.getLogger(__name__)


class SynthesizedStrategy_alpha_audusd_eb3084(EdgeStrategy):
    """
    Multi-timeframe liquidity sweep displacement strategy engineered for AUDUSD.
    
    Identifies institutional stop runs (buy-side / sell-side liquidity sweeps)
    beyond local swing extremes, followed by immediate aggressive displacement
    (market structure shift with expansion candle and fair value gap confirmation).
    """

    strategy_id: str = "alpha_audusd_eb3084"
    applicable_symbols: set = {"AUDUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, **kwargs: Any) -> None:
        super().__init__(settings or {}, **kwargs)
        self.swing_lookback: int = 30
        self.sweep_tolerance_pips: float = 0.0003  # 3 pips
        self.displacement_multiplier: float = 1.6  # Body to ATR ratio
        self.atr_period: int = 14

    async def evaluate(
        self,
        session: AsyncSession,
        symbol: str,
        settings: Dict[str, Any]
    ) -> EdgeSignal:
        if symbol.upper() not in self.applicable_symbols:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Symbol {symbol} not supported by {self.strategy_id}",
                tags=["unsupported_symbol"]
            )

        try:
            # Retrieve candle data from base strategy data loader
            candles = await self.get_historical_candles(
                session=session,
                symbol=symbol,
                timeframe=settings.get("timeframe", "15m"),
                limit=settings.get("candle_limit", 150)
            )

            if candles is None or len(candles) < self.swing_lookback + self.atr_period:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient historical candle depth for liquidity sweep analysis",
                    tags=["insufficient_data"]
                )

            df = pd.DataFrame(candles)
            for col in ["open", "high", "low", "close"]:
                df[col] = df[col].astype(float)

            # ATR Calculation
            high_low = df["high"] - df["low"]
            high_close_prev = (df["high"] - df["close"].shift(1)).abs()
            low_close_prev = (df["low"] - df["close"].shift(1)).abs()
            tr = pd.concat([high_low, high_close_prev, low_close_prev], axis=1).max(axis=1)
            df["atr"] = tr.rolling(window=self.atr_period).mean()

            # Dynamic Swing Levels (excluding latest 3 confirmation bars)
            lookback_window = df.iloc[-self.swing_lookback - 3 : -3]
            swing_high = lookback_window["high"].max()
            swing_low = lookback_window["low"].min()

            # Recent structural candles
            trigger_candle = df.iloc[-2]
            current_candle = df.iloc[-1]
            prev_candle = df.iloc[-3]

            current_atr = df["atr"].iloc[-1]
            if math.isnan(current_atr) or current_atr <= 0:
                current_atr = 0.0010  # Fallback 10 pips default for AUDUSD

            # Evaluate Bullish Liquidity Sweep & Displacement
            # Scenario: Sell-side liquidity sweep below swing low, quick rejection & bullish displacement
            swept_sell_side = (
                (prev_candle["low"] < swing_low or trigger_candle["low"] < swing_low)
                and trigger_candle["close"] > swing_low - (self.sweep_tolerance_pips * 0.5)
            )
            bullish_body = trigger_candle["close"] - trigger_candle["open"]
            bullish_displacement = (
                bullish_body > (current_atr * self.displacement_multiplier)
                and trigger_candle["close"] > trigger_candle["open"]
                and current_candle["close"] >= trigger_candle["close"] - (bullish_body * 0.382)
            )
            bullish_fvg = trigger_candle["low"] > df.iloc[-4]["high"] if len(df) >= 4 else False

            # Evaluate Bearish Liquidity Sweep & Displacement
            # Scenario: Buy-side liquidity sweep above swing high, quick rejection & bearish displacement
            swept_buy_side = (
                (prev_candle["high"] > swing_high or trigger_candle["high"] > swing_high)
                and trigger_candle["close"] < swing_high + (self.sweep_tolerance_pips * 0.5)
            )
            bearish_body = trigger_candle["open"] - trigger_candle["close"]
            bearish_displacement = (
                bearish_body > (current_atr * self.displacement_multiplier)
                and trigger_candle["close"] < trigger_candle["open"]
                and current_candle["close"] <= trigger_candle["close"] + (bearish_body * 0.382)
            )
            bearish_fvg = trigger_candle["high"] < df.iloc[-4]["low"] if len(df) >= 4 else False

            # Decision Logic
            if swept_sell_side and bullish_displacement:
                confidence = 0.72
                if bullish_fvg:
                    confidence += 0.13
                sweep_depth = max(0.0, swing_low - min(prev_candle["low"], trigger_candle["low"]))
                if sweep_depth >= self.sweep_tolerance_pips:
                    confidence += 0.05
                confidence = min(0.95, round(confidence, 2))

                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction="buy",
                    valid=True,
                    confidence=confidence,
                    rationale=(
                        f"AUDUSD Sell-side liquidity sweep below {swing_low:.5f} confirmed with "
                        f"bullish displacement body {bullish_body * 10000:.1f} pips vs ATR {current_atr * 10000:.1f} pips."
                    ),
                    tags=["liquidity_sweep", "market_structure_shift", "bullish_displacement", "audusd"]
                )

            elif swept_buy_side and bearish_displacement:
                confidence = 0.72
                if bearish_fvg:
                    confidence += 0.13
                sweep_depth = max(0.0, max(prev_candle["high"], trigger_candle["high"]) - swing_high)
                if sweep_depth >= self.sweep_tolerance_pips:
                    confidence += 0.05
                confidence = min(0.95, round(confidence, 2))

                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction="sell",
                    valid=True,
                    confidence=confidence,
                    rationale=(
                        f"AUDUSD Buy-side liquidity sweep above {swing_high:.5f} confirmed with "
                        f"bearish displacement body {bearish_body * 10000:.1f} pips vs ATR {current_atr * 10000:.1f} pips."
                    ),
                    tags=["liquidity_sweep", "market_structure_shift", "bearish_displacement", "audusd"]
                )

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale="No valid MTF liquidity sweep and displacement pattern detected",
                tags=["no_setup"]
            )

        except Exception as ex:
            logger.error(f"Error evaluating {self.strategy_id} on {symbol}: {str(ex)}", exc_info=True)
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Evaluation failed: {str(ex)}",
                tags=["error"]
            )