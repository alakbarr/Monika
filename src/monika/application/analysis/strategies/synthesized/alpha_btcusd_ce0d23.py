from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_btcusd_ce0d23(EdgeStrategy):
    strategy_id: str = "alpha_btcusd_ce0d23"
    applicable_symbols: set = {"BTCUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        # Define hyperparameters
        self.atr_period = 14
        self.exhaustion_threshold = 1.5  # ATR must be > 1.5x rolling mean ATR
        self.reversion_lookback = 20    # Lookback for mean reversion
        self.min_confidence = 0.6

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            # Fetch candle history
            candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe='H1', limit=100)
            
            if not candles or len(candles) < max(self.atr_period, self.reversion_lookback) + 5:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient historical data",
                    tags=['insufficient_data']
                )
            
            # Convert to DataFrame
            df = pd.DataFrame([
                {
                    'high': c.high,
                    'low': c.low,
                    'close': c.close,
                    'open': c.open
                } for c in candles
            ])
            
            # Calculate ATR
            high = df['high']
            low = df['low']
            close = df['close']
            
            # True Range
            prev_close = close.shift(1)
            tr1 = high - low
            tr2 = (high - prev_close).abs()
            tr3 = (low - prev_close).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            
            # ATR using Wilder's smoothing (EMA with alpha=1/period)
            atr = tr.ewm(alpha=1.0/self.atr_period, min_periods=self.atr_period).mean()
            
            # Rolling mean of ATR for exhaustion detection
            atr_mean = atr.rolling(window=self.reversion_lookback, min_periods=self.reversion_lookback).mean()
            
            # Check for ATR exhaustion: current ATR significantly higher than recent average
            if pd.isna(atr.iloc[-1]) or pd.isna(atr_mean.iloc[-1]) or atr_mean.iloc[-1] == 0:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="ATR calculation invalid",
                    tags=['calculation_error']
                )
            
            atr_ratio = atr.iloc[-1] / atr_mean.iloc[-1]
            
            # Mean reversion signal: price deviates from recent mean
            price_mean = close.rolling(window=self.reversion_lookback, min_periods=self.reversion_lookback).mean()
            price_std = close.rolling(window=self.reversion_lookback, min_periods=self.reversion_lookback).std()
            
            if pd.isna(price_mean.iloc[-1]) or pd.isna(price_std.iloc[-1]) or price_std.iloc[-1] == 0:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Price statistics invalid",
                    tags=['calculation_error']
                )
            
            # Z-score of current price
            z_score = (close.iloc[-1] - price_mean.iloc[-1]) / price_std.iloc[-1]
            
            # Signal logic:
            # 1. ATR exhaustion: atr_ratio > threshold (volatility spike)
            # 2. Mean reversion: price is extended (|z_score| > 1.5)
            # 3. Direction: buy if price is below mean (z_score < -1.5), sell if above (z_score > 1.5)
            
            atr_exhausted = atr_ratio > self.exhaustion_threshold
            price_extended = abs(z_score) > 1.5
            
            if atr_exhausted and price_extended:
                if z_score < 0:
                    direction = 'buy'
                    confidence = min(0.95, 0.6 + 0.1 * (atr_ratio - self.exhaustion_threshold) + 0.05 * abs(z_score))
                else:
                    direction = 'sell'
                    confidence = min(0.95, 0.6 + 0.1 * (atr_ratio - self.exhaustion_threshold) + 0.05 * abs(z_score))
                
                if confidence >= self.min_confidence:
                    rationale = f"ATR exhaustion (ratio={atr_ratio:.2f}) with mean reversion (z_score={z_score:.2f})"
                    return EdgeSignal(
                        strategy_id=self.strategy_id,
                        symbol=symbol,
                        direction=direction,
                        valid=True,
                        confidence=confidence,
                        rationale=rationale,
                        tags=['atr_exhaustion', 'mean_reversion']
                    )
                else:
                    return EdgeSignal(
                        strategy_id=self.strategy_id,
                        symbol=symbol,
                        direction=None,
                        valid=False,
                        confidence=confidence,
                        rationale=f"Signal confidence too low: {confidence:.2f}",
                        tags=['low_confidence']
                    )
            else:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale=f"No signal: atr_ratio={atr_ratio:.2f}, z_score={z_score:.2f}",
                    tags=['no_signal']
                )
                
        except Exception as e:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f'Calculation error: {e}',
                tags=['error']
            )