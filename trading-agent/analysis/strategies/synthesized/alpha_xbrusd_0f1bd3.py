from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xbrusd_0f1bd3(EdgeStrategy):
    strategy_id: str = "alpha_xbrusd_0f1bd3"
    applicable_symbols: set = {"XBRUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        cfg = self.settings or {}
        self.timeframe: str = str(cfg.get("timeframe", "H1"))
        self.candle_limit: int = int(cfg.get("candle_limit", 100))
        self.ema_period: int = int(cfg.get("ema_period", 21))
        self.atr_period: int = int(cfg.get("atr_period", 14))
        self.rsi_period: int = int(cfg.get("rsi_period", 14))
        self.exhaustion_multiplier: float = float(cfg.get("exhaustion_multiplier", 2.2))
        self.min_wick_ratio: float = float(cfg.get("min_wick_ratio", 0.30))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            if symbol.upper() not in self.applicable_symbols:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale=f"Symbol {symbol} is not applicable for {self.strategy_id}",
                    tags=["unsupported_symbol"]
                )

            candles = await self.get_historical_candles(
                session=session,
                symbol=symbol,
                timeframe=self.timeframe,
                limit=self.candle_limit
            )

            if not candles or len(candles) < max(self.ema_period, self.atr_period, self.rsi_period) + 5:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient historical candle data for ATR exhaustion calculation.",
                    tags=["insufficient_data"]
                )

            records: List[Dict[str, float]] = []
            for c in candles:
                try:
                    records.append({
                        "open": float(c.open),
                        "high": float(c.high),
                        "low": float(c.low),
                        "close": float(c.close)
                    })
                except (AttributeError, TypeError):
                    records.append({
                        "open": float(c["open"]),
                        "high": float(c["high"]),
                        "low": float(c["low"]),
                        "close": float(c["close"])
                    })

            df = pd.DataFrame(records)
            if df.empty or len(df) < self.ema_period:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Empty dataframe generated from candle data.",
                    tags=["empty_data"]
                )

            high = df["high"]
            low = df["low"]
            close = df["close"]
            open_p = df["open"]

            # EMA Baseline
            ema = close.ewm(span=self.ema_period, adjust=False).mean()

            # True Range and ATR
            prev_close = close.shift(1)
            tr1 = high - low
            tr2 = (high - prev_close).abs()
            tr3 = (low - prev_close).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr = tr.ewm(span=self.atr_period, adjust=False).mean()

            # Sanitization of ATR to avoid division by zero
            atr_clean = atr.replace(0.0, np.nan).ffill().bfill().fillna(0.01)

            # ATR normalized distance from EMA
            atr_dist = (close - ema) / atr_clean
            atr_dist = atr_dist.replace([np.inf, -np.inf], 0.0).fillna(0.0)

            # RSI Calculation
            delta = close.diff()
            gain = delta.clip(lower=0.0)
            loss = -delta.clip(upper=0.0)
            avg_gain = gain.ewm(com=self.rsi_period - 1, adjust=False).mean()
            avg_loss = loss.ewm(com=self.rsi_period - 1, adjust=False).mean()
            rs = avg_gain / avg_loss.replace(0.0, np.nan)
            rsi = 100.0 - (100.0 / (1.0 + rs))
            rsi = rsi.replace([np.inf, -np.inf], 50.0).ffill().bfill().fillna(50.0)

            # Latest state metrics
            curr_dist = float(atr_dist.iloc[-1])
            prev_dist = float(atr_dist.iloc[-2])
            curr_rsi = float(rsi.iloc[-1])
            curr_open = float(open_p.iloc[-1])
            curr_close = float(close.iloc[-1])
            curr_high = float(high.iloc[-1])
            curr_low = float(low.iloc[-1])
            curr_atr = float(atr_clean.iloc[-1])
            curr_ema = float(ema.iloc[-1])

            candle_span = max(curr_high - curr_low, 1e-6)
            upper_wick = curr_high - max(curr_open, curr_close)
            lower_wick = min(curr_open, curr_close) - curr_low
            upper_wick_ratio = upper_wick / candle_span
            lower_wick_ratio = lower_wick / candle_span

            direction: Optional[str] = None
            confidence: float = 0.0
            rationale: str = "Price within normal ATR volatility envelope."
            tags: List[str] = ["neutral"]

            # Overbought Exhaustion -> Mean Reversion Short
            if (curr_dist >= self.exhaustion_multiplier or prev_dist >= self.exhaustion_multiplier) and (curr_rsi >= 65.0 or upper_wick_ratio >= self.min_wick_ratio):
                dist_magnitude = max(curr_dist, prev_dist)
                dist_excess = max(0.0, dist_magnitude - self.exhaustion_multiplier)
                base_conf = 0.58 + min(0.22, dist_excess * 0.15)
                
                # Bonus for rejection structure
                wick_bonus = 0.08 if upper_wick_ratio >= self.min_wick_ratio else 0.0
                rsi_bonus = 0.06 if curr_rsi >= 70.0 else 0.0
                is_bearish_close = 0.04 if curr_close < curr_open else 0.0
                
                confidence = float(min(0.92, max(0.55, base_conf + wick_bonus + rsi_bonus + is_bearish_close)))
                direction = "sell"
                tags = ["mean_reversion", "overbought", "exhaustion"]
                rationale = (
                    f"XBRUSD upper ATR exhaustion triggered: ATR Dist={curr_dist:.2f}x (threshold={self.exhaustion_multiplier}x), "
                    f"RSI={curr_rsi:.1f}, Upper Wick Ratio={upper_wick_ratio:.1%}, EMA={curr_ema:.2f}, ATR={curr_atr:.2f}."
                )

            # Oversold Exhaustion -> Mean Reversion Long
            elif (curr_dist <= -self.exhaustion_multiplier or prev_dist <= -self.exhaustion_multiplier) and (curr_rsi <= 35.0 or lower_wick_ratio >= self.min_wick_ratio):
                dist_magnitude = abs(min(curr_dist, prev_dist))
                dist_excess = max(0.0, dist_magnitude - self.exhaustion_multiplier)
                base_conf = 0.58 + min(0.22, dist_excess * 0.15)

                wick_bonus = 0.08 if lower_wick_ratio >= self.min_wick_ratio else 0.0
                rsi_bonus = 0.06 if curr_rsi <= 30.0 else 0.0
                is_bullish_close = 0.04 if curr_close > curr_open else 0.0

                confidence = float(min(0.92, max(0.55, base_conf + wick_bonus + rsi_bonus + is_bullish_close)))
                direction = "buy"
                tags = ["mean_reversion", "oversold", "exhaustion"]
                rationale = (
                    f"XBRUSD lower ATR exhaustion triggered: ATR Dist={curr_dist:.2f}x (threshold=-{self.exhaustion_multiplier}x), "
                    f"RSI={curr_rsi:.1f}, Lower Wick Ratio={lower_wick_ratio:.1%}, EMA={curr_ema:.2f}, ATR={curr_atr:.2f}."
                )

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=direction,
                valid=(direction is not None),
                confidence=confidence if direction is not None else 0.0,
                rationale=rationale,
                tags=tags,
            )
        except Exception as e:
            return EdgeSignal(strategy_id=getattr(self, 'strategy_id', 'unknown'), symbol=getattr(self, 'symbol', 'unknown'), direction=None, valid=False, confidence=0.0, rationale=f'Calculation error: {e}', tags=['error'])
