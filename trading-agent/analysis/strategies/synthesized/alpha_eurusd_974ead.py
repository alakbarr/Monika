from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_eurusd_974ead(EdgeStrategy):
    strategy_id: str = "alpha_eurusd_974ead"
    applicable_symbols: set = {"EURUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        user_settings = settings or {}
        self.timeframe: str = user_settings.get("timeframe", "H1")
        self.limit: int = int(user_settings.get("limit", 100))
        self.ema_period: int = int(user_settings.get("ema_period", 20))
        self.atr_period: int = int(user_settings.get("atr_period", 14))
        self.rsi_period: int = int(user_settings.get("rsi_period", 14))
        self.atr_exhaustion_mult: float = float(user_settings.get("atr_exhaustion_mult", 2.2))
        self.rsi_ob: float = float(user_settings.get("rsi_ob", 68.0))
        self.rsi_os: float = float(user_settings.get("rsi_os", 32.0))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            if symbol not in self.applicable_symbols:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale=f"Symbol {symbol} not applicable for this strategy.",
                    tags=["unsupported_symbol"]
                )

            candles = await self.get_historical_candles(
                session=session,
                symbol=symbol,
                timeframe=self.timeframe,
                limit=self.limit
            )

            if not candles or len(candles) < max(self.ema_period, self.atr_period, self.rsi_period) + 5:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient candle history for ATR exhaustion analysis.",
                    tags=["insufficient_data"]
                )

            df = pd.DataFrame([
                {
                    "open": float(c.open),
                    "high": float(c.high),
                    "low": float(c.low),
                    "close": float(c.close),
                    "volume": float(c.volume) if hasattr(c, "volume") and c.volume is not None else 0.0
                }
                for c in candles
            ])

            # Sanitize inputs
            df = df.replace([np.inf, -np.inf], np.nan).ffill().bfill().fillna(0.0)

            # Calculate True Range & Average True Range (ATR)
            prev_close = df["close"].shift(1)
            tr1 = df["high"] - df["low"]
            tr2 = (df["high"] - prev_close).abs()
            tr3 = (df["low"] - prev_close).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr = tr.rolling(window=self.atr_period, min_periods=1).mean()

            # Baseline EMA
            ema = df["close"].ewm(span=self.ema_period, adjust=False).mean()

            # Deviation in ATR units
            safe_atr = atr.replace(0.0, 1e-6)
            stretch = (df["close"] - ema) / safe_atr

            # RSI Calculation
            delta = df["close"].diff()
            gain = delta.where(delta > 0, 0.0).rolling(window=self.rsi_period, min_periods=1).mean()
            loss = (-delta.where(delta < 0, 0.0)).rolling(window=self.rsi_period, min_periods=1).mean()
            safe_loss = loss.replace(0.0, 1e-6)
            rs = gain / safe_loss
            rsi = 100.0 - (100.0 / (1.0 + rs))

            # Current and previous bar metrics
            curr_close = df["close"].iloc[-1]
            curr_open = df["open"].iloc[-1]
            curr_high = df["high"].iloc[-1]
            curr_low = df["low"].iloc[-1]
            curr_stretch = float(stretch.iloc[-1])
            curr_rsi = float(rsi.iloc[-1])
            curr_atr = float(atr.iloc[-1])
            curr_ema = float(ema.iloc[-1])

            upper_exhaustion_barrier = curr_ema + (self.atr_exhaustion_mult * curr_atr)
            lower_exhaustion_barrier = curr_ema - (self.atr_exhaustion_mult * curr_atr)

            # Rejection wick / candlestick exhaustion dynamics
            body_size = abs(curr_close - curr_open)
            upper_wick = curr_high - max(curr_open, curr_close)
            lower_wick = min(curr_open, curr_close) - curr_low

            direction = None
            confidence = 0.0
            rationale = "Price is within normal ATR oscillation bounds."
            tags = ["neutral", "atr_exhaustion"]

            # Bearish Exhaustion -> Mean Reversion Sell
            if curr_stretch >= self.atr_exhaustion_mult and (curr_rsi >= self.rsi_ob or upper_wick > body_size):
                direction = "sell"
                excess = max(0.0, curr_stretch - self.atr_exhaustion_mult)
                rsi_excess = max(0.0, curr_rsi - self.rsi_ob) / 30.0
                confidence = float(min(0.92, 0.60 + (excess * 0.10) + (rsi_excess * 0.15)))
                rationale = (
                    f"EURUSD upside exhaustion: Price ({curr_close:.5f}) extended {curr_stretch:.2f} ATRs above EMA "
                    f"(Barrier: {upper_exhaustion_barrier:.5f}) with RSI at {curr_rsi:.1f}. Expecting mean reversion to EMA ({curr_ema:.5f})."
                )
                tags = ["mean_reversion", "overbought_exhaustion", "short"]

            # Bullish Exhaustion -> Mean Reversion Buy
            elif curr_stretch <= -self.atr_exhaustion_mult and (curr_rsi <= self.rsi_os or lower_wick > body_size):
                direction = "buy"
                excess = max(0.0, abs(curr_stretch) - self.atr_exhaustion_mult)
                rsi_excess = max(0.0, self.rsi_os - curr_rsi) / 30.0
                confidence = float(min(0.92, 0.60 + (excess * 0.10) + (rsi_excess * 0.15)))
                rationale = (
                    f"EURUSD downside exhaustion: Price ({curr_close:.5f}) extended {abs(curr_stretch):.2f} ATRs below EMA "
                    f"(Barrier: {lower_exhaustion_barrier:.5f}) with RSI at {curr_rsi:.1f}. Expecting mean reversion to EMA ({curr_ema:.5f})."
                )
                tags = ["mean_reversion", "oversold_exhaustion", "long"]

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=direction,
                valid=direction is not None,
                confidence=confidence,
                rationale=rationale,
                tags=tags
            )

        except Exception as e:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Calculation error: {str(e)}",
                tags=["error"]
            )
