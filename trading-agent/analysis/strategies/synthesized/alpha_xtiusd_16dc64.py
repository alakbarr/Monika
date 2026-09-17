from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xtiusd_16dc64(EdgeStrategy):
    strategy_id: str = "alpha_xtiusd_16dc64"
    applicable_symbols: set = {"XTIUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        # Define hyperparameters here
        self.h1_limit = 200
        self.h4_limit = 100
        self.liquidity_lookback = 20
        self.displacement_atr_mult = 1.5
        self.atr_period = 14
        self.rsi_period = 14
        self.rsi_oversold = 30.0
        self.rsi_overbought = 70.0
        self.volume_ma_period = 20
        self.volume_spike_mult = 1.5

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            # Fetch H1 and H4 candles
            h1_candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe='H1', limit=self.h1_limit)
            h4_candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe='H4', limit=self.h4_limit)
            
            if not h1_candles or not h4_candles:
                return EdgeSignal(strategy_id=self.strategy_id, symbol=symbol, direction=None, valid=False, confidence=0.0, rationale="Insufficient candle data", tags=["insufficient_data"])
            
            # Convert to DataFrames
            h1_df = pd.DataFrame([{
                'open': c.open,
                'high': c.high,
                'low': c.low,
                'close': c.close,
                'volume': c.volume if hasattr(c, 'volume') else 0.0,
                'timestamp': c.timestamp if hasattr(c, 'timestamp') else None
            } for c in h1_candles])
            
            h4_df = pd.DataFrame([{
                'open': c.open,
                'high': c.high,
                'low': c.low,
                'close': c.close,
                'volume': c.volume if hasattr(c, 'volume') else 0.0,
                'timestamp': c.timestamp if hasattr(c, 'timestamp') else None
            } for c in h4_candles])
            
            # Ensure numeric types
            for col in ['open', 'high', 'low', 'close', 'volume']:
                h1_df[col] = pd.to_numeric(h1_df[col], errors='coerce')
                h4_df[col] = pd.to_numeric(h4_df[col], errors='coerce')
            
            # Sanitize NaNs
            h1_df = h1_df.replace([np.inf, -np.inf], np.nan).ffill().bfill()
            h4_df = h4_df.replace([np.inf, -np.inf], np.nan).ffill().bfill()
            
            # Calculate ATR for H1
            h1_df['tr'] = np.maximum(
                h1_df['high'] - h1_df['low'],
                np.maximum(
                    abs(h1_df['high'] - h1_df['close'].shift(1)),
                    abs(h1_df['low'] - h1_df['close'].shift(1))
                )
            )
            h1_df['atr'] = h1_df['tr'].rolling(window=self.atr_period, min_periods=1).mean()
            
            # Calculate RSI for H1
            delta = h1_df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period, min_periods=1).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period, min_periods=1).mean()
            rs = gain / loss.replace(0, np.nan)
            h1_df['rsi'] = 100 - (100 / (1 + rs))
            h1_df['rsi'] = h1_df['rsi'].fillna(50.0)
            
            # Calculate Volume MA for H1
            h1_df['vol_ma'] = h1_df['volume'].rolling(window=self.volume_ma_period, min_periods=1).mean()
            
            # Identify liquidity pools (recent highs/lows)
            recent_h1 = h1_df.tail(self.liquidity_lookback)
            liquidity_high = recent_h1['high'].max()
            liquidity_low = recent_h1['low'].min()
            
            # Check for liquidity sweep on H1
            last_h1 = h1_df.iloc[-1]
            prev_h1 = h1_df.iloc[-2] if len(h1_df) > 1 else last_h1
            
            # Sweep high: price wicks above recent high but closes below
            sweep_high = (last_h1['high'] > liquidity_high) and (last_h1['close'] < liquidity_high)
            # Sweep low: price wicks below recent low but closes above
            sweep_low = (last_h1['low'] < liquidity_low) and (last_h1['close'] > liquidity_low)
            
            # Check for displacement (strong move with volume)
            displacement = abs(last_h1['close'] - last_h1['open']) > (self.displacement_atr_mult * last_h1['atr'])
            volume_spike = last_h1['volume'] > (self.volume_spike_mult * last_h1['vol_ma'])
            
            # H4 Trend Confirmation
            h4_trend_up = h4_df['close'].iloc[-1] > h4_df['close'].iloc[-5] if len(h4_df) >= 5 else False
            h4_trend_down = h4_df['close'].iloc[-1] < h4_df['close'].iloc[-5] if len(h4_df) >= 5 else False
            
            # Signal Logic
            direction = None
            confidence = 0.0
            rationale = ""
            tags = []
            
            # Bullish Setup: Sweep Low + Displacement Up + Volume Spike + H4 Trend Up + RSI not overbought
            if sweep_low and displacement and volume_spike and h4_trend_up and last_h1['rsi'] < self.rsi_overbought:
                direction = 'buy'
                confidence = 0.75
                rationale = "Bullish liquidity sweep of recent lows with displacement and volume confirmation, aligned with H4 uptrend"
                tags = ["liquidity_sweep", "displacement", "volume_spike", "h4_trend_aligned"]
            
            # Bearish Setup: Sweep High + Displacement Down + Volume Spike + H4 Trend Down + RSI not oversold
            elif sweep_high and displacement and volume_spike and h4_trend_down and last_h1['rsi'] > self.rsi_oversold:
                direction = 'sell'
                confidence = 0.75
                rationale = "Bearish liquidity sweep of recent highs with displacement and volume confirmation, aligned with H4 downtrend"
                tags = ["liquidity_sweep", "displacement", "volume_spike", "h4_trend_aligned"]
            
            # Partial Confidence: Sweep + Displacement but missing volume or trend
            elif (sweep_low or sweep_high) and displacement:
                if sweep_low and h4_trend_up:
                    direction = 'buy'
                    confidence = 0.55
                    rationale = "Bullish liquidity sweep with displacement, volume spike missing"
                    tags = ["liquidity_sweep", "displacement", "partial_confirmation"]
                elif sweep_high and h4_trend_down:
                    direction = 'sell'
                    confidence = 0.55
                    rationale = "Bearish liquidity sweep with displacement, volume spike missing"
                    tags = ["liquidity_sweep", "displacement", "partial_confirmation"]
            
            if direction is None:
                return EdgeSignal(strategy_id=self.strategy_id, symbol=symbol, direction=None, valid=False, confidence=0.0, rationale="No valid liquidity sweep displacement setup detected", tags=["no_signal"])
            
            return EdgeSignal(strategy_id=self.strategy_id, symbol=symbol, direction=direction, valid=True, confidence=confidence, rationale=rationale, tags=tags)
            
        except Exception as e:
            return EdgeSignal(strategy_id=self.strategy_id, symbol=symbol, direction=None, valid=False, confidence=0.0, rationale=f"Calculation error: {e}", tags=["error"])
