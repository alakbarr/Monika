from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xtiusd_f30ff5(EdgeStrategy):
    strategy_id: str = "alpha_xtiusd_f30ff5"
    applicable_symbols: set = {"XTIUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.settings = settings or {}
        # Define default hyperparameters
        self.settings.setdefault("atr_period", 14)
        self.settings.setdefault("ema_period", 20)
        self.settings.setdefault("atr_multiplier", 2.5)
        self.settings.setdefault("rsi_period", 14)
        self.settings.setdefault("rsi_oversold", 30.0)
        self.settings.setdefault("rsi_overbought", 70.0)
        self.settings.setdefault("timeframe", "H1")
        self.settings.setdefault("limit", 100)

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
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

        try:
            # Resolve hyperparameters
            atr_period = int(settings.get("atr_period", self.settings.get("atr_period", 14)))
            ema_period = int(settings.get("ema_period", self.settings.get("ema_period", 20)))
            atr_multiplier = float(settings.get("atr_multiplier", self.settings.get("atr_multiplier", 2.5)))
            rsi_period = int(settings.get("rsi_period", self.settings.get("rsi_period", 14)))
            rsi_oversold = float(settings.get("rsi_oversold", self.settings.get("rsi_oversold", 30.0)))
            rsi_overbought = float(settings.get("rsi_overbought", self.settings.get("rsi_overbought", 70.0)))
            timeframe = str(settings.get("timeframe", self.settings.get("timeframe", "H1")))
            limit = int(settings.get("limit", self.settings.get("limit", 100)))

            # Fetch historical candles
            candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe=timeframe, limit=limit)
            if not candles or len(candles) < max(atr_period, ema_period, rsi_period) + 5:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient candle history to calculate indicators.",
                    tags=["insufficient_data"]
                )

            # Build DataFrame safely
            data = []
            for c in candles:
                try:
                    close_val = c.close if hasattr(c, 'close') else c['close']
                    high_val = c.high if hasattr(c, 'high') else c['high']
                    low_val = c.low if hasattr(c, 'low') else c['low']
                    open_val = c.open if hasattr(c, 'open') else c['open']
                except Exception:
                    close_val = c['close']
                    high_val = c['high']
                    low_val = c['low']
                    open_val = c['open']
                
                data.append({
                    'open': float(open_val),
                    'high': float(high_val),
                    'low': float(low_val),
                    'close': float(close_val)
                })

            df = pd.DataFrame(data)
            df.replace([np.inf, -np.inf], np.nan, inplace=True)
            df.ffill(inplace=True)
            df.bfill(inplace=True)

            # Calculate Indicators
            df['prev_close'] = df['close'].shift(1)
            df['tr1'] = df['high'] - df['low']
            df['tr2'] = (df['high'] - df['prev_close']).abs()
            df['tr3'] = (df['low'] - df['prev_close']).abs()
            df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
            
            df['atr'] = df['tr'].rolling(window=atr_period, min_periods=1).mean()
            df['ema'] = df['close'].ewm(span=ema_period, adjust=False, min_periods=1).mean()

            # RSI Calculation
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0.0)).rolling(window=rsi_period, min_periods=1).mean()
            loss = (-delta.where(delta < 0, 0.0)).rolling(window=rsi_period, min_periods=1).mean()
            rs = gain / (loss + 1e-9)
            df['rsi'] = 100.0 - (100.0 / (1.0 + rs))

            # Exhaustion Bands
            df['upper_band'] = df['ema'] + (atr_multiplier * df['atr'])
            df['lower_band'] = df['ema'] - (atr_multiplier * df['atr'])

            # Final sanitization
            df.bfill(inplace=True)
            df.ffill(inplace=True)

            if df.empty:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Processed DataFrame is empty.",
                    tags=["empty_df"]
                )

            # Extract latest values
            last_row = df.iloc[-1]
            close = float(last_row['close'])
            ema = float(last_row['ema'])
            atr = float(last_row['atr'])
            rsi = float(last_row['rsi'])
            upper_band = float(last_row['upper_band'])
            lower_band = float(last_row['lower_band'])

            direction = None
            confidence = 0.0
            rationale = "Price within normal ATR bands. No exhaustion detected."
            tags = ["neutral"]

            if atr > 0:
                # Buy Setup: Price pierces lower band and RSI is oversold
                if close < lower_band and rsi < rsi_oversold:
                    direction = "buy"
                    deviation = (lower_band - close) / atr
                    confidence = min(0.95, max(0.50, 0.50 + (deviation * 0.15)))
                    rationale = (
                        f"XTIUSD price ({close:.3f}) exhausted below lower ATR band ({lower_band:.3f}) "
                        f"with RSI ({rsi:.1f}) oversold. Expecting mean reversion to EMA ({ema:.3f})."
                    )
                    tags = ["mean_reversion", "oversold_exhaustion"]
                
                # Sell Setup: Price pierces upper band and RSI is overbought
                elif close > upper_band and rsi > rsi_overbought:
                    direction = "sell"
                    deviation = (close - upper_band) / atr
                    confidence = min(0.95, max(0.50, 0.50 + (deviation * 0.15)))
                    rationale = (
                        f"XTIUSD price ({close:.3f}) exhausted above upper ATR band ({upper_band:.3f}) "
                        f"with RSI ({rsi:.1f}) overbought. Expecting mean reversion to EMA ({ema:.3f})."
                    )
                    tags = ["mean_reversion", "overbought_exhaustion"]

            valid = direction is not None

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=direction,
                valid=valid,
                confidence=float(confidence),
                rationale=rationale,
                tags=tags
            )

        except Exception as e:
            logging.error(f"Error in strategy {self.strategy_id}: {str(e)}")
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Calculation error: {str(e)}",
                tags=["error"]
            )