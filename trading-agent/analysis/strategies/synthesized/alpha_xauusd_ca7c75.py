from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xauusd_ca7c75(EdgeStrategy):
    strategy_id: str = "alpha_xauusd_ca7c75"
    applicable_symbols: set = {"XAUUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.timeframe = self.settings.get("timeframe", "H1")
        self.atr_period = int(self.settings.get("atr_period", 14))
        self.ma_period = int(self.settings.get("ma_period", 20))
        self.stretch_threshold = float(self.settings.get("stretch_threshold", 2.0))
        self.rsi_period = int(self.settings.get("rsi_period", 14))
        self.rsi_overbought = float(self.settings.get("rsi_overbought", 70.0))
        self.rsi_oversold = float(self.settings.get("rsi_oversold", 30.0))
        self.min_candles = int(self.settings.get("min_candles", 30))

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
                limit=100
            )

            if not candles or len(candles) < self.min_candles:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale=f"Insufficient candle data: received {len(candles) if candles else 0}, required {self.min_candles}",
                    tags=["insufficient_data"]
                )

            df = pd.DataFrame([{
                'open': float(c.open if hasattr(c, 'open') else c['open']),
                'high': float(c.high if hasattr(c, 'high') else c['high']),
                'low': float(c.low if hasattr(c, 'low') else c['low']),
                'close': float(c.close if hasattr(c, 'close') else c['close']),
                'volume': float(c.volume if hasattr(c, 'volume') else c.get('volume', 0.0))
            } for c in candles])

            # Calculate True Range and ATR
            prev_close = df['close'].shift(1)
            tr1 = df['high'] - df['low']
            tr2 = (df['high'] - prev_close).abs()
            tr3 = (df['low'] - prev_close).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

            df['atr'] = tr.rolling(window=self.atr_period, min_periods=1).mean()
            df['atr'] = df['atr'].replace(0, np.nan).ffill().bfill().fillna(1.0)

            # Calculate Moving Average and ATR Z-score (Stretch)
            df['ma'] = df['close'].rolling(window=self.ma_period, min_periods=1).mean()
            df['atr_z'] = (df['close'] - df['ma']) / df['atr']

            # Calculate RSI
            delta = df['close'].diff()
            gain = delta.clip(lower=0)
            loss = -delta.clip(upper=0)
            avg_gain = gain.rolling(window=self.rsi_period, min_periods=1).mean()
            avg_loss = loss.rolling(window=self.rsi_period, min_periods=1).mean()
            rs = avg_gain / avg_loss.replace(0, np.nan)
            df['rsi'] = 100.0 - (100.0 / (1.0 + rs.fillna(0.0)))
            df['rsi'] = df['rsi'].fillna(50.0)

            # Volatility exhaustion baseline
            df['atr_ma'] = df['atr'].rolling(window=10, min_periods=1).mean()

            latest = df.iloc[-1]
            curr_z = float(latest['atr_z'])
            curr_rsi = float(latest['rsi'])
            curr_atr = float(latest['atr'])
            curr_atr_ma = float(latest['atr_ma'])

            atr_exhausted = curr_atr > (curr_atr_ma * 1.05)

            direction = None
            confidence = 0.0
            rationale_parts = []

            # Bearish Mean Reversion Signal
            if curr_z >= self.stretch_threshold and (curr_rsi >= self.rsi_overbought or atr_exhausted):
                direction = 'sell'
                stretch_factor = min(2.0, curr_z / self.stretch_threshold)
                rsi_factor = min(1.5, max(1.0, curr_rsi / self.rsi_overbought)) if curr_rsi >= self.rsi_overbought else 1.1
                confidence = min(0.95, round(0.50 * stretch_factor * rsi_factor, 2))
                rationale_parts.append(
                    f"Upper ATR stretch exhausted on XAUUSD (Z-score={curr_z:.2f} >= {self.stretch_threshold}, RSI={curr_rsi:.1f})"
                )

            # Bullish Mean Reversion Signal
            elif curr_z <= -self.stretch_threshold and (curr_rsi <= self.rsi_oversold or atr_exhausted):
                direction = 'buy'
                stretch_factor = min(2.0, abs(curr_z) / self.stretch_threshold)
                rsi_factor = min(1.5, max(1.0, (100.0 - curr_rsi) / (100.0 - self.rsi_oversold))) if curr_rsi <= self.rsi_oversold else 1.1
                confidence = min(0.95, round(0.50 * stretch_factor * rsi_factor, 2))
                rationale_parts.append(
                    f"Lower ATR stretch exhausted on XAUUSD (Z-score={curr_z:.2f} <= -{self.stretch_threshold}, RSI={curr_rsi:.1f})"
                )

            else:
                direction = None
                confidence = 0.0
                rationale_parts.append(
                    f"No ATR exhaustion setup detected (Z-score={curr_z:.2f}, RSI={curr_rsi:.1f})"
                )

            rationale = "; ".join(rationale_parts)
            tags = ["mean_reversion", "atr_exhaustion", "xauusd"]
            if direction:
                tags.append(f"signal_{direction}")

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=direction,
                valid=True,
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
