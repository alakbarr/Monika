from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_audusd_aacbcf(EdgeStrategy):
    strategy_id: str = "alpha_audusd_aacbcf"
    applicable_symbols: set = {"AUDUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.atr_period: int = int(self.settings.get("atr_period", 14))
        self.ema_period: int = int(self.settings.get("ema_period", 20))
        self.rsi_period: int = int(self.settings.get("rsi_period", 14))
        self.exhaustion_multiplier: float = float(self.settings.get("exhaustion_multiplier", 2.2))
        self.rsi_ob: float = float(self.settings.get("rsi_ob", 70.0))
        self.rsi_os: float = float(self.settings.get("rsi_os", 30.0))
        self.timeframe: str = self.settings.get("timeframe", "H1")
        self.candle_limit: int = int(self.settings.get("candle_limit", 120))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            if symbol not in self.applicable_symbols:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale=f"Symbol {symbol} not supported by this strategy.",
                    tags=["unsupported_symbol"]
                )

            candles = await self.get_historical_candles(
                session=session,
                symbol=symbol,
                timeframe=self.timeframe,
                limit=self.candle_limit
            )

            if not candles or len(candles) < max(self.atr_period, self.ema_period, self.rsi_period) + 10:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient historical candle data for ATR exhaustion analysis.",
                    tags=["insufficient_data"]
                )

            opens = np.array([float(c.open if hasattr(c, "open") else c["open"]) for c in candles], dtype=np.float64)
            highs = np.array([float(c.high if hasattr(c, "high") else c["high"]) for c in candles], dtype=np.float64)
            lows = np.array([float(c.low if hasattr(c, "low") else c["low"]) for c in candles], dtype=np.float64)
            closes = np.array([float(c.close if hasattr(c, "close") else c["close"]) for c in candles], dtype=np.float64)

            df = pd.DataFrame({"open": opens, "high": highs, "low": lows, "close": closes})

            # Calculate True Range and ATR
            df["prev_close"] = df["close"].shift(1)
            tr1 = df["high"] - df["low"]
            tr2 = (df["high"] - df["prev_close"]).abs()
            tr3 = (df["low"] - df["prev_close"]).abs()
            df["tr"] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            df["atr"] = df["tr"].rolling(window=self.atr_period, min_periods=self.atr_period).mean()

            # Calculate EMA baseline
            df["ema"] = df["close"].ewm(span=self.ema_period, adjust=False).mean()

            # Calculate RSI
            delta = df["close"].diff()
            gain = delta.clip(lower=0.0)
            loss = -delta.clip(upper=0.0)
            avg_gain = gain.rolling(window=self.rsi_period, min_periods=self.rsi_period).mean()
            avg_loss = loss.rolling(window=self.rsi_period, min_periods=self.rsi_period).mean()
            
            # Use smoothed RSI values
            for i in range(self.rsi_period, len(df)):
                avg_gain.iloc[i] = (avg_gain.iloc[i - 1] * (self.rsi_period - 1) + gain.iloc[i]) / self.rsi_period
                avg_loss.iloc[i] = (avg_loss.iloc[i - 1] * (self.rsi_period - 1) + loss.iloc[i]) / self.rsi_period

            rs = avg_gain / avg_loss.replace(0.0, np.nan)
            df["rsi"] = 100.0 - (100.0 / (1.0 + rs))
            df["rsi"] = df["rsi"].ffill().bfill().fillna(50.0)

            # Sanitize calculations
            df["atr"] = df["atr"].ffill().bfill().fillna(0.0001)
            df["atr"] = np.where(df["atr"] <= 0.0, 0.0001, df["atr"])

            # ATR Exhaustion Metric: Distance of close from EMA normalized by ATR
            df["atr_deviation"] = (df["close"] - df["ema"]) / df["atr"]

            last_close = df["close"].iloc[-1]
            last_open = df["open"].iloc[-1]
            last_high = df["high"].iloc[-1]
            last_low = df["low"].iloc[-1]
            last_atr = df["atr"].iloc[-1]
            last_dev = df["atr_deviation"].iloc[-1]
            last_rsi = df["rsi"].iloc[-1]

            prev_dev = df["atr_deviation"].iloc[-2]

            direction = None
            confidence = 0.0
            rationale_parts = []
            tags = ["atr_exhaustion", "mean_reversion"]

            # Mean Reversion Buy: Price exhausted downwards, extreme negative ATR deviation and oversold RSI
            if last_dev <= -self.exhaustion_multiplier and last_rsi <= self.rsi_os:
                direction = "buy"
                # Check for stabilization / rejection pattern (lower shadow or reversal tick)
                lower_wick = min(last_open, last_close) - last_low
                body = abs(last_close - last_open)
                rejection = lower_wick > body * 0.5 or last_close > last_open
                
                base_conf = min(0.90, 0.65 + abs(last_dev - self.exhaustion_multiplier) * 0.08)
                if rejection:
                    base_conf = min(0.95, base_conf + 0.05)
                    tags.append("rejection_wick")

                confidence = round(base_conf, 2)
                rationale_parts.append(
                    f"Downside ATR exhaustion detected: Dev={last_dev:.2f} (threshold: -{self.exhaustion_multiplier}), "
                    f"RSI={last_rsi:.1f}, ATR={last_atr:.5f}."
                )

            # Mean Reversion Sell: Price exhausted upwards, extreme positive ATR deviation and overbought RSI
            elif last_dev >= self.exhaustion_multiplier and last_rsi >= self.rsi_ob:
                direction = "sell"
                # Check for stabilization / rejection pattern (upper shadow or reversal tick)
                upper_wick = last_high - max(last_open, last_close)
                body = abs(last_close - last_open)
                rejection = upper_wick > body * 0.5 or last_close < last_open

                base_conf = min(0.90, 0.65 + abs(last_dev - self.exhaustion_multiplier) * 0.08)
                if rejection:
                    base_conf = min(0.95, base_conf + 0.05)
                    tags.append("rejection_wick")

                confidence = round(base_conf, 2)
                rationale_parts.append(
                    f"Upside ATR exhaustion detected: Dev={last_dev:.2f} (threshold: {self.exhaustion_multiplier}), "
                    f"RSI={last_rsi:.1f}, ATR={last_atr:.5f}."
                )

            if direction is not None:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=direction,
                    valid=True,
                    confidence=confidence,
                    rationale=" ".join(rationale_parts),
                    tags=tags
                )

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"No ATR exhaustion setup. Current deviation: {last_dev:.2f}, RSI: {last_rsi:.1f}.",
                tags=["neutral"]
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
