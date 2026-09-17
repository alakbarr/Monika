from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xbrusd_beb0e3(EdgeStrategy):
    strategy_id: str = "alpha_xbrusd_beb0e3"
    applicable_symbols: set = {"XBRUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.ma_period: int = int(self.settings.get("ma_period", 20))
        self.atr_period: int = int(self.settings.get("atr_period", 14))
        self.rsi_period: int = int(self.settings.get("rsi_period", 14))
        self.exhaustion_mult: float = float(self.settings.get("exhaustion_mult", 2.25))
        self.rsi_overbought: float = float(self.settings.get("rsi_overbought", 68.0))
        self.rsi_oversold: float = float(self.settings.get("rsi_oversold", 32.0))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe="H1", limit=100)
            if not candles or len(candles) < max(self.ma_period, self.atr_period, self.rsi_period) + 15:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient historical candle data.",
                    tags=["insufficient_data", "xbrusd"]
                )

            data = []
            for c in candles:
                c_close = float(c.close if hasattr(c, "close") else c.get("close", 0.0))
                c_high = float(c.high if hasattr(c, "high") else c.get("high", 0.0))
                c_low = float(c.low if hasattr(c, "low") else c.get("low", 0.0))
                c_open = float(c.open if hasattr(c, "open") else c.get("open", 0.0))
                data.append({"open": c_open, "high": c_high, "low": c_low, "close": c_close})

            df = pd.DataFrame(data)

            # Calculate True Range and ATR
            prev_close = df["close"].shift(1)
            tr1 = df["high"] - df["low"]
            tr2 = (df["high"] - prev_close).abs()
            tr3 = (df["low"] - prev_close).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr = tr.rolling(window=self.atr_period, min_periods=self.atr_period).mean()

            # Baseline Moving Average (EMA)
            ema = df["close"].ewm(span=self.ma_period, adjust=False).mean()

            # Relative Strength Index (RSI)
            delta = df["close"].diff()
            gain = delta.clip(lower=0.0)
            loss = (-delta).clip(lower=0.0)
            avg_gain = gain.ewm(alpha=1.0 / self.rsi_period, min_periods=self.rsi_period, adjust=False).mean()
            avg_loss = loss.ewm(alpha=1.0 / self.rsi_period, min_periods=self.rsi_period, adjust=False).mean()
            
            rs = avg_gain / avg_loss.replace(0.0, np.nan)
            rsi = 100.0 - (100.0 / (1.0 + rs))
            rsi = rsi.fillna(50.0)

            # ATR Exhaustion Deviation
            safe_atr = atr.replace(0.0, np.nan).ffill().bfill().fillna(0.01)
            atr_deviation = (df["close"] - ema) / safe_atr

            latest_close = df["close"].iloc[-1]
            latest_ema = ema.iloc[-1]
            latest_dev = atr_deviation.iloc[-1]
            latest_rsi = rsi.iloc[-1]
            latest_atr = safe_atr.iloc[-1]

            if math.isnan(latest_dev) or math.isnan(latest_rsi):
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Indicator calculation resulted in NaN values.",
                    tags=["nan_error", "xbrusd"]
                )

            # Mean Reversion Long Condition: Price heavily stretched below EMA + RSI oversold
            if latest_dev <= -self.exhaustion_mult and latest_rsi <= self.rsi_oversold:
                stretch_severity = min(abs(latest_dev) / self.exhaustion_mult, 2.0)
                rsi_severity = (self.rsi_oversold - latest_rsi) / max(self.rsi_oversold, 1.0)
                confidence = float(np.clip(0.60 + 0.20 * (stretch_severity - 1.0) + 0.20 * rsi_severity, 0.50, 0.95))
                rationale = (
                    f"XBRUSD ATR exhaustion buy setup: Price ({latest_close:.2f}) is {abs(latest_dev):.2f} ATRs "
                    f"below EMA{self.ma_period} ({latest_ema:.2f}) with RSI at {latest_rsi:.1f} (ATR: {latest_atr:.2f})."
                )
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction="buy",
                    valid=True,
                    confidence=round(confidence, 4),
                    rationale=rationale,
                    tags=["mean_reversion", "atr_exhaustion", "oversold", "xbrusd"]
                )

            # Mean Reversion Short Condition: Price heavily stretched above EMA + RSI overbought
            elif latest_dev >= self.exhaustion_mult and latest_rsi >= self.rsi_overbought:
                stretch_severity = min(latest_dev / self.exhaustion_mult, 2.0)
                rsi_severity = (latest_rsi - self.rsi_overbought) / max(100.0 - self.rsi_overbought, 1.0)
                confidence = float(np.clip(0.60 + 0.20 * (stretch_severity - 1.0) + 0.20 * rsi_severity, 0.50, 0.95))
                rationale = (
                    f"XBRUSD ATR exhaustion sell setup: Price ({latest_close:.2f}) is {latest_dev:.2f} ATRs "
                    f"above EMA{self.ma_period} ({latest_ema:.2f}) with RSI at {latest_rsi:.1f} (ATR: {latest_atr:.2f})."
                )
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction="sell",
                    valid=True,
                    confidence=round(confidence, 4),
                    rationale=rationale,
                    tags=["mean_reversion", "atr_exhaustion", "overbought", "xbrusd"]
                )

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Neutral: ATR dev={latest_dev:.2f} within threshold +/-{self.exhaustion_mult}, RSI={latest_rsi:.1f}.",
                tags=["neutral", "xbrusd"]
            )

        except Exception as e:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Calculation error: {str(e)}",
                tags=["error", "exception"]
            )