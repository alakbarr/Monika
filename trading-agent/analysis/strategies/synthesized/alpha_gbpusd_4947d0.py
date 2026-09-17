from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_gbpusd_4947d0(EdgeStrategy):
    strategy_id: str = "alpha_gbpusd_4947d0"
    applicable_symbols: set = {"GBPUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        # Define hyperparameters for ATR exhaustion mean reversion
        self.atr_period: int = 14
        self.ema_period: int = 20
        self.multiplier: float = 2.5
        self.rsi_period: int = 14

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        # Default neutral signal
        neutral_signal = EdgeSignal(
            strategy_id=self.strategy_id,
            symbol=symbol,
            direction=None,
            valid=False,
            confidence=0.0,
            rationale="Insufficient data or no setup detected.",
            tags=[]
        )

        if symbol not in self.applicable_symbols:
            return neutral_signal

        try:
            # Fetch historical candles (H1 timeframe is optimal for GBPUSD ATR exhaustion)
            candles = await self.get_historical_candles(
                session=session, 
                symbol=symbol, 
                timeframe='H1', 
                limit=100
            )
            
            if not candles or len(candles) < max(self.atr_period, self.ema_period, self.rsi_period) + 10:
                return neutral_signal

            # Parse candles safely supporting both object attributes and dictionary formats
            records = []
            for c in candles:
                if isinstance(c, dict):
                    records.append({
                        'open': float(c.get('open', 0)),
                        'high': float(c.get('high', 0)),
                        'low': float(c.get('low', 0)),
                        'close': float(c.get('close', 0))
                    })
                else:
                    records.append({
                        'open': float(c.open),
                        'high': float(c.high),
                        'low': float(c.low),
                        'close': float(c.close)
                    })

            df = pd.DataFrame(records)

            # Calculate True Range (TR) and Average True Range (ATR)
            df['close_prev'] = df['close'].shift(1)
            df['tr1'] = df['high'] - df['low']
            df['tr2'] = (df['high'] - df['close_prev']).abs()
            df['tr3'] = (df['low'] - df['close_prev']).abs()
            df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
            
            df['atr'] = df['tr'].rolling(window=self.atr_period).mean()
            df['ema'] = df['close'].ewm(span=self.ema_period, adjust=False).mean()
            
            # Calculate RSI for overbought/oversold confirmation
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
            rs = gain / (loss + 1e-9)
            df['rsi'] = 100 - (100 / (1 + rs))

            # Extract latest values
            latest = df.iloc[-1]
            curr_close = latest['close']
            curr_high = latest['high']
            curr_low = latest['low']
            curr_open = latest['open']
            curr_ema = latest['ema']
            curr_atr = latest['atr']
            curr_rsi = latest['rsi']

            if pd.isna(curr_ema) or pd.isna(curr_atr) or pd.isna(curr_rsi) or curr_atr == 0:
                return neutral_signal

            # Define exhaustion bands
            upper_band = curr_ema + (self.multiplier * curr_atr)
            lower_band = curr_ema - (self.multiplier * curr_atr)

            candle_range = curr_high - curr_low
            if candle_range == 0:
                candle_range = 1e-9

            # Rejection wick criteria (at least 20% of the candle range must be the rejection wick)
            is_buy_setup = (
                curr_low < lower_band and 
                curr_rsi < 35 and 
                (curr_close > curr_low + 0.2 * candle_range)
            )

            is_sell_setup = (
                curr_high > upper_band and 
                curr_rsi > 65 and 
                (curr_close < curr_high - 0.2 * candle_range)
            )

            direction = None
            confidence = 0.0
            rationale = ""
            tags = ["mean-reversion", "atr-exhaustion"]

            if is_buy_setup:
                direction = 'buy'
                # Scale confidence based on penetration depth and RSI oversold level
                penetration = (lower_band - curr_low) / curr_atr
                rsi_factor = (35 - curr_rsi) / 35
                confidence = min(0.95, max(0.60, 0.5 + (penetration * 0.15) + (rsi_factor * 0.2)))
                rationale = (
                    f"GBPUSD ATR exhaustion buy signal. Low ({curr_low:.5f}) penetrated "
                    f"lower band ({lower_band:.5f}) with RSI at {curr_rsi:.2f}. Rejection wick confirmed."
                )
                tags.append("oversold-rebound")
                
            elif is_sell_setup:
                direction = 'sell'
                # Scale confidence based on penetration depth and RSI overbought level
                penetration = (curr_high - upper_band) / curr_atr
                rsi_factor = (curr_rsi - 65) / 35
                confidence = min(0.95, max(0.60, 0.5 + (penetration * 0.15) + (rsi_factor * 0.2)))
                rationale = (
                    f"GBPUSD ATR exhaustion sell signal. High ({curr_high:.5f}) penetrated "
                    f"upper band ({upper_band:.5f}) with RSI at {curr_rsi:.2f}. Rejection wick confirmed."
                )
                tags.append("overbought-reversal")

            if direction:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=direction,
                    valid=True,
                    confidence=round(confidence, 2),
                    rationale=rationale,
                    tags=tags
                )

        except Exception as e:
            logging.error(f"Error in strategy {self.strategy_id}: {str(e)}")
            return neutral_signal

        return neutral_signal