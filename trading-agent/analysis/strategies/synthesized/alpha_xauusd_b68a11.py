from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xauusd_b68a11(EdgeStrategy):
    strategy_id: str = "alpha_xauusd_b68a11"
    applicable_symbols: set = {"XAUUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.atr_period: int = int(self.settings.get("atr_period", 14))
        self.baseline_period: int = int(self.settings.get("baseline_period", 20))
        self.atr_multiplier: float = float(self.settings.get("atr_multiplier", 2.3))
        self.rsi_period: int = int(self.settings.get("rsi_period", 14))
        self.rsi_ob: float = float(self.settings.get("rsi_ob", 70.0))
        self.rsi_os: float = float(self.settings.get("rsi_os", 30.0))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            if symbol.upper() not in self.applicable_symbols:
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
                limit=100
            )

            if not candles or len(candles) < max(self.baseline_period, self.atr_period, self.rsi_period) + 10:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient historical candle data for ATR exhaustion analysis.",
                    tags=["insufficient_data"]
                )

            records = []
            for c in candles:
                c_open = float(c.open if hasattr(c, 'open') else c['open'])
                c_high = float(c.high if hasattr(c, 'high') else c['high'])
                c_low = float(c.low if hasattr(c, 'low') else c['low'])
                c_close = float(c.close if hasattr(c, 'close') else c['close'])
                c_volume = float(c.volume if hasattr(c, 'volume') else c.get('volume', 0.0))
                records.append({
                    'open': c_open,
                    'high': c_high,
                    'low': c_low,
                    'close': c_close,
                    'volume': c_volume
                })

            df = pd.DataFrame(records)

            # Calculate True Range & ATR
            df['prev_close'] = df['close'].shift(1)
            tr1 = df['high'] - df['low']
            tr2 = (df['high'] - df['prev_close']).abs()
            tr3 = (df['low'] - df['prev_close']).abs()
            df['tr'] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            df['atr'] = df['tr'].rolling(window=self.atr_period, min_periods=self.atr_period).mean()

            # Baseline EMA
            df['ema'] = df['close'].ewm(span=self.baseline_period, adjust=False).mean()

            # Relative Strength Index (RSI)
            delta = df['close'].diff()
            gain = delta.clip(lower=0.0)
            loss = -delta.clip(upper=0.0)
            avg_gain = gain.rolling(window=self.rsi_period, min_periods=self.rsi_period).mean()
            avg_loss = loss.rolling(window=self.rsi_period, min_periods=self.rsi_period).mean()
            rs = avg_gain / (avg_loss.replace(0.0, 1e-9))
            df['rsi'] = 100.0 - (100.0 / (1.0 + rs))

            df = df.ffill().bfill()

            curr = df.iloc[-1]
            prev = df.iloc[-2]

            current_atr = float(curr['atr'])
            if current_atr <= 0:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Invalid ATR value",
                    tags=["invalid_atr"],
                )

            current_close = float(curr['close'])
            current_ema = float(curr['ema'])
            current_rsi = float(curr['rsi'])
            upper_band = current_ema + (self.atr_multiplier * current_atr)
            lower_band = current_ema - (self.atr_multiplier * current_atr)

            if current_close > upper_band and current_rsi > self.rsi_ob:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction="sell",
                    valid=True,
                    confidence=min(0.85, 0.6 + (current_rsi - self.rsi_ob) * 0.01),
                    rationale=f"Mean reversion sell: Close {current_close:.2f} above upper ATR band {upper_band:.2f} with RSI {current_rsi:.1f}",
                    tags=["mean_reversion", "overbought", "atr_exhaustion"],
                )
            elif current_close < lower_band and current_rsi < self.rsi_os:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction="buy",
                    valid=True,
                    confidence=min(0.85, 0.6 + (self.rsi_os - current_rsi) * 0.01),
                    rationale=f"Mean reversion buy: Close {current_close:.2f} below lower ATR band {lower_band:.2f} with RSI {current_rsi:.1f}",
                    tags=["mean_reversion", "oversold", "atr_exhaustion"],
                )

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale="No ATR exhaustion signal triggered",
                tags=["neutral"],
            )
        except Exception as e:
            return EdgeSignal(strategy_id=getattr(self, 'strategy_id', 'unknown'), symbol=getattr(self, 'symbol', 'unknown'), direction=None, valid=False, confidence=0.0, rationale=f'Calculation error: {e}', tags=['error'])
