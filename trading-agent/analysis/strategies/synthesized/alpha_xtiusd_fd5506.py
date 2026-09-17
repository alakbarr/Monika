from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xtiusd_fd5506(EdgeStrategy):
    strategy_id: str = "alpha_xtiusd_fd5506"
    applicable_symbols: set = {"XTIUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.timeframe: str = self.settings.get("timeframe", "H1")
        self.atr_period: int = int(self.settings.get("atr_period", 14))
        self.ema_period: int = int(self.settings.get("ema_period", 20))
        self.rsi_period: int = int(self.settings.get("rsi_period", 14))
        self.exhaustion_multiplier: float = float(self.settings.get("exhaustion_multiplier", 2.2))
        self.rsi_overbought: float = float(self.settings.get("rsi_overbought", 70.0))
        self.rsi_oversold: float = float(self.settings.get("rsi_oversold", 30.0))
        self.history_limit: int = int(self.settings.get("history_limit", 120))

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
                limit=self.history_limit
            )

            min_required = max(self.atr_period, self.ema_period, self.rsi_period) + 10
            if not candles or len(candles) < min_required:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient historical candle data for ATR exhaustion calculation.",
                    tags=["insufficient_data"]
                )

            # Build DataFrame
            records = []
            for c in candles:
                c_open = float(c.open) if hasattr(c, "open") else float(c["open"])
                c_high = float(c.high) if hasattr(c, "high") else float(c["high"])
                c_low = float(c.low) if hasattr(c, "low") else float(c["low"])
                c_close = float(c.close) if hasattr(c, "close") else float(c["close"])
                records.append({
                    "open": c_open,
                    "high": c_high,
                    "low": c_low,
                    "close": c_close
                })

            df = pd.DataFrame(records)

            # Calculate True Range & ATR
            df["prev_close"] = df["close"].shift(1)
            tr1 = df["high"] - df["low"]
            tr2 = (df["high"] - df["prev_close"]).abs()
            tr3 = (df["low"] - df["prev_close"]).abs()
            df["tr"] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            df["atr"] = df["tr"].rolling(window=self.atr_period, min_periods=self.atr_period).mean()

            # Calculate EMA Baseline
            df["ema"] = df["close"].ewm(span=self.ema_period, adjust=False).mean()

            # Calculate RSI
            delta = df["close"].diff()
            gain = delta.clip(lower=0.0)
            loss = (-delta).clip(lower=0.0)
            avg_gain = gain.rolling(window=self.rsi_period, min_periods=self.rsi_period).mean()
            avg_loss = loss.rolling(window=self.rsi_period, min_periods=self.rsi_period).mean()

            rs = avg_gain / (avg_loss.replace(0.0, np.nan))
            df["rsi"] = 100.0 - (100.0 / (1.0 + rs))
            df["rsi"] = df["rsi"].fillna(50.0)

            # Clean and sanitize NaNs
            df = df.ffill().bfill().fillna(0.0)

            curr = df.iloc[-1]
            prev = df.iloc[-2]

            atr_val = float(curr["atr"])
            ema_val = float(curr["ema"])
            close_val = float(curr["close"])
            open_val = float(curr["open"])
            high_val = float(curr["high"])
            low_val = float(curr["low"])
            rsi_val = float(curr["rsi"])

            if atr_val <= 0.0:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Calculated ATR is zero or invalid.",
                    tags=["invalid_atr"]
                )

            # Normalized distance from mean in ATR units
            atr_distance = (close_val - ema_val) / atr_val

            # Exhaustion Candle Patterns: Rejection wicks
            total_range = max(high_val - low_val, 1e-6)
            upper_wick = high_val - max(open_val, close_val)
            lower_wick = min(open_val, close_val) - low_val
            upper_wick_pct = upper_wick / total_range
            lower_wick_pct = lower_wick / total_range

            direction = None
            confidence = 0.0
            rationale_parts = []
            tags = ["mean_reversion", "atr_exhaustion"]

            # Overextended Upside -> Short Mean Reversion
            if atr_distance >= self.exhaustion_multiplier:
                is_rsi_exhausted = rsi_val >= self.rsi_overbought
                has_wick_rejection = upper_wick_pct >= 0.35

                if is_rsi_exhausted or has_wick_rejection:
                    direction = "sell"
                    base_conf = 0.65
                    atr_boost = min(0.20, (atr_distance - self.exhaustion_multiplier) * 0.15)
                    wick_boost = 0.10 if has_wick_rejection else 0.0
                    rsi_boost = 0.05 if is_rsi_exhausted else 0.0
                    confidence = min(0.95, base_conf + atr_boost + wick_boost + rsi_boost)

                    rationale_parts.append(
                        f"Upside exhaustion: Close {close_val:.2f} is +{atr_distance:.2f} ATR above EMA {ema_val:.2f}."
                    )
                    rationale_parts.append(f"RSI: {rsi_val:.1f}, Upper wick: {upper_wick_pct*100:.1f}%.")
                    tags.append("exhaustion_sell")

            # Overextended Downside -> Long Mean Reversion
            elif atr_distance <= -self.exhaustion_multiplier:
                is_rsi_exhausted = rsi_val <= self.rsi_oversold
                has_wick_rejection = lower_wick_pct >= 0.35

                if is_rsi_exhausted or has_wick_rejection:
                    direction = "buy"
                    base_conf = 0.65
                    atr_boost = min(0.20, (abs(atr_distance) - self.exhaustion_multiplier) * 0.15)
                    wick_boost = 0.10 if has_wick_rejection else 0.0
                    rsi_boost = 0.05 if is_rsi_exhausted else 0.0
                    confidence = min(0.95, base_conf + atr_boost + wick_boost + rsi_boost)

                    rationale_parts.append(
                        f"Downside exhaustion: Close {close_val:.2f} is {atr_distance:.2f} ATR below EMA {ema_val:.2f}."
                    )
                    rationale_parts.append(f"RSI: {rsi_val:.1f}, Lower wick: {lower_wick_pct*100:.1f}%.")
                    tags.append("exhaustion_buy")

            if direction is not None:
                rationale_str = " | ".join(rationale_parts)
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=direction,
                    valid=True,
                    confidence=round(confidence, 4),
                    rationale=rationale_str,
                    tags=tags
                )

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"No exhaustion edge. Distance: {atr_distance:.2f} ATR, RSI: {rsi_val:.1f}.",
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