from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xauusd_63216a(EdgeStrategy):
    strategy_id: str = "alpha_xauusd_63216a"
    applicable_symbols: set = {"XAUUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.timeframe = self.settings.get("timeframe", "H1")
        self.atr_period = int(self.settings.get("atr_period", 14))
        self.ema_period = int(self.settings.get("ema_period", 20))
        self.rsi_period = int(self.settings.get("rsi_period", 14))
        self.atr_exhaustion_threshold = float(self.settings.get("atr_exhaustion_threshold", 2.2))
        self.rsi_overbought = float(self.settings.get("rsi_overbought", 68.0))
        self.rsi_oversold = float(self.settings.get("rsi_oversold", 32.0))
        self.candle_limit = int(self.settings.get("candle_limit", 100))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            if symbol not in self.applicable_symbols:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale=f"Symbol {symbol} is not supported by {self.strategy_id}",
                    tags=["invalid_symbol"]
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
                    rationale="Insufficient candle history for analysis",
                    tags=["insufficient_data"]
                )

            data = []
            for c in candles:
                if isinstance(c, dict):
                    o = float(c.get('open', 0.0))
                    h = float(c.get('high', 0.0))
                    l = float(c.get('low', 0.0))
                    cl = float(c.get('close', 0.0))
                    v = float(c.get('volume', 0.0))
                else:
                    o = float(c.open)
                    h = float(c.high)
                    l = float(c.low)
                    cl = float(c.close)
                    try:
                        v = float(c.volume)
                    except AttributeError:
                        v = 0.0
                data.append({'open': o, 'high': h, 'low': l, 'close': cl, 'volume': v})

            df = pd.DataFrame(data)

            # ATR Calculation
            df['prev_close'] = df['close'].shift(1)
            tr1 = df['high'] - df['low']
            tr2 = (df['high'] - df['prev_close']).abs()
            tr3 = (df['low'] - df['prev_close']).abs()
            df['tr'] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            df['atr'] = df['tr'].ewm(span=self.atr_period, adjust=False).mean()

            # EMA Calculation
            df['ema'] = df['close'].ewm(span=self.ema_period, adjust=False).mean()

            # Normalized ATR Distance (Z-Score analogue for exhaustion)
            atr_denom = df['atr'].replace(0.0, np.nan)
            df['atr_dev'] = (df['close'] - df['ema']) / atr_denom
            df['atr_dev'] = df['atr_dev'].replace([np.inf, -np.inf], np.nan).ffill().bfill().fillna(0.0)

            # RSI Calculation
            delta = df['close'].diff()
            gain = delta.clip(lower=0.0)
            loss = -1.0 * delta.clip(upper=0.0)
            avg_gain = gain.ewm(com=self.rsi_period - 1, min_periods=self.rsi_period).mean()
            avg_loss = loss.ewm(com=self.rsi_period - 1, min_periods=self.rsi_period).mean()
            rs = avg_gain / avg_loss.replace(0.0, np.nan)
            df['rsi'] = 100.0 - (100.0 / (1.0 + rs))
            df['rsi'] = df['rsi'].replace([np.inf, -np.inf], np.nan).ffill().bfill().fillna(50.0)

            latest = df.iloc[-1]
            curr_close = float(latest['close'])
            curr_ema = float(latest['ema'])
            curr_atr = float(latest['atr'])
            curr_dev = float(latest['atr_dev'])
            curr_rsi = float(latest['rsi'])

            direction = None
            tags = ["mean_reversion", "atr_exhaustion", "xauusd"]

            if curr_dev <= -self.atr_exhaustion_threshold and curr_rsi <= self.rsi_oversold:
                direction = 'buy'
                tags.append("oversold_exhaustion")
            elif curr_dev >= self.atr_exhaustion_threshold and curr_rsi >= self.rsi_overbought:
                direction = 'sell'
                tags.append("overbought_exhaustion")

            if direction is not None:
                excess_dev = max(0.0, abs(curr_dev) - self.atr_exhaustion_threshold)
                if direction == 'buy':
                    excess_rsi = max(0.0, self.rsi_oversold - curr_rsi)
                else:
                    excess_rsi = max(0.0, curr_rsi - self.rsi_overbought)

                raw_confidence = 0.65 + (excess_dev * 0.10) + (excess_rsi * 0.01)
                confidence = float(min(0.95, max(0.50, raw_confidence)))
                rationale = (
                    f"ATR exhaustion mean-reversion triggered on {symbol} ({self.timeframe}): "
                    f"Close={curr_close:.2f}, EMA{self.ema_period}={curr_ema:.2f}, ATR={curr_atr:.2f}, "
                    f"ATR Dev={curr_dev:.2f} (threshold={self.atr_exhaustion_threshold}), RSI={curr_rsi:.1f}. Direction: {direction.upper()}."
                )
            else:
                confidence = 0.0
                rationale = (
                    f"No ATR exhaustion setup on {symbol} ({self.timeframe}): "
                    f"ATR Dev={curr_dev:.2f}, RSI={curr_rsi:.1f}."
                )

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
