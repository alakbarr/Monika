from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_usdjpy_131b6e(EdgeStrategy):
    strategy_id: str = "alpha_usdjpy_131b6e"
    applicable_symbols: set = {"USDJPY"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.atr_period = int(self.settings.get("atr_period", 14))
        self.ma_period = int(self.settings.get("ma_period", 20))
        self.atr_mult_threshold = float(self.settings.get("atr_mult_threshold", 2.2))
        self.rsi_period = int(self.settings.get("rsi_period", 14))
        self.rsi_overbought = float(self.settings.get("rsi_overbought", 68.0))
        self.rsi_oversold = float(self.settings.get("rsi_oversold", 32.0))
        self.atr_ma_period = int(self.settings.get("atr_ma_period", 50))
        self.atr_exhaustion_ratio = float(self.settings.get("atr_exhaustion_ratio", 1.15))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            if symbol not in self.applicable_symbols:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale=f"Symbol {symbol} not applicable for strategy {self.strategy_id}.",
                    tags=["invalid_symbol"]
                )

            timeframe = settings.get("timeframe", "H1")
            limit = int(settings.get("candle_limit", 120))

            candles = await self.get_historical_candles(
                session=session,
                symbol=symbol,
                timeframe=timeframe,
                limit=limit
            )

            if not candles or len(candles) < max(self.ma_period, self.atr_ma_period) + 5:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient historical candles available.",
                    tags=["insufficient_data"]
                )

            df_data = []
            for c in candles:
                if isinstance(c, dict):
                    df_data.append({
                        'open': float(c['open']),
                        'high': float(c['high']),
                        'low': float(c['low']),
                        'close': float(c['close']),
                    })
                else:
                    df_data.append({
                        'open': float(c.open),
                        'high': float(c.high),
                        'low': float(c.low),
                        'close': float(c.close),
                    })

            df = pd.DataFrame(df_data)

            # ATR Calculation
            high = df['high']
            low = df['low']
            close = df['close']
            prev_close = close.shift(1)

            tr1 = high - low
            tr2 = (high - prev_close).abs()
            tr3 = (low - prev_close).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

            atr = tr.rolling(window=self.atr_period, min_periods=1).mean()
            atr = atr.ffill().bfill().fillna(1e-4)

            # Moving Average Baseline (Exponential Moving Average)
            ma = close.ewm(span=self.ma_period, adjust=False).mean()

            # Price distance from EMA in ATR multiples
            dev = close - ma
            atr_dist = dev / atr
            atr_dist = atr_dist.replace([np.inf, -np.inf], 0.0).fillna(0.0)

            # Long-term ATR average to detect volatility expansion/exhaustion
            atr_ma = atr.rolling(window=self.atr_ma_period, min_periods=1).mean()
            atr_ratio = atr / (atr_ma + 1e-8)
            atr_ratio = atr_ratio.replace([np.inf, -np.inf], 1.0).fillna(1.0)

            # Relative Strength Index (RSI) Calculation
            delta = close.diff()
            gain = delta.clip(lower=0.0)
            loss = (-delta).clip(lower=0.0)
            avg_gain = gain.rolling(window=self.rsi_period, min_periods=1).mean()
            avg_loss = loss.rolling(window=self.rsi_period, min_periods=1).mean()
            rs = avg_gain / (avg_loss + 1e-8)
            rsi = 100.0 - (100.0 / (1.0 + rs))
            rsi = rsi.ffill().bfill().fillna(50.0)

            curr_dist = float(atr_dist.iloc[-1])
            curr_atr_ratio = float(atr_ratio.iloc[-1])
            curr_rsi = float(rsi.iloc[-1])

            direction = None
            confidence = 0.0
            rationale_parts = []

            is_atr_exhausted = curr_atr_ratio >= self.atr_exhaustion_ratio

            # Mean Reversion Logic
            if curr_dist >= self.atr_mult_threshold and curr_rsi >= self.rsi_overbought:
                direction = "sell"
                dist_factor = min((curr_dist - self.atr_mult_threshold) / 2.0, 0.25)
                rsi_factor = min((curr_rsi - self.rsi_overbought) / 30.0, 0.20)
                exhaustion_bonus = 0.10 if is_atr_exhausted else 0.0
                confidence = round(min(0.55 + dist_factor + rsi_factor + exhaustion_bonus, 0.95), 4)

                rationale_parts.append(
                    f"Overbought ATR exhaustion signal on USDJPY: ATR Dist={curr_dist:.2f} (>= {self.atr_mult_threshold}), "
                    f"RSI={curr_rsi:.1f} (>= {self.rsi_overbought}), ATR Ratio={curr_atr_ratio:.2f}."
                )

            elif curr_dist <= -self.atr_mult_threshold and curr_rsi <= self.rsi_oversold:
                direction = "buy"
                dist_factor = min((abs(curr_dist) - self.atr_mult_threshold) / 2.0, 0.25)
                rsi_factor = min((self.rsi_oversold - curr_rsi) / 30.0, 0.20)
                exhaustion_bonus = 0.10 if is_atr_exhausted else 0.0
                confidence = round(min(0.55 + dist_factor + rsi_factor + exhaustion_bonus, 0.95), 4)

                rationale_parts.append(
                    f"Oversold ATR exhaustion signal on USDJPY: ATR Dist={curr_dist:.2f} (<= -{self.atr_mult_threshold}), "
                    f"RSI={curr_rsi:.1f} (<= {self.rsi_oversold}), ATR Ratio={curr_atr_ratio:.2f}."
                )
            else:
                rationale_parts.append(
                    f"Neutral: ATR Dist={curr_dist:.2f}, RSI={curr_rsi:.1f}, ATR Ratio={curr_atr_ratio:.2f}. "
                    f"No threshold breach for mean reversion."
                )

            valid = direction is not None
            rationale = " ".join(rationale_parts)
            tags = ["mean_reversion", "atr_exhaustion", "usdjpy"]
            if valid:
                tags.append(f"signal_{direction}")

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=direction,
                valid=valid,
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
                rationale=f"Calculation error: {e}",
                tags=["error"]
            )
