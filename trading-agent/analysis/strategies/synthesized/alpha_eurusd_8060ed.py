from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_eurusd_8060ed(EdgeStrategy):
    strategy_id: str = "alpha_eurusd_8060ed"
    applicable_symbols: set = {"EURUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.base_lookback = self.settings.get("base_lookback", 20)
        self.min_lookback = self.settings.get("min_lookback", 8)
        self.max_lookback = self.settings.get("max_lookback", 40)
        self.volume_ma_period = self.settings.get("volume_ma_period", 20)
        self.volume_trigger_threshold = self.settings.get("volume_trigger_threshold", 1.25)
        self.trend_filter_period = self.settings.get("trend_filter_period", 50)

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        # Merge runtime settings if provided
        base_lookback = settings.get("base_lookback", self.base_lookback)
        min_lookback = settings.get("min_lookback", self.min_lookback)
        max_lookback = settings.get("max_lookback", self.max_lookback)
        volume_ma_period = settings.get("volume_ma_period", self.volume_ma_period)
        volume_trigger_threshold = settings.get("volume_trigger_threshold", self.volume_trigger_threshold)
        trend_filter_period = settings.get("trend_filter_period", self.trend_filter_period)

        try:
            # Fetch H1 candles (100 limit is safe and sufficient)
            candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe='H1', limit=100)
            
            if not candles or len(candles) < max(max_lookback + volume_ma_period, trend_filter_period) + 5:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient historical candle data.",
                    tags=["insufficient_data"]
                )

            # Convert to DataFrame safely
            df = pd.DataFrame([{
                'high': float(c.high),
                'low': float(c.low),
                'close': float(c.close),
                'volume': float(c.volume)
            } for c in candles])

            # Calculate indicators
            df['vol_ma'] = df['volume'].rolling(window=volume_ma_period).mean()
            df['trend_ema'] = df['close'].ewm(span=trend_filter_period, adjust=False).mean()

            # Get latest completed candle index (-1) and previous index (-2)
            # We use index -2 to calculate the dynamic Donchian channel to avoid lookahead bias
            vol_ratio = df['volume'].iloc[-2] / df['vol_ma'].iloc[-2] if df['vol_ma'].iloc[-2] > 0 else 1.0
            
            # Dynamic lookback calculation: higher volume -> shorter lookback (faster breakout detection)
            dynamic_lookback = int(np.clip(base_lookback / vol_ratio, min_lookback, max_lookback))
            
            # Calculate Donchian Channel based on dynamic lookback
            # Lookback window ends at index -2 (inclusive)
            start_idx = max(0, len(df) - 2 - dynamic_lookback)
            end_idx = len(df) - 1 # exclusive of the current trigger candle at -1
            
            channel_high = df['high'].iloc[start_idx:end_idx].max()
            channel_low = df['low'].iloc[start_idx:end_idx].min()

            current_close = df['close'].iloc[-1]
            current_volume = df['volume'].iloc[-1]
            current_vol_ma = df['vol_ma'].iloc[-1]
            current_trend = df['trend_ema'].iloc[-1]

            # Signal conditions
            vol_expansion = current_volume > (current_vol_ma * volume_trigger_threshold)
            
            buy_trigger = (current_close > channel_high) and vol_expansion and (current_close > current_trend)
            sell_trigger = (current_close < channel_low) and vol_expansion and (current_close < current_trend)

            direction = None
            confidence = 0.0
            rationale = "No breakout detected or volume expansion insufficient."
            tags = ["neutral", "donchian_dynamic"]

            if buy_trigger:
                direction = "buy"
                confidence = float(np.clip(0.6 + (current_volume / current_vol_ma - volume_trigger_threshold) * 0.1, 0.6, 0.95))
                rationale = f"Bullish dynamic Donchian breakout above {channel_high:.5f} with volume expansion ratio {(current_volume/current_vol_ma):.2f}."
                tags = ["bullish", "breakout", "volume_expansion"]
            elif sell_trigger:
                direction = "sell"
                confidence = float(np.clip(0.6 + (current_volume / current_vol_ma - volume_trigger_threshold) * 0.1, 0.6, 0.95))
                rationale = f"Bearish dynamic Donchian breakout below {channel_low:.5f} with volume expansion ratio {(current_volume/current_vol_ma):.2f}."
                tags = ["bearish", "breakout", "volume_expansion"]

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
            logging.error(f"Error in strategy {self.strategy_id} evaluation: {str(e)}")
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Execution error: {str(e)}",
                tags=["error"]
            )