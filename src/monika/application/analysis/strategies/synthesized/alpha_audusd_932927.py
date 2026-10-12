from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_audusd_932927(EdgeStrategy):
    strategy_id: str = "alpha_audusd_932927"
    applicable_symbols: set = {"AUDUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        # Institutional Hyperparameters for AUDUSD Mean Reversion
        self.ema_period: int = self.settings.get("ema_period", 20)
        self.atr_period: int = self.settings.get("atr_period", 14)
        self.exhaustion_multiplier: float = self.settings.get("exhaustion_multiplier", 2.2)
        self.rsi_period: int = self.settings.get("rsi_period", 14)
        self.rsi_oversold: float = self.settings.get("rsi_oversold", 30.0)
        self.rsi_overbought: float = self.settings.get("rsi_overbought", 70.0)
        self.trend_filter_period: int = self.settings.get("trend_filter_period", 50)
        self.trend_slope_threshold: float = self.settings.get("trend_slope_threshold", 0.15)
        self.timeframe: str = self.settings.get("timeframe", "H1")

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            # Fetch historical candles
            candles = await self.get_historical_candles(
                session=session, 
                symbol=symbol, 
                timeframe=self.timeframe, 
                limit=100
            )
            
            if not candles or len(candles) < max(self.trend_filter_period, 50):
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient historical candle data",
                    tags=["insufficient_data"]
                )

            # Parse candles safely into a Pandas DataFrame
            data = []
            for c in candles:
                if hasattr(c, 'close'):
                    data.append({
                        'open': float(c.open),
                        'high': float(c.high),
                        'low': float(c.low),
                        'close': float(c.close),
                        'volume': float(c.volume) if hasattr(c, 'volume') else 0.0
                    })
                elif isinstance(c, dict):
                    data.append({
                        'open': float(c.get('open', 0)),
                        'high': float(c.get('high', 0)),
                        'low': float(c.get('low', 0)),
                        'close': float(c.get('close', 0)),
                        'volume': float(c.get('volume', 0))
                    })

            df = pd.DataFrame(data)

            # Calculate True Range (TR) and Average True Range (ATR)
            high_low = df['high'] - df['low']
            high_cp = (df['high'] - df['close'].shift(1)).abs()
            low_cp = (df['low'] - df['close'].shift(1)).abs()
            tr = pd.concat([high_low, high_cp, low_cp], axis=1).max(axis=1)
            df['atr'] = tr.ewm(span=self.atr_period, adjust=False).mean()

            # Calculate EMAs
            df['ema'] = df['close'].ewm(span=self.ema_period, adjust=False).mean()
            df['ema_trend'] = df['close'].ewm(span=self.trend_filter_period, adjust=False).mean()

            # Calculate RSI
            delta = df['close'].diff()
            gain = delta.clip(lower=0)
            loss = -delta.clip(upper=0)
            avg_gain = gain.ewm(com=self.rsi_period - 1, adjust=False).mean()
            avg_loss = loss.ewm(com=self.rsi_period - 1, adjust=False).mean()
            rs = avg_gain / (avg_loss + 1e-10)
            df['rsi'] = 100 - (100 / (1 + rs))

            # Extract latest values
            last_row = df.iloc[-1]
            prev_row = df.iloc[-2]
            
            close = last_row['close']
            ema = last_row['ema']
            atr = last_row['atr']
            rsi = last_row['rsi']
            
            # Exhaustion Bands
            upper_band = ema + (self.exhaustion_multiplier * atr)
            lower_band = ema - (self.exhaustion_multiplier * atr)

            # Trend Filter: Slope of the long-term EMA normalized by ATR
            # Ensures we only trade mean reversion when the market is not in a strong trend
            slope = (last_row['ema_trend'] - df['ema_trend'].iloc[-6]) / (atr + 1e-10)
            is_ranging = abs(slope) < self.trend_slope_threshold

            direction = None
            confidence = 0.0
            rationale = "No signal generated"
            tags = ["neutral"]

            if is_ranging:
                # Buy Signal: Price exhausted below lower ATR band + RSI oversold
                if close < lower_band and rsi < self.rsi_oversold:
                    direction = "buy"
                    deviation = abs(close - ema) / (atr + 1e-10)
                    confidence = min(0.95, max(0.50, (deviation / self.exhaustion_multiplier) * 0.85))
                    rationale = f"AUDUSD exhausted below lower ATR band ({close:.5f} < {lower_band:.5f}) with RSI oversold ({rsi:.2f})."
                    tags = ["oversold", "mean_reversion", "atr_exhaustion"]
                
                # Sell Signal: Price exhausted above upper ATR band + RSI overbought
                elif close > upper_band and rsi > self.rsi_overbought:
                    direction = "sell"
                    deviation = abs(close - ema) / (atr + 1e-10)
                    confidence = min(0.95, max(0.50, (deviation / self.exhaustion_multiplier) * 0.85))
                    rationale = f"AUDUSD exhausted above upper ATR band ({close:.5f} > {upper_band:.5f}) with RSI overbought ({rsi:.2f})."
                    tags = ["overbought", "mean_reversion", "atr_exhaustion"]
            else:
                rationale = f"Market is trending strongly (slope: {slope:.4f}). Mean reversion suspended."
                tags = ["trending", "suspended"]

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=direction,
                valid=True if direction else False,
                confidence=round(confidence, 4),
                rationale=rationale,
                tags=tags
            )

        except Exception as e:
            logging.error(f"Error evaluating strategy {self.strategy_id}: {str(e)}")
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Execution error: {str(e)}",
                tags=["error"]
            )