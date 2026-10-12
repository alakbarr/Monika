from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xbrusd_ec8f88(EdgeStrategy):
    strategy_id: str = "alpha_xbrusd_ec8f88"
    applicable_symbols: set = {"XBRUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.timeframe = self.settings.get("timeframe", "H1")
        self.limit = self.settings.get("limit", 100)
        self.ema_period = self.settings.get("ema_period", 20)
        self.atr_period = self.settings.get("atr_period", 14)
        self.atr_multiplier = self.settings.get("atr_multiplier", 2.8)
        self.rsi_period = self.settings.get("rsi_period", 14)
        self.rsi_oversold = self.settings.get("rsi_oversold", 25)
        self.rsi_overbought = self.settings.get("rsi_overbought", 75)

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            # Fetch historical candles
            candles = await self.get_historical_candles(
                session=session, 
                symbol=symbol, 
                timeframe=self.timeframe, 
                limit=self.limit
            )
            
            required_candles = max(self.ema_period, self.atr_period, self.rsi_period) + 5
            if not candles or len(candles) < required_candles:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient candle history for indicator calculation",
                    tags=["insufficient_data"]
                )

            # Build DataFrame safely
            data = []
            for c in candles:
                try:
                    close_val = float(c.close) if hasattr(c, 'close') else float(c['close'])
                    high_val = float(c.high) if hasattr(c, 'high') else float(c['high'])
                    low_val = float(c.low) if hasattr(c, 'low') else float(c['low'])
                    open_val = float(c.open) if hasattr(c, 'open') else float(c['open'])
                    volume_val = float(c.volume) if hasattr(c, 'volume') else float(c['volume'])
                except Exception:
                    continue
                data.append({
                    'open': open_val,
                    'high': high_val,
                    'low': low_val,
                    'close': close_val,
                    'volume': volume_val
                })

            if len(data) < required_candles:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Failed to parse sufficient candle data",
                    tags=["parse_error"]
                )

            df = pd.DataFrame(data)
            df = df.ffill().bfill()

            # Calculate EMA
            df['ema'] = df['close'].ewm(span=self.ema_period, adjust=False).mean()

            # Calculate ATR
            high_low = df['high'] - df['low']
            high_cp = (df['high'] - df['close'].shift(1)).abs()
            low_cp = (df['low'] - df['close'].shift(1)).abs()
            
            tr = pd.concat([high_low, high_cp, low_cp], axis=1).max(axis=1)
            df['atr'] = tr.ewm(span=self.atr_period, adjust=False).mean()

            # Calculate RSI
            diff = df['close'].diff()
            gain = diff.clip(lower=0)
            loss = -diff.clip(upper=0)
            
            avg_gain = gain.ewm(com=self.rsi_period - 1, adjust=False).mean()
            avg_loss = loss.ewm(com=self.rsi_period - 1, adjust=False).mean()
            
            rs = avg_gain / (avg_loss + 1e-9)
            df['rsi'] = 100 - (100 / (1 + rs))

            # Calculate Distance from EMA in terms of ATR
            df['distance'] = (df['close'] - df['ema']) / (df['atr'] + 1e-9)

            # Clean up any NaNs or Infs
            df = df.replace([np.inf, -np.inf], np.nan)
            df = df.ffill().bfill().fillna(0.0)

            # Get latest values
            last_row = df.iloc[-1]
            distance = float(last_row['distance'])
            rsi = float(last_row['rsi'])
            close_price = float(last_row['close'])

            direction = None
            confidence = 0.0
            rationale = ""
            tags = ["mean_reversion", "atr_exhaustion"]

            # Signal Logic
            # Buy: Price is significantly below EMA (exhaustion) and RSI is oversold
            if distance < -self.atr_multiplier and rsi < self.rsi_oversold:
                direction = "buy"
                confidence = min(0.95, max(0.5, abs(distance) / (self.atr_multiplier * 1.5)))
                rationale = (
                    f"XBRUSD price ({close_price:.2f}) is exhausted to the downside. "
                    f"Distance from EMA({self.ema_period}) is {distance:.2f} ATRs (threshold: -{self.atr_multiplier}). "
                    f"RSI is oversold at {rsi:.1f}."
                )
                tags.append("oversold_exhaustion")

            # Sell: Price is significantly above EMA (exhaustion) and RSI is overbought
            elif distance > self.atr_multiplier and rsi > self.rsi_overbought:
                direction = "sell"
                confidence = min(0.95, max(0.5, abs(distance) / (self.atr_multiplier * 1.5)))
                rationale = (
                    f"XBRUSD price ({close_price:.2f}) is exhausted to the upside. "
                    f"Distance from EMA({self.ema_period}) is {distance:.2f} ATRs (threshold: {self.atr_multiplier}). "
                    f"RSI is overbought at {rsi:.1f}."
                )
                tags.append("overbought_exhaustion")
            else:
                rationale = (
                    f"No exhaustion detected. Distance from EMA: {distance:.2f} ATRs. RSI: {rsi:.1f}."
                )

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=direction,
                valid=True,
                confidence=confidence if direction else 0.0,
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