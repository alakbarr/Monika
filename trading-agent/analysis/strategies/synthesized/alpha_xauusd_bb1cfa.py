from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xauusd_bb1cfa(EdgeStrategy):
    strategy_id: str = "alpha_xauusd_bb1cfa"
    applicable_symbols: set = {"XAUUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.atr_period = self.settings.get("atr_period", 14)
        self.sma_period = self.settings.get("sma_period", 20)
        self.atr_multiplier = self.settings.get("atr_multiplier", 2.2)
        self.rsi_period = self.settings.get("rsi_period", 14)
        self.rsi_oversold = self.settings.get("rsi_oversold", 30.0)
        self.rsi_overbought = self.settings.get("rsi_overbought", 70.0)

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
                    tags=["inapplicable"]
                )

            # Fetch H1 candles to capture intraday/daily exhaustion levels
            candles = await self.get_historical_candles(
                session=session, 
                symbol=symbol, 
                timeframe='H1', 
                limit=100
            )

            if not candles or len(candles) < max(self.atr_period, self.sma_period, self.rsi_period) + 5:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient candle history to calculate indicators.",
                    tags=["insufficient_data"]
                )

            # Parse candles safely
            data = []
            for c in candles:
                try:
                    high = float(c.high)
                    low = float(c.low)
                    close = float(c.close)
                    open_val = float(c.open)
                except (AttributeError, TypeError, KeyError):
                    high = float(c['high'])
                    low = float(c['low'])
                    close = float(c['close'])
                    open_val = float(c['open'])
                data.append({'high': high, 'low': low, 'close': close, 'open': open_val})

            df = pd.DataFrame(data)

            # Calculate ATR
            df['prev_close'] = df['close'].shift(1)
            df['tr1'] = df['high'] - df['low']
            df['tr2'] = (df['high'] - df['prev_close']).abs()
            df['tr3'] = (df['low'] - df['prev_close']).abs()
            df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
            df['atr'] = df['tr'].rolling(window=self.atr_period, min_periods=1).mean()

            # Calculate SMA
            df['sma'] = df['close'].rolling(window=self.sma_period, min_periods=1).mean()

            # Calculate RSI
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0.0)).rolling(window=self.rsi_period, min_periods=1).mean()
            loss = (-delta.where(delta < 0, 0.0)).rolling(window=self.rsi_period, min_periods=1).mean()
            rs = gain / (loss + 1e-9)
            df['rsi'] = 100.0 - (100.0 / (1.0 + rs))

            # Sanitize NaNs and Infs
            df = df.replace([np.inf, -np.inf], np.nan)
            df = df.ffill().bfill()

            if df.empty or len(df) < 2:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Dataframe empty after sanitization.",
                    tags=["empty_df"]
                )

            latest = df.iloc[-1]
            close = float(latest['close'])
            sma = float(latest['sma'])
            atr = float(latest['atr'])
            rsi = float(latest['rsi'])

            upper_band = sma + (self.atr_multiplier * atr)
            lower_band = sma - (self.atr_multiplier * atr)

            direction = None
            confidence = 0.0
            rationale = "Price within normal ATR bands. No exhaustion detected."
            tags = ["neutral"]

            # Mean Reversion Long: Price exhausted below lower ATR band + RSI oversold
            if close < lower_band and rsi < self.rsi_oversold:
                direction = "buy"
                deviation = lower_band - close
                confidence = min(0.95, 0.5 + (deviation / (atr + 1e-9)))
                rationale = (
                    f"XAUUSD exhausted below lower ATR band. "
                    f"Close: {close:.2f}, Lower Band: {lower_band:.2f}, "
                    f"RSI: {rsi:.2f} (Oversold). Expecting mean reversion to SMA: {sma:.2f}."
                )
                tags = ["exhaustion_oversold", "mean_reversion_buy"]

            # Mean Reversion Short: Price exhausted above upper ATR band + RSI overbought
            elif close > upper_band and rsi > self.rsi_overbought:
                direction = "sell"
                deviation = close - upper_band
                confidence = min(0.95, 0.5 + (deviation / (atr + 1e-9)))
                rationale = (
                    f"XAUUSD exhausted above upper ATR band. "
                    f"Close: {close:.2f}, Upper Band: {upper_band:.2f}, "
                    f"RSI: {rsi:.2f} (Overbought). Expecting mean reversion to SMA: {sma:.2f}."
                )
                tags = ["exhaustion_overbought", "mean_reversion_sell"]

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=direction,
                valid=True,
                confidence=float(confidence),
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