from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_gbpusd_867953(EdgeStrategy):
    strategy_id: str = "alpha_gbpusd_867953"
    applicable_symbols: set = {"GBPUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.ema_period: int = int(self.settings.get("ema_period", 20))
        self.atr_period: int = int(self.settings.get("atr_period", 14))
        self.rsi_period: int = int(self.settings.get("rsi_period", 14))
        self.stretch_threshold: float = float(self.settings.get("stretch_threshold", 2.2))
        self.rsi_ob: float = float(self.settings.get("rsi_ob", 70.0))
        self.rsi_os: float = float(self.settings.get("rsi_os", 30.0))
        self.min_wick_ratio: float = float(self.settings.get("min_wick_ratio", 0.25))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            if symbol not in self.applicable_symbols:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale=f"Symbol {symbol} not supported by strategy.",
                    tags=["unsupported_symbol"]
                )

            candles = await self.get_historical_candles(
                session=session,
                symbol=symbol,
                timeframe='H1',
                limit=120
            )

            if not candles or len(candles) < max(self.ema_period, self.atr_period, self.rsi_period) + 10:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient candle history for indicator calculations.",
                    tags=["insufficient_data"]
                )

            records: List[Dict[str, float]] = []
            for c in candles:
                c_open = float(c.open if hasattr(c, 'open') else c['open'])
                c_high = float(c.high if hasattr(c, 'high') else c['high'])
                c_low = float(c.low if hasattr(c, 'low') else c['low'])
                c_close = float(c.close if hasattr(c, 'close') else c['close'])
                records.append({'open': c_open, 'high': c_high, 'low': c_low, 'close': c_close})

            df = pd.DataFrame.from_records(records)

            # Price action metrics
            df['prev_close'] = df['close'].shift(1)
            tr1 = df['high'] - df['low']
            tr2 = (df['high'] - df['prev_close']).abs()
            tr3 = (df['low'] - df['prev_close']).abs()
            df['tr'] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

            # Wilders / EMA smoothing for ATR
            df['atr'] = df['tr'].ewm(alpha=1.0 / self.atr_period, adjust=False).mean()
            df['ema'] = df['close'].ewm(span=self.ema_period, adjust=False).mean()

            # RSI Calculation
            delta = df['close'].diff()
            gain = delta.where(delta > 0, 0.0).ewm(alpha=1.0 / self.rsi_period, adjust=False).mean()
            loss = (-delta.where(delta < 0, 0.0)).ewm(alpha=1.0 / self.rsi_period, adjust=False).mean()
            
            rs = gain / loss.replace(0.0, 1e-9)
            df['rsi'] = 100.0 - (100.0 / (1.0 + rs))

            # ATR Exhaustion Stretch
            atr_safe = df['atr'].replace(0.0, np.nan).ffill().bfill().fillna(1e-4)
            df['atr_stretch'] = (df['close'] - df['ema']) / atr_safe

            # Candlestick Rejection Analysis
            candle_span = (df['high'] - df['low']).replace(0.0, 1e-5)
            body_min = df[['open', 'close']].min(axis=1)
            body_max = df[['open', 'close']].max(axis=1)
            df['lower_wick_ratio'] = (body_min - df['low']) / candle_span
            df['upper_wick_ratio'] = (df['high'] - body_max) / candle_span

            # Sanitize numerical metrics
            df = df.ffill().bfill().fillna(0.0)

            latest = df.iloc[-1]
            prev = df.iloc[-2]

            current_close = float(latest['close'])
            current_ema = float(latest['ema'])
            current_atr = float(latest['atr'])
            current_stretch = float(latest['atr_stretch'])
            current_rsi = float(latest['rsi'])
            lower_wick = float(latest['lower_wick_ratio'])
            upper_wick = float(latest['upper_wick_ratio'])

            direction: Optional[str] = None
            confidence: float = 0.0
            rationale_parts: List[str] = []
            signal_tags: List[str] = ["atr_exhaustion", "mean_reversion"]

            # Bullish Exhaustion Mean Reversion
            if current_stretch <= -self.stretch_threshold and current_rsi <= self.rsi_os:
                if lower_wick >= self.min_wick_ratio or prev['atr_stretch'] < current_stretch:
                    direction = 'buy'
                    excess = abs(current_stretch) - self.stretch_threshold
                    confidence = min(0.92, max(0.60, 0.60 + (excess * 0.15) + (lower_wick * 0.20)))
                    rationale_parts.append(
                        f"Oversold exhaustion detected: ATR Stretch={current_stretch:.2f} (<= -{self.stretch_threshold}), "
                        f"RSI={current_rsi:.1f}, Lower Wick Ratio={lower_wick:.2%}, Baseline EMA={current_ema:.5f}"
                    )
                    signal_tags.append("bullish_reversal")

            # Bearish Exhaustion Mean Reversion
            elif current_stretch >= self.stretch_threshold and current_rsi >= self.rsi_ob:
                if upper_wick >= self.min_wick_ratio or prev['atr_stretch'] > current_stretch:
                    direction = 'sell'
                    excess = current_stretch - self.stretch_threshold
                    confidence = min(0.92, max(0.60, 0.60 + (excess * 0.15) + (upper_wick * 0.20)))
                    rationale_parts.append(
                        f"Overbought exhaustion detected: ATR Stretch={current_stretch:.2f} (>= +{self.stretch_threshold}), "
                        f"RSI={current_rsi:.1f}, Upper Wick Ratio={upper_wick:.2%}, Baseline EMA={current_ema:.5f}"
                    )
                    signal_tags.append("bearish_reversal")

            if direction is not None:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=direction,
                    valid=True,
                    confidence=round(confidence, 4),
                    rationale=" | ".join(rationale_parts),
                    tags=signal_tags
                )

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=True,
                confidence=0.0,
                rationale=(
                    f"No exhaustion setup: Stretch={current_stretch:.2f} within thresholds "
                    f"[-{self.stretch_threshold}, {self.stretch_threshold}], RSI={current_rsi:.1f}"
                ),
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