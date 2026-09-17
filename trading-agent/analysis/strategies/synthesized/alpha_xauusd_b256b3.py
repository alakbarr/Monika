from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xauusd_b256b3(EdgeStrategy):
    strategy_id: str = "alpha_xauusd_b256b3"
    applicable_symbols: set = {"XAUUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.timeframe = self.settings.get("timeframe", "H1")
        self.atr_period = self.settings.get("atr_period", 14)
        self.ema_period = self.settings.get("ema_period", 20)
        self.rsi_period = self.settings.get("rsi_period", 14)
        self.atr_multiplier = self.settings.get("atr_multiplier", 2.2)
        self.rsi_oversold = self.settings.get("rsi_oversold", 30.0)
        self.rsi_overbought = self.settings.get("rsi_overbought", 70.0)

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            # Merge runtime settings with instance settings
            eval_settings = {**self.settings, **settings}
            timeframe = eval_settings.get("timeframe", self.timeframe)
            atr_period = eval_settings.get("atr_period", self.atr_period)
            ema_period = eval_settings.get("ema_period", self.ema_period)
            rsi_period = eval_settings.get("rsi_period", self.rsi_period)
            atr_multiplier = eval_settings.get("atr_multiplier", self.atr_multiplier)
            rsi_oversold = eval_settings.get("rsi_oversold", self.rsi_oversold)
            rsi_overbought = eval_settings.get("rsi_overbought", self.rsi_overbought)

            # Fetch historical candles
            candles = await self.get_historical_candles(
                session=session, 
                symbol=symbol, 
                timeframe=timeframe, 
                limit=100
            )

            if not candles or len(candles) < max(ema_period, atr_period, rsi_period) + 5:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient historical candle data.",
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
                except AttributeError:
                    high = float(c['high'])
                    low = float(c['low'])
                    close = float(c['close'])
                    open_val = float(c['open'])
                data.append({'open': open_val, 'high': high, 'low': low, 'close': close})

            df = pd.DataFrame(data)

            # Calculate True Range and ATR
            df['prev_close'] = df['close'].shift(1)
            df['tr1'] = df['high'] - df['low']
            df['tr2'] = (df['high'] - df['prev_close']).abs()
            df['tr3'] = (df['low'] - df['prev_close']).abs()
            df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
            df['atr'] = df['tr'].rolling(window=atr_period, min_periods=atr_period).mean()

            # Calculate EMA
            df['ema'] = df['close'].ewm(span=ema_period, adjust=False).mean()

            # Calculate RSI
            delta = df['close'].diff()
            gain = delta.clip(lower=0)
            loss = -delta.clip(upper=0)
            avg_gain = gain.rolling(window=rsi_period, min_periods=rsi_period).mean()
            avg_loss = loss.rolling(window=rsi_period, min_periods=rsi_period).mean()
            rs = avg_gain / (avg_loss + 1e-9)
            df['rsi'] = 100 - (100 / (1 + rs))

            # Sanitize NaNs/Infs
            df = df.ffill().bfill().fillna(0.0)

            if len(df) < 2:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Dataframe processing resulted in empty set.",
                    tags=["empty_dataframe"]
                )

            last_row = df.iloc[-1]
            close = float(last_row['close'])
            ema = float(last_row['ema'])
            atr = float(last_row['atr'])
            rsi = float(last_row['rsi'])
            high = float(last_row['high'])
            low = float(last_row['low'])
            open_val = float(last_row['open'])

            if atr <= 0:
                atr = 1e-4

            deviation = (close - ema) / atr
            candle_range = high - low if (high - low) > 0 else 1e-4
            
            direction = None
            confidence = 0.0
            rationale = "No ATR exhaustion detected."
            tags = ["neutral"]

            # Buy Condition: Price is significantly below EMA (exhaustion) and RSI is oversold
            if deviation < -atr_multiplier and rsi < rsi_oversold:
                direction = 'buy'
                # Calculate lower shadow rejection ratio
                lower_shadow = min(open_val, close) - low
                shadow_ratio = lower_shadow / candle_range
                
                # Base confidence on deviation magnitude, boosted by rejection shadow
                dev_factor = min(1.0, abs(deviation) / (atr_multiplier * 1.5))
                confidence = float(np.clip((dev_factor * 0.6) + (shadow_ratio * 0.4), 0.1, 1.0))
                
                rationale = (
                    f"XAUUSD Mean Reversion Buy: Price is {abs(deviation):.2f} ATRs below EMA. "
                    f"RSI is {rsi:.1f} (Oversold). Shadow rejection ratio: {shadow_ratio:.2%}."
                )
                tags = ["exhaustion_buy", "mean_reversion"]

            # Sell Condition: Price is significantly above EMA (exhaustion) and RSI is overbought
            elif deviation > atr_multiplier and rsi > rsi_overbought:
                direction = 'sell'
                # Calculate upper shadow rejection ratio
                upper_shadow = high - max(open_val, close)
                shadow_ratio = upper_shadow / candle_range
                
                # Base confidence on deviation magnitude, boosted by rejection shadow
                dev_factor = min(1.0, abs(deviation) / (atr_multiplier * 1.5))
                confidence = float(np.clip((dev_factor * 0.6) + (shadow_ratio * 0.4), 0.1, 1.0))
                
                rationale = (
                    f"XAUUSD Mean Reversion Sell: Price is {deviation:.2f} ATRs above EMA. "
                    f"RSI is {rsi:.1f} (Overbought). Shadow rejection ratio: {shadow_ratio:.2%}."
                )
                tags = ["exhaustion_sell", "mean_reversion"]

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
