from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xtiusd_83031c(EdgeStrategy):
    strategy_id: str = "alpha_xtiusd_83031c"
    applicable_symbols: set = {"XTIUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.base_lookback = self.settings.get("base_lookback", 20)
        self.volume_ma_period = self.settings.get("volume_ma_period", 20)
        self.expansion_factor = self.settings.get("expansion_factor", 0.15)
        self.trend_filter_period = self.settings.get("trend_filter_period", 50)

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            # Fetch H1 candles (100 limit is sufficient for 50 EMA and 20 Donchian calculations)
            candles = await self.get_historical_candles(
                session=session, symbol=symbol, timeframe='H1', limit=100
            )
            
            if not candles or len(candles) < max(self.trend_filter_period, self.base_lookback) + 5:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient historical candle data.",
                    tags=["insufficient_data"]
                )

            # Parse candles safely supporting both object and dict access
            data = []
            for c in candles:
                try:
                    close = c.close
                    high = c.high
                    low = c.low
                    volume = c.volume
                    open_p = c.open
                except AttributeError:
                    close = c.get('close')
                    high = c.get('high')
                    low = c.get('low')
                    volume = c.get('volume', 1.0)
                    open_p = c.get('open')
                
                data.append({
                    'open': float(open_p) if open_p is not None else 0.0,
                    'high': float(high) if high is not None else 0.0,
                    'low': float(low) if low is not None else 0.0,
                    'close': float(close) if close is not None else 0.0,
                    'volume': float(volume) if volume is not None else 1.0
                })

            df = pd.DataFrame(data)

            # Calculate Volume Ratio (Current Volume / SMA of Volume)
            df['vol_sma'] = df['volume'].rolling(window=self.volume_ma_period).mean()
            df['vol_ratio'] = df['volume'] / df['vol_sma'].replace(0, 1.0)
            
            last_vol_ratio = df['vol_ratio'].iloc[-1]
            if pd.isna(last_vol_ratio):
                last_vol_ratio = 1.0
            
            # Dynamic Lookback based on volume intensity:
            # High volume -> shorter lookback (faster breakout detection)
            # Low volume -> longer lookback (filters noise)
            dynamic_lookback = int(np.clip(
                self.base_lookback * (2.0 - min(last_vol_ratio, 1.5)), 
                10, 
                40
            ))

            # Calculate Donchian Channels
            df['donchian_high'] = df['high'].shift(1).rolling(window=dynamic_lookback).max()
            df['donchian_low'] = df['low'].shift(1).rolling(window=dynamic_lookback).min()
            df['donchian_mid'] = (df['donchian_high'] + df['donchian_low']) / 2.0

            # Dynamic Expansion based on volume ratio
            # If volume is high, expand the channel to require a stronger breakout
            df['u_dynamic'] = df['donchian_mid'] + (df['donchian_high'] - df['donchian_mid']) * (
                1.0 + self.expansion_factor * (df['vol_ratio'] - 1.0).clip(lower=-0.5, upper=1.5)
            )
            df['l_dynamic'] = df['donchian_mid'] - (df['donchian_mid'] - df['donchian_low']) * (
                1.0 + self.expansion_factor * (df['vol_ratio'] - 1.0).clip(lower=-0.5, upper=1.5)
            )

            # Trend Filter (EMA 50)
            df['ema_trend'] = df['close'].ewm(span=self.trend_filter_period, adjust=False).mean()

            # ATR for volatility context
            df['tr'] = np.maximum(
                df['high'] - df['low'], 
                np.maximum(
                    abs(df['high'] - df['close'].shift(1)), 
                    abs(df['low'] - df['close'].shift(1))
                )
            )
            df['atr'] = df['tr'].rolling(window=14).mean()

            # Extract current and previous values
            close_curr = df['close'].iloc[-1]
            close_prev = df['close'].iloc[-2]
            u_dyn_curr = df['u_dynamic'].iloc[-1]
            u_dyn_prev = df['u_dynamic'].iloc[-2]
            l_dyn_curr = df['l_dynamic'].iloc[-1]
            l_dyn_prev = df['l_dynamic'].iloc[-2]
            ema_curr = df['ema_trend'].iloc[-1]
            vol_ratio_curr = df['vol_ratio'].iloc[-1]

            # Signal Logic
            direction = None
            confidence = 0.0
            rationale = "Price consolidating within volume-weighted dynamic Donchian bands."
            tags = ["consolidation"]

            # Check for Breakout
            if close_curr > u_dyn_curr and close_prev <= u_dyn_prev:
                if close_curr > ema_curr:
                    direction = 'buy'
                    confidence = float(np.clip(0.65 + 0.15 * (vol_ratio_curr - 1.0), 0.5, 0.95))
                    rationale = (
                        f"Bullish breakout above dynamic Donchian upper band ({u_dyn_curr:.2f}) "
                        f"with volume confirmation (ratio: {vol_ratio_curr:.2f}) and aligned with EMA trend."
                    )
                    tags = ["breakout", "bullish", "volume_expansion"]
                else:
                    direction = 'buy'
                    confidence = 0.55
                    rationale = (
                        f"Counter-trend bullish breakout above dynamic Donchian upper band ({u_dyn_curr:.2f}) "
                        f"with volume ratio {vol_ratio_curr:.2f}."
                    )
                    tags = ["breakout", "counter_trend"]

            elif close_curr < l_dyn_curr and close_prev >= l_dyn_prev:
                if close_curr < ema_curr:
                    direction = 'sell'
                    confidence = float(np.clip(0.65 + 0.15 * (vol_ratio_curr - 1.0), 0.5, 0.95))
                    rationale = (
                        f"Bearish breakout below dynamic Donchian lower band ({l_dyn_curr:.2f}) "
                        f"with volume confirmation (ratio: {vol_ratio_curr:.2f}) and aligned with EMA trend."
                    )
                    tags = ["breakout", "bearish", "volume_expansion"]
                else:
                    direction = 'sell'
                    confidence = 0.55
                    rationale = (
                        f"Counter-trend bearish breakout below dynamic Donchian lower band ({l_dyn_curr:.2f}) "
                        f"with volume ratio {vol_ratio_curr:.2f}."
                    )
                    tags = ["breakout", "counter_trend"]

            # Check for Mean Reversion if no breakout and volume is low
            if direction is None and vol_ratio_curr < 0.8:
                if close_prev < l_dyn_prev and close_curr >= l_dyn_curr:
                    direction = 'buy'
                    confidence = 0.60
                    rationale = (
                        f"Mean reversion buy signal: price recovered from dynamic lower band ({l_dyn_curr:.2f}) "
                        f"on low volume (ratio: {vol_ratio_curr:.2f})."
                    )
                    tags = ["mean_reversion", "bullish"]
                elif close_prev > u_dyn_prev and close_curr <= u_dyn_curr:
                    direction = 'sell'
                    confidence = 0.60
                    rationale = (
                        f"Mean reversion sell signal: price rejected from dynamic upper band ({u_dyn_curr:.2f}) "
                        f"on low volume (ratio: {vol_ratio_curr:.2f})."
                    )
                    tags = ["mean_reversion", "bearish"]

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
                rationale=f"Error executing strategy: {str(e)}",
                tags=["error"]
            )