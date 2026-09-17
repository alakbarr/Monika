from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xauusd_133dfb(EdgeStrategy):
    strategy_id: str = "alpha_xauusd_133dfb"
    applicable_symbols: set = {"XAUUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        cfg = self.settings or {}
        self.timeframe: str = str(cfg.get("timeframe", "H1"))
        self.atr_period: int = int(cfg.get("atr_period", 14))
        self.ema_period: int = int(cfg.get("ema_period", 21))
        self.rsi_period: int = int(cfg.get("rsi_period", 14))
        self.atr_exhaustion_threshold: float = float(cfg.get("atr_exhaustion_threshold", 2.6))
        self.rsi_ob: float = float(cfg.get("rsi_ob", 70.0))
        self.rsi_os: float = float(cfg.get("rsi_os", 30.0))
        self.min_history_candles: int = int(cfg.get("min_history_candles", 60))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            if symbol.upper() not in self.applicable_symbols:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale=f"Symbol {symbol} not in applicable symbols: {self.applicable_symbols}",
                    tags=["unsupported_symbol"]
                )

            candles = await self.get_historical_candles(
                session=session,
                symbol=symbol,
                timeframe=self.timeframe,
                limit=max(120, self.min_history_candles)
            )

            if not candles or len(candles) < self.min_history_candles:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale=f"Insufficient candle history. Required: {self.min_history_candles}, Received: {len(candles) if candles else 0}",
                    tags=["insufficient_data"]
                )

            # Robust extraction of OHLC data
            highs: List[float] = []
            lows: List[float] = []
            closes: List[float] = []
            opens: List[float] = []

            for c in candles:
                if hasattr(c, "open") and hasattr(c, "high") and hasattr(c, "low") and hasattr(c, "close"):
                    opens.append(float(c.open))
                    highs.append(float(c.high))
                    lows.append(float(c.low))
                    closes.append(float(c.close))
                elif isinstance(c, dict):
                    opens.append(float(c.get("open", 0.0)))
                    highs.append(float(c.get("high", 0.0)))
                    lows.append(float(c.get("low", 0.0)))
                    closes.append(float(c.get("close", 0.0)))
                else:
                    continue

            if len(closes) < self.min_history_candles:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Failed to parse sufficient OHLC data points",
                    tags=["data_parsing_error"]
                )

            df = pd.DataFrame({"open": opens, "high": highs, "low": lows, "close": closes})

            # Calculate True Range and ATR
            prev_close = df["close"].shift(1)
            tr1 = df["high"] - df["low"]
            tr2 = (df["high"] - prev_close).abs()
            tr3 = (df["low"] - prev_close).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr = tr.rolling(window=self.atr_period, min_periods=1).mean()
            atr = atr.replace(0.0, np.nan).ffill().bfill().fillna(1.0)

            # EMA anchor
            ema = df["close"].ewm(span=self.ema_period, adjust=False).mean()

            # Relative Strength Index (RSI)
            delta = df["close"].diff()
            gain = delta.clip(lower=0.0)
            loss = -delta.clip(upper=0.0)
            avg_gain = gain.ewm(alpha=1.0 / self.rsi_period, min_periods=self.rsi_period, adjust=False).mean()
            avg_loss = loss.ewm(alpha=1.0 / self.rsi_period, min_periods=self.rsi_period, adjust=False).mean()
            rs = avg_gain / avg_loss.replace(0.0, np.nan)
            rsi = 100.0 - (100.0 / (1.0 + rs))
            rsi = rsi.ffill().bfill().fillna(50.0)

            # Metrics for latest candle
            curr_close = float(df["close"].iloc[-1])
            curr_open = float(df["open"].iloc[-1])
            curr_high = float(df["high"].iloc[-1])
            curr_low = float(df["low"].iloc[-1])
            curr_ema = float(ema.iloc[-1])
            curr_atr = float(atr.iloc[-1])
            curr_rsi = float(rsi.iloc[-1])

            candle_range = max(curr_high - curr_low, 1e-5)
            upper_wick = curr_high - max(curr_open, curr_close)
            lower_wick = min(curr_open, curr_close) - curr_low
            upper_wick_ratio = upper_wick / candle_range
            lower_wick_ratio = lower_wick / candle_range

            # ATR Exhaustion Deviation
            atr_deviation = (curr_close - curr_ema) / curr_atr

            direction: Optional[str] = None
            confidence: float = 0.0
            rationale_parts: List[str] = []
            tags: List[str] = ["atr_exhaustion", "mean_reversion"]

            # Bearish Exhaustion (Overbought / Extended Above EMA) -> Sell
            if atr_deviation >= self.atr_exhaustion_threshold and curr_rsi >= self.rsi_ob:
                direction = "sell"
                deviation_excess = min(atr_deviation - self.atr_exhaustion_threshold, 2.0)
                wick_boost = min(upper_wick_ratio * 0.15, 0.10)
                rsi_factor = min((curr_rsi - self.rsi_ob) / 30.0, 0.15)
                base_conf = 0.65
                confidence = float(min(base_conf + (deviation_excess * 0.10) + wick_boost + rsi_factor, 0.95))
                rationale_parts.append(
                    f"Bearish ATR exhaustion detected. Deviation: +{atr_deviation:.2f} ATR (Threshold: {self.atr_exhaustion_threshold}), "
                    f"RSI: {curr_rsi:.1f}, Upper Wick Ratio: {upper_wick_ratio:.2%}, Target EMA: {curr_ema:.2f}"
                )
                tags.extend(["exhaustion_high", "overbought"])

            # Bullish Exhaustion (Oversold / Extended Below EMA) -> Buy
            elif atr_deviation <= -self.atr_exhaustion_threshold and curr_rsi <= self.rsi_os:
                direction = "buy"
                deviation_excess = min(abs(atr_deviation) - self.atr_exhaustion_threshold, 2.0)
                wick_boost = min(lower_wick_ratio * 0.15, 0.10)
                rsi_factor = min((self.rsi_os - curr_rsi) / 30.0, 0.15)
                base_conf = 0.65
                confidence = float(min(base_conf + (deviation_excess * 0.10) + wick_boost + rsi_factor, 0.95))
                rationale_parts.append(
                    f"Bullish ATR exhaustion detected. Deviation: {atr_deviation:.2f} ATR (Threshold: -{self.atr_exhaustion_threshold}), "
                    f"RSI: {curr_rsi:.1f}, Lower Wick Ratio: {lower_wick_ratio:.2%}, Target EMA: {curr_ema:.2f}"
                )
                tags.extend(["exhaustion_low", "oversold"])

            if direction is not None and confidence >= 0.60:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=direction,
                    valid=True,
                    confidence=round(confidence, 4),
                    rationale=" | ".join(rationale_parts),
                    tags=tags
                )

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"No mean-reversion exhaustion trigger. ATR Deviation: {atr_deviation:.2f}, RSI: {curr_rsi:.1f}",
                tags=["neutral_exhaustion"]
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
