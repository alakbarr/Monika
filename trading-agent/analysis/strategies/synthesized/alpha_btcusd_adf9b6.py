from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_btcusd_adf9b6(EdgeStrategy):
    strategy_id: str = "alpha_btcusd_adf9b6"
    applicable_symbols: set = {"BTCUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.timeframe: str = self.settings.get("timeframe", "H1")
        self.lookback: int = int(self.settings.get("lookback", 120))
        self.ema_period: int = int(self.settings.get("ema_period", 20))
        self.atr_period: int = int(self.settings.get("atr_period", 14))
        self.rsi_period: int = int(self.settings.get("rsi_period", 14))
        self.exhaustion_threshold: float = float(self.settings.get("exhaustion_threshold", 2.25))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            candles = await self.get_historical_candles(
                session=session,
                symbol=symbol,
                timeframe=self.timeframe,
                limit=self.lookback
            )

            min_required = max(self.ema_period, self.atr_period, self.rsi_period) + 15
            if not candles or len(candles) < min_required:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale=f"Insufficient candle history: {len(candles) if candles else 0}/{min_required} required.",
                    tags=["insufficient_data", "atr_exhaustion"]
                )

            opens: List[float] = []
            highs: List[float] = []
            lows: List[float] = []
            closes: List[float] = []

            for c in candles:
                try:
                    opens.append(float(c.open))
                    highs.append(float(c.high))
                    lows.append(float(c.low))
                    closes.append(float(c.close))
                except AttributeError:
                    opens.append(float(c["open"]))
                    highs.append(float(c["high"]))
                    lows.append(float(c["low"]))
                    closes.append(float(c["close"]))

            df = pd.DataFrame({
                "open": opens,
                "high": highs,
                "low": lows,
                "close": closes
            })

            # Trend Baseline: Exponential Moving Average
            df["ema"] = df["close"].ewm(span=self.ema_period, adjust=False).mean()

            # Volatility Metric: Average True Range (ATR)
            tr1 = df["high"] - df["low"]
            tr2 = (df["high"] - df["close"].shift(1)).abs()
            tr3 = (df["low"] - df["close"].shift(1)).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            df["atr"] = tr.rolling(window=self.atr_period, min_periods=self.atr_period).mean().bfill()

            # Mean-Reversion Exhaustion Gauge (ATR-normalized deviation)
            safe_atr = df["atr"].replace(0.0, np.nan).ffill().fillna(1.0)
            df["close_dev"] = (df["close"] - df["ema"]) / safe_atr
            df["low_dev"] = (df["low"] - df["ema"]) / safe_atr
            df["high_dev"] = (df["high"] - df["ema"]) / safe_atr

            # Secondary Confirmation: RSI Momentum Reversal
            delta = df["close"].diff()
            gain = delta.clip(lower=0.0)
            loss = -delta.clip(upper=0.0)
            avg_gain = gain.rolling(window=self.rsi_period, min_periods=self.rsi_period).mean()
            avg_loss = loss.rolling(window=self.rsi_period, min_periods=self.rsi_period).mean()
            rs = avg_gain / avg_loss.replace(0.0, np.nan)
            df["rsi"] = (100.0 - (100.0 / (1.0 + rs))).fillna(50.0)

            # Signal evaluation on latest bars
            curr_c = df["close"].iloc[-1]
            curr_o = df["open"].iloc[-1]
            prev_c = df["close"].iloc[-2]
            curr_rsi = df["rsi"].iloc[-1]
            prev_rsi = df["rsi"].iloc[-2]

            curr_low_dev = df["low_dev"].iloc[-1]
            prev_low_dev = df["low_dev"].iloc[-2]
            curr_high_dev = df["high_dev"].iloc[-1]
            prev_high_dev = df["high_dev"].iloc[-2]
            curr_close_dev = df["close_dev"].iloc[-1]

            bullish_exhaustion = (prev_low_dev <= -self.exhaustion_threshold or curr_low_dev <= -self.exhaustion_threshold)
            bullish_reversal = curr_c > curr_o and curr_c > prev_c and curr_rsi > prev_rsi and curr_rsi < 50.0

            bearish_exhaustion = (prev_high_dev >= self.exhaustion_threshold or curr_high_dev >= self.exhaustion_threshold)
            bearish_reversal = curr_c < curr_o and curr_c < prev_c and curr_rsi < prev_rsi and curr_rsi > 50.0

            if bullish_exhaustion and bullish_reversal:
                dev_mag = abs(min(prev_low_dev, curr_low_dev))
                confidence = float(np.clip(0.60 + (dev_mag - self.exhaustion_threshold) * 0.15, 0.60, 0.92))
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction="buy",
                    valid=True,
                    confidence=confidence,
                    rationale=f"Bullish mean reversion: Lower ATR exhaustion reached ({dev_mag:.2f} ATR below EMA) with positive reversal trigger (RSI: {curr_rsi:.1f}).",
                    tags=["mean_reversion", "atr_exhaustion", "oversold_bounce"]
                )

            elif bearish_exhaustion and bearish_reversal:
                dev_mag = max(prev_high_dev, curr_high_dev)
                confidence = float(np.clip(0.60 + (dev_mag - self.exhaustion_threshold) * 0.15, 0.60, 0.92))
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction="sell",
                    valid=True,
                    confidence=confidence,
                    rationale=f"Bearish mean reversion: Upper ATR exhaustion reached ({dev_mag:.2f} ATR above EMA) with negative reversal trigger (RSI: {curr_rsi:.1f}).",
                    tags=["mean_reversion", "atr_exhaustion", "overbought_fade"]
                )

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=True,
                confidence=0.0,
                rationale=f"No exhaustion setup detected. Current ATR deviation: {curr_close_dev:.2f} (Threshold: ±{self.exhaustion_threshold:.2f}).",
                tags=["neutral", "within_band"]
            )

        except Exception as e:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Calculation error: {e}",
                tags=["error"]
            )