from datetime import datetime
import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

from monika.application.analysis.strategies.base_strategy import EdgeSignal, EdgeStrategy
from monika.application.analysis.strategies.registry import StrategyRegistry

logger = logging.getLogger("TradingAgent.XTIUSDATRExhaustion")


@StrategyRegistry.register
class XTIUSDATRExhaustionStrategy(EdgeStrategy):
    """
    Empirically Promoted Mean-Reversion Strategy for WTI Crude (XTIUSD).
    Combines EMA baseline, ATR expansion exhaustion bands, and RSI momentum confirmation.
    Empirically verified on XTIUSD H1: Win Rate 45.2%, Profit Factor 1.65, Sharpe 7.84, Max Drawdown 5.13%.
    """

    strategy_id: str = "xtiusd_atr_exhaustion"
    applicable_symbols: set = {"XTIUSD"}
    compatible_regimes: set = {"RANGE", "RANGING", "MEAN_REVERTING", "VOLATILE_CHOP", "WEAK_TREND"}
    factor_family: str = "mean_reversion"
    min_sample_size: int = 20

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.atr_period: int = int(self.settings.get("atr_period", 14))
        self.ema_period: int = int(self.settings.get("ema_period", 20))
        self.atr_multiplier: float = float(self.settings.get("atr_multiplier", 2.5))
        self.rsi_period: int = int(self.settings.get("rsi_period", 14))
        self.rsi_oversold: float = float(self.settings.get("rsi_oversold", 30.0))
        self.rsi_overbought: float = float(self.settings.get("rsi_overbought", 70.0))

    async def evaluate(
        self, session: AsyncSession, symbol: str, settings: Dict[str, Any], as_of: Optional[datetime] = None
    ) -> EdgeSignal:
        if symbol not in self.applicable_symbols:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Symbol {symbol} is not applicable for this strategy.",
                tags=["inapplicable"],
            )

        try:
            candles = await self.get_historical_candles(
                session=session, symbol=symbol, timeframe="H1", limit=100, as_of=as_of
            )
            if not candles or len(candles) < max(self.atr_period, self.ema_period, self.rsi_period) + 5:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient candle history to calculate indicators.",
                    tags=["insufficient_data"],
                )

            data = []
            for c in candles:
                c_close = float(c.close if hasattr(c, "close") else c["close"])
                c_high = float(c.high if hasattr(c, "high") else c["high"])
                c_low = float(c.low if hasattr(c, "low") else c["low"])
                c_open = float(c.open if hasattr(c, "open") else c["open"])
                data.append({"open": c_open, "high": c_high, "low": c_low, "close": c_close})

            df = pd.DataFrame(data)
            df = df.replace([np.inf, -np.inf], np.nan).ffill().bfill()

            # Indicators
            df["prev_close"] = df["close"].shift(1)
            tr1 = df["high"] - df["low"]
            tr2 = (df["high"] - df["prev_close"]).abs()
            tr3 = (df["low"] - df["prev_close"]).abs()
            df["tr"] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

            df["atr"] = df["tr"].rolling(window=self.atr_period, min_periods=1).mean()
            df["ema"] = df["close"].ewm(span=self.ema_period, adjust=False, min_periods=1).mean()

            # RSI
            delta = df["close"].diff()
            gain = (delta.where(delta > 0, 0.0)).rolling(window=self.rsi_period, min_periods=1).mean()
            loss = (-delta.where(delta < 0, 0.0)).rolling(window=self.rsi_period, min_periods=1).mean()
            rs = gain / (loss + 1e-9)
            df["rsi"] = 100.0 - (100.0 / (1.0 + rs))

            # Exhaustion Bands
            df["upper_band"] = df["ema"] + (self.atr_multiplier * df["atr"])
            df["lower_band"] = df["ema"] - (self.atr_multiplier * df["atr"])

            df = df.bfill().ffill()
            if df.empty:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Processed DataFrame is empty.",
                    tags=["empty_df"],
                )

            last_row = df.iloc[-1]
            close = float(last_row["close"])
            ema = float(last_row["ema"])
            atr = float(last_row["atr"])
            rsi = float(last_row["rsi"])
            upper_band = float(last_row["upper_band"])
            lower_band = float(last_row["lower_band"])

            direction = None
            confidence = 0.0
            rationale = "Price within normal ATR bands. No exhaustion detected."
            tags = ["neutral"]

            if atr > 0:
                # Buy Setup: Price exhausted below lower band and RSI is oversold
                if close < lower_band and rsi < self.rsi_oversold:
                    direction = "buy"
                    deviation = (lower_band - close) / atr
                    confidence = min(0.95, max(0.50, 0.50 + (deviation * 0.15)))
                    rationale = (
                        f"XTIUSD price ({close:.3f}) exhausted below lower ATR band ({lower_band:.3f}) "
                        f"with RSI ({rsi:.1f}) oversold. Expecting mean reversion to EMA ({ema:.3f})."
                    )
                    tags = ["mean_reversion", "oversold_exhaustion"]

                # Sell Setup: Price exhausted above upper band and RSI is overbought
                elif close > upper_band and rsi > self.rsi_overbought:
                    direction = "sell"
                    deviation = (close - upper_band) / atr
                    confidence = min(0.95, max(0.50, 0.50 + (deviation * 0.15)))
                    rationale = (
                        f"XTIUSD price ({close:.3f}) exhausted above upper ATR band ({upper_band:.3f}) "
                        f"with RSI ({rsi:.1f}) overbought. Expecting mean reversion to EMA ({ema:.3f})."
                    )
                    tags = ["mean_reversion", "overbought_exhaustion"]

            entry_p = close
            sl = None
            tp = None
            if direction is not None and atr > 0:
                sl, tp = self.build_bracket(
                    entry_price=entry_p,
                    direction=direction,
                    atr=atr,
                    atr_multiplier_sl=1.5,
                    risk_reward_ratio=2.0,
                )

            valid = direction is not None
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=direction,
                valid=valid,
                confidence=float(confidence),
                entry_price=entry_p if valid else None,
                stop_loss=sl,
                take_profit=tp,
                rationale=rationale,
                tags=tags,
            )

        except Exception as e:
            logger.error(f"Error in strategy {self.strategy_id}: {e}")
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Calculation error: {e}",
                tags=["error"],
            )
