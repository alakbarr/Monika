from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_gbpusd_9f0652(EdgeStrategy):
    strategy_id: str = "alpha_gbpusd_9f0652"
    applicable_symbols: set = {"GBPUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.base_lookback = self.settings.get("base_lookback", 20)
        self.min_lookback = self.settings.get("min_lookback", 10)
        self.max_lookback = self.settings.get("max_lookback", 40)
        self.volume_ma_period = self.settings.get("volume_ma_period", 20)
        self.trend_ema_period = self.settings.get("trend_ema_period", 100)
        self.volume_expansion_threshold = self.settings.get("volume_expansion_threshold", 1.2)
        self.timeframe = self.settings.get("timeframe", "H1")

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            local_settings = {**self.settings, **settings}
            timeframe = local_settings.get("timeframe", self.timeframe)
            
            # Fetch historical candles
            candles = await self.get_historical_candles(
                session=session, 
                symbol=symbol, 
                timeframe=timeframe, 
                limit=150
            )
            
            if not candles or len(candles) < 110:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale=f"Insufficient candle history. Required: 110, Got: {len(candles) if candles else 0}",
                    tags=["insufficient_data"]
                )

            # Convert to DataFrame safely
            df_data = []
            for c in candles:
                df_data.append({
                    'open': float(c.open if hasattr(c, 'open') else c['open']),
                    'high': float(c.high if hasattr(c, 'high') else c['high']),
                    'low': float(c.low if hasattr(c, 'low') else c['low']),
                    'close': float(c.close if hasattr(c, 'close') else c['close']),
                    'volume': float(c.volume if hasattr(c, 'volume') else c['volume']),
                })
            df = pd.DataFrame(df_data)

            # Sanitize inputs
            df = df.ffill().bfill().fillna(0.0)

            # Calculate Volume EMA
            vol_ma_period = int(local_settings.get("volume_ma_period", self.volume_ma_period))
            df['vol_ema'] = df['volume'].ewm(span=vol_ma_period, adjust=False).mean()
            df['vol_ema'] = df['vol_ema'].replace(0.0, 1e-8)  # Avoid division by zero
            df['vol_ratio'] = df['volume'] / df['vol_ema']
            df['vol_ratio'] = df['vol_ratio'].ffill().bfill().fillna(1.0)

            # Calculate Trend EMA
            trend_ema_period = int(local_settings.get("trend_ema_period", self.trend_ema_period))
            df['trend_ema'] = df['close'].ewm(span=trend_ema_period, adjust=False).mean()

            # Calculate ATR for volatility context
            high_low = df['high'] - df['low']
            high_cp = (df['high'] - df['close'].shift(1)).abs()
            low_cp = (df['low'] - df['close'].shift(1)).abs()
            tr = pd.concat([high_low, high_cp, low_cp], axis=1).max(axis=1)
            df['atr'] = tr.rolling(window=14, min_periods=1).mean().ffill().bfill().fillna(0.0)

            # Dynamic Donchian Channel calculation for the last few bars
            upper_bands = []
            lower_bands = []
            
            base_lookback = int(local_settings.get("base_lookback", self.base_lookback))
            min_lookback = int(local_settings.get("min_lookback", self.min_lookback))
            max_lookback = int(local_settings.get("max_lookback", self.max_lookback))

            eval_range = 5
            for idx in range(len(df) - eval_range, len(df)):
                vol_ratio = df['vol_ratio'].iloc[idx]
                # Dynamic lookback: higher volume -> smaller lookback (faster breakout detection)
                lookback = int(np.clip(round(base_lookback / vol_ratio), min_lookback, max_lookback))
                
                # Donchian channel is calculated on the prior 'lookback' bars (excluding current bar)
                start_idx = max(0, idx - lookback)
                if start_idx < idx:
                    upper_bands.append(df['high'].iloc[start_idx:idx].max())
                    lower_bands.append(df['low'].iloc[start_idx:idx].min())
                else:
                    upper_bands.append(df['high'].iloc[idx])
                    lower_bands.append(df['low'].iloc[idx])

            # Map bands to variables
            close_curr = df['close'].iloc[-1]
            close_prev = df['close'].iloc[-2]
            
            upper_curr = upper_bands[-1]
            lower_curr = lower_bands[-1]
            
            upper_prev = upper_bands[-2]
            lower_prev = lower_bands[-2]

            vol_ratio_curr = df['vol_ratio'].iloc[-1]
            trend_curr = df['trend_ema'].iloc[-1]
            vol_threshold = float(local_settings.get("volume_expansion_threshold", self.volume_expansion_threshold))

            # Signal Logic
            direction = None
            confidence = 0.0
            reasons = []

            # Condition 1: Breakout of dynamic Donchian Channel
            bullish_breakout = (close_curr > upper_curr) and (close_prev <= upper_prev)
            bearish_breakout = (close_curr < lower_curr) and (close_prev >= lower_prev)

            # Condition 2: Volume Expansion Confirmation
            volume_confirmed = vol_ratio_curr >= vol_threshold

            # Condition 3: Trend Filter
            trend_bullish = close_curr > trend_curr
            trend_bearish = close_curr < trend_curr

            if bullish_breakout and volume_confirmed and trend_bullish:
                direction = "buy"
                vol_factor = min(vol_ratio_curr / vol_threshold, 2.0)
                confidence = float(np.clip(0.6 + (vol_factor - 1.0) * 0.2, 0.6, 0.95))
                reasons.append(f"Bullish dynamic Donchian breakout above {upper_curr:.5f}.")
                reasons.append(f"Volume confirmed with ratio {vol_ratio_curr:.2f}x.")
                reasons.append(f"Price above Trend EMA ({trend_curr:.5f}).")

            elif bearish_breakout and volume_confirmed and trend_bearish:
                direction = "sell"
                vol_factor = min(vol_ratio_curr / vol_threshold, 2.0)
                confidence = float(np.clip(0.6 + (vol_factor - 1.0) * 0.2, 0.6, 0.95))
                reasons.append(f"Bearish dynamic Donchian breakout below {lower_curr:.5f}.")
                reasons.append(f"Volume confirmed with ratio {vol_ratio_curr:.2f}x.")
                reasons.append(f"Price below Trend EMA ({trend_curr:.5f}).")

            else:
                direction = None
                confidence = 0.0
                reasons.append("No dynamic Donchian breakout with volume confirmation detected.")

            rationale = " | ".join(reasons)
            tags = ["volume_weighted", "donchian_expansion", "gbpusd_h1"]
            if direction:
                tags.append("breakout")

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
                rationale=f"Calculation error: {str(e)}",
                tags=["error"]
            )