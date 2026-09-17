from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_gbpusd_1fb4c5(EdgeStrategy):
    strategy_id: str = "alpha_gbpusd_1fb4c5"
    applicable_symbols: set = {"GBPUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.timeframe = self.settings.get("timeframe", "H1")
        self.atr_period = int(self.settings.get("atr_period", 14))
        self.ema_period = int(self.settings.get("ema_period", 20))
        self.atr_multiplier = float(self.settings.get("atr_multiplier", 2.5))
        self.rsi_period = int(self.settings.get("rsi_period", 14))
        self.rsi_overbought = float(self.settings.get("rsi_overbought", 70.0))
        self.rsi_oversold = float(self.settings.get("rsi_oversold", 30.0))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            if symbol not in self.applicable_symbols:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale=f"Symbol {symbol} is not applicable for this strategy.",
                    tags=["inapplicable"]
                )

            # Fetch historical candles
            limit = max(self.atr_period, self.ema_period, self.rsi_period) * 3 + 10
            candles = await self.get_historical_candles(
                session=session,
                symbol=symbol,
                timeframe=self.timeframe,
                limit=limit
            )

            if not candles or len(candles) < limit:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale=f"Insufficient candle history. Got {len(candles) if candles else 0}, need {limit}.",
                    tags=["insufficient_data"]
                )

            # Parse candles to DataFrame safely
            data = []
            for c in candles:
                if hasattr(c, 'close'):
                    data.append({
                        'open': float(c.open),
                        'high': float(c.high),
                        'low': float(c.low),
                        'close': float(c.close),
                    })
                else:
                    data.append({
                        'open': float(c.get('open', 0.0)),
                        'high': float(c.get('high', 0.0)),
                        'low': float(c.get('low', 0.0)),
                        'close': float(c.get('close', 0.0)),
                    })

            df = pd.DataFrame(data)
            df = df.replace([np.inf, -np.inf], np.nan).ffill().bfill()

            # Calculate ATR
            df['h_l'] = df['high'] - df['low']
            df['h_pc'] = (df['high'] - df['close'].shift(1)).abs()
            df['l_pc'] = (df['low'] - df['close'].shift(1)).abs()
            df['tr'] = df[['h_l', 'h_pc', 'l_pc']].max(axis=1)
            df['atr'] = df['tr'].rolling(window=self.atr_period, min_periods=1).mean()

            # Calculate EMA
            df['ema'] = df['close'].ewm(span=self.ema_period, adjust=False, min_periods=1).mean()

            # Calculate RSI
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0.0)).rolling(window=self.rsi_period, min_periods=1).mean()
            loss = (-delta.where(delta < 0, 0.0)).rolling(window=self.rsi_period, min_periods=1).mean()
            rs = gain / loss.replace(0.0, np.nan)
            df['rsi'] = 100.0 - (100.0 / (1.0 + rs))
            df['rsi'] = df['rsi'].fillna(50.0)

            # Final cleanup of indicators
            df = df.ffill().bfill()

            if df.empty:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="DataFrame is empty after processing indicators.",
                    tags=["empty_dataframe"]
                )

            last_row = df.iloc[-1]
            close = float(last_row['close'])
            ema = float(last_row['ema'])
            atr = float(last_row['atr'])
            rsi = float(last_row['rsi'])

            if atr <= 0:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="ATR is zero or negative, cannot calculate bands.",
                    tags=["invalid_atr"]
                )

            upper_band = ema + (self.atr_multiplier * atr)
            lower_band = ema - (self.atr_multiplier * atr)

            direction = None
            confidence = 0.0
            rationale = "Price within normal ATR bands."
            tags = ["neutral"]

            # Check for exhaustion
            if close >= upper_band and rsi >= self.rsi_overbought:
                direction = "sell"
                deviation = (close - ema) / (atr * self.atr_multiplier) if atr > 0 else 1.0
                confidence = min(0.95, max(0.5, 0.5 + (deviation - 1.0) * 0.5))
                rationale = f"Price ({close:.5f}) exhausted above upper ATR band ({upper_band:.5f}) with RSI ({rsi:.2f}) overbought."
                tags = ["exhaustion", "overbought", "mean_reversion"]

            elif close <= lower_band and rsi <= self.rsi_oversold:
                direction = "buy"
                deviation = (ema - close) / (atr * self.atr_multiplier) if atr > 0 else 1.0
                confidence = min(0.95, max(0.5, 0.5 + (deviation - 1.0) * 0.5))
                rationale = f"Price ({close:.5f}) exhausted below lower ATR band ({lower_band:.5f}) with RSI ({rsi:.2f}) oversold."
                tags = ["exhaustion", "oversold", "mean_reversion"]

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=direction,
                valid=True,
                confidence=float(confidence) if direction else 0.0,
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
                rationale=f"Calculation error: {str(e)}",
                tags=["error"]
            )