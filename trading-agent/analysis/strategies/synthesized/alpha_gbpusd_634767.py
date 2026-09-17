from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_gbpusd_634767(EdgeStrategy):
    strategy_id: str = "alpha_gbpusd_634767"
    applicable_symbols: set = {"GBPUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.atr_period = self.settings.get("atr_period", 14)
        self.ema_period = self.settings.get("ema_period", 20)
        self.rsi_period = self.settings.get("rsi_period", 14)
        self.exhaustion_threshold = self.settings.get("exhaustion_threshold", 2.5)
        self.rsi_oversold = self.settings.get("rsi_oversold", 30.0)
        self.rsi_overbought = self.settings.get("rsi_overbought", 70.0)
        self.timeframe = self.settings.get("timeframe", "H1")
        self.limit = self.settings.get("limit", 100)

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            # Merge runtime settings if provided
            atr_period = settings.get("atr_period", self.atr_period)
            ema_period = settings.get("ema_period", self.ema_period)
            rsi_period = settings.get("rsi_period", self.rsi_period)
            exhaustion_threshold = settings.get("exhaustion_threshold", self.exhaustion_threshold)
            rsi_oversold = settings.get("rsi_oversold", self.rsi_oversold)
            rsi_overbought = settings.get("rsi_overbought", self.rsi_overbought)
            timeframe = settings.get("timeframe", self.timeframe)
            limit = settings.get("limit", self.limit)

            # Fetch historical candles
            candles = await self.get_historical_candles(
                session=session, symbol=symbol, timeframe=timeframe, limit=limit
            )

            if not candles or len(candles) < max(atr_period, ema_period, rsi_period) + 5:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient historical data.",
                    tags=["insufficient_data"]
                )

            # Convert candles to DataFrame safely supporting both object and dict interfaces
            df_data = []
            for c in candles:
                try:
                    c_open = float(c.open)
                    c_high = float(c.high)
                    c_low = float(c.low)
                    c_close = float(c.close)
                except AttributeError:
                    c_open = float(c['open'])
                    c_high = float(c['high'])
                    c_low = float(c['low'])
                    c_close = float(c['close'])
                
                df_data.append({
                    'open': c_open,
                    'high': c_high,
                    'low': c_low,
                    'close': c_close
                })
            
            df = pd.DataFrame(df_data)

            # Clean input data
            df = df.replace([np.inf, -np.inf], np.nan)
            df = df.ffill().bfill()

            # Calculate True Range (TR) and Average True Range (ATR)
            df['prev_close'] = df['close'].shift(1)
            df['tr1'] = df['high'] - df['low']
            df['tr2'] = (df['high'] - df['prev_close']).abs()
            df['tr3'] = (df['low'] - df['prev_close']).abs()
            df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
            
            df['atr'] = df['tr'].rolling(window=atr_period, min_periods=1).mean()
            df['ema'] = df['close'].ewm(span=ema_period, adjust=False, min_periods=1).mean()
            
            # Calculate Relative Strength Index (RSI)
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0.0)).rolling(window=rsi_period, min_periods=1).mean()
            loss = (-delta.where(delta < 0, 0.0)).rolling(window=rsi_period, min_periods=1).mean()
            rs = gain / (loss + 1e-9)
            df['rsi'] = 100.0 - (100.0 / (1.0 + rs))

            # Clean calculated indicators
            df = df.replace([np.inf, -np.inf], np.nan)
            df = df.ffill().bfill()

            # Calculate ATR Exhaustion Ratio
            df['deviation'] = df['close'] - df['ema']
            df['atr_ratio'] = df['deviation'] / (df['atr'] + 1e-9)

            # Extract latest values
            latest_ratio = float(df['atr_ratio'].iloc[-1])
            latest_rsi = float(df['rsi'].iloc[-1])
            latest_close = float(df['close'].iloc[-1])
            latest_ema = float(df['ema'].iloc[-1])

            direction = None
            confidence = 0.0
            rationale = "Price within normal ATR bands."
            tags = ["neutral"]

            # Mean Reversion Buy Signal (Downside Exhaustion)
            if latest_ratio <= -exhaustion_threshold and latest_rsi <= rsi_oversold:
                direction = "buy"
                confidence = min(0.95, max(0.5, abs(latest_ratio) / (exhaustion_threshold * 1.5)))
                rationale = (
                    f"GBPUSD downside exhaustion detected. Price: {latest_close:.5f} is "
                    f"{abs(latest_ratio):.2f}x ATR below the {ema_period}-EMA. RSI: {latest_rsi:.1f}."
                )
                tags = ["mean_reversion", "oversold_exhaustion", "bullish"]

            # Mean Reversion Sell Signal (Upside Exhaustion)
            elif latest_ratio >= exhaustion_threshold and latest_rsi >= rsi_overbought:
                direction = "sell"
                confidence = min(0.95, max(0.5, abs(latest_ratio) / (exhaustion_threshold * 1.5)))
                rationale = (
                    f"GBPUSD upside exhaustion detected. Price: {latest_close:.5f} is "
                    f"{latest_ratio:.2f}x ATR above the {ema_period}-EMA. RSI: {latest_rsi:.1f}."
                )
                tags = ["mean_reversion", "overbought_exhaustion", "bearish"]

            valid = direction is not None

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=direction,
                valid=valid,
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
                rationale=f"Calculation error: {str(e)}",
                tags=["error"]
            )