from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xbrusd_042cd9(EdgeStrategy):
    strategy_id: str = "alpha_xbrusd_042cd9"
    applicable_symbols: set = {"XBRUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        cfg = settings or {}
        self.ema_period: int = int(cfg.get("ema_period", 20))
        self.atr_period: int = int(cfg.get("atr_period", 14))
        self.atr_exhaustion_mult: float = float(cfg.get("atr_exhaustion_mult", 2.25))
        self.rsi_period: int = int(cfg.get("rsi_period", 14))
        self.rsi_oversold: float = float(cfg.get("rsi_oversold", 30.0))
        self.rsi_overbought: float = float(cfg.get("rsi_overbought", 70.0))
        self.min_history: int = int(cfg.get("min_history", 60))

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
                timeframe="H1",
                limit=120
            )

            if not candles or len(candles) < self.min_history:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient historical candle data for ATR exhaustion analysis.",
                    tags=["insufficient_data"]
                )

            # Build DataFrame
            records = []
            for c in candles:
                c_open = float(c.open if hasattr(c, "open") else c["open"])
                c_high = float(c.high if hasattr(c, "high") else c["high"])
                c_low = float(c.low if hasattr(c, "low") else c["low"])
                c_close = float(c.close if hasattr(c, "close") else c["close"])
                c_vol = float(c.volume if hasattr(c, "volume") else c.get("volume", 1.0))
                records.append({
                    "open": c_open,
                    "high": c_high,
                    "low": c_low,
                    "close": c_close,
                    "volume": c_vol
                })

            df = pd.DataFrame(records)

            # Compute True Range and ATR
            df["prev_close"] = df["close"].shift(1)
            tr1 = df["high"] - df["low"]
            tr2 = (df["high"] - df["prev_close"]).abs()
            tr3 = (df["low"] - df["prev_close"]).abs()
            df["tr"] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            df["atr"] = df["tr"].rolling(window=self.atr_period, min_periods=self.atr_period).mean().ffill().bfill()

            # Baseline EMA
            df["ema"] = df["close"].ewm(span=self.ema_period, adjust=False).mean()

            # Relative Strength Index (RSI)
            delta = df["close"].diff()
            gain = delta.clip(lower=0.0)
            loss = -delta.clip(upper=0.0)
            avg_gain = gain.rolling(window=self.rsi_period, min_periods=self.rsi_period).mean()
            avg_loss = loss.rolling(window=self.rsi_period, min_periods=self.rsi_period).mean()
            rs = avg_gain / (avg_loss.replace(0.0, 1e-9))
            df["rsi"] = 100.0 - (100.0 / (1.0 + rs))
            df["rsi"] = df["rsi"].ffill().bfill().fillna(50.0)

            # Volume Moving Average
            df["vol_sma"] = df["volume"].rolling(window=20, min_periods=5).mean().ffill().bfill().fillna(1.0)

            # Current state indicators
            curr = df.iloc[-1]
            prev = df.iloc[-2]

            atr_val = float(curr["atr"])
            if atr_val <= 0.0:
                atr_val = 1e-4

            ema_val = float(curr["ema"])
            close_val = float(curr["close"])
            open_val = float(curr["open"])
            high_val = float(curr["high"])
            low_val = float(curr["low"])
            rsi_val = float(curr["rsi"])
            vol_val = float(curr["volume"])
            vol_sma_val = float(curr["vol_sma"])

            # Normalized ATR deviation
            dev_atr = (close_val - ema_val) / atr_val
            candle_range = max(high_val - low_val, 1e-4)
            lower_wick_ratio = (min(open_val, close_val) - low_val) / candle_range
            upper_wick_ratio = (high_val - max(open_val, close_val)) / candle_range

            upper_band = ema_val + (self.atr_exhaustion_mult * atr_val)
            lower_band = ema_val - (self.atr_exhaustion_mult * atr_val)

            direction: Optional[str] = None
            confidence: float = 0.0
            rationale_parts: List[str] = []
            tags: List[str] = ["mean_reversion", "atr_exhaustion"]

            # Long Reversal: Downside ATR Exhaustion
            long_exhaustion = (low_val <= lower_band or dev_atr <= -self.atr_exhaustion_mult) and (rsi_val <= self.rsi_oversold or float(prev["rsi"]) <= self.rsi_oversold)
            # Short Reversal: Upside ATR Exhaustion
            short_exhaustion = (high_val >= upper_band or dev_atr >= self.atr_exhaustion_mult) and (rsi_val >= self.rsi_overbought or float(prev["rsi"]) >= self.rsi_overbought)

            if long_exhaustion and not short_exhaustion:
                direction = "buy"
                confidence = 0.65

                # Adjust confidence based on exhaustion quality
                if dev_atr <= -(self.atr_exhaustion_mult + 0.5):
                    confidence += 0.10
                    tags.append("extreme_atr_stretch")

                if rsi_val <= 25.0:
                    confidence += 0.08
                    tags.append("deep_oversold")

                if lower_wick_ratio >= 0.35 or close_val > open_val:
                    confidence += 0.07
                    tags.append("hammer_rejection")

                if vol_sma_val > 0 and vol_val >= 1.3 * vol_sma_val:
                    confidence += 0.05
                    tags.append("volume_climax")

                confidence = min(round(confidence, 2), 0.95)
                rationale_parts.append(
                    f"XBRUSD oversold ATR exhaustion detected. Deviation: {dev_atr:.2f} ATR below EMA{self.ema_period} "
                    f"(Band: {lower_band:.2f}, Close: {close_val:.2f}, RSI: {rsi_val:.1f}). Reversion to mean expected."
                )

            elif short_exhaustion and not long_exhaustion:
                direction = "sell"
                confidence = 0.65

                # Adjust confidence based on exhaustion quality
                if dev_atr >= (self.atr_exhaustion_mult + 0.5):
                    confidence += 0.10
                    tags.append("extreme_atr_stretch")

                if rsi_val >= 75.0:
                    confidence += 0.08
                    tags.append("deep_overbought")

                if upper_wick_ratio >= 0.35 or close_val < open_val:
                    confidence += 0.07
                    tags.append("shooting_star_rejection")

                if vol_sma_val > 0 and vol_val >= 1.3 * vol_sma_val:
                    confidence += 0.05
                    tags.append("volume_climax")

                confidence = min(round(confidence, 2), 0.95)
                rationale_parts.append(
                    f"XBRUSD overbought ATR exhaustion detected. Deviation: {dev_atr:.2f} ATR above EMA{self.ema_period} "
                    f"(Band: {upper_band:.2f}, Close: {close_val:.2f}, RSI: {rsi_val:.1f}). Reversion to mean expected."
                )

            if direction is not None and confidence >= 0.60:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=direction,
                    valid=True,
                    confidence=confidence,
                    rationale=" | ".join(rationale_parts),
                    tags=tags
                )
            else:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale=f"No ATR exhaustion setup on XBRUSD. Current ATR dev: {dev_atr:.2f}, RSI: {rsi_val:.1f}.",
                    tags=["neutral"]
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
