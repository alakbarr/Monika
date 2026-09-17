from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_audusd_3a4246(EdgeStrategy):
    strategy_id: str = "alpha_audusd_3a4246"
    applicable_symbols: set = {"AUDUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        # Define hyperparameters here
        self.h1_limit = 100
        self.m15_limit = 100
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
            # Fetch H1 and M15 candles
            h1_candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe='H1', limit=self.h1_limit)
            m15_candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe='M15', limit=self.m15_limit)
            
            if not h1_candles or not m15_candles:
                return EdgeSignal(strategy_id=self.strategy_id, symbol=symbol, direction=None, valid=False, confidence=0.0, rationale="Insufficient candle data", tags=["insufficient_data"])
            
            # Convert to DataFrames
            h1_df = pd.DataFrame([{
                'open': c.open,
                'high': c.high,
                'low': c.low,
                'close': c.close,
                'volume': getattr(c, 'volume', 0.0)
            } for c in h1_candles])
            
            m15_df = pd.DataFrame([{
                'open': c.open,
                'high': c.high,
                'low': c.low,
                'close': c.close,
                'volume': getattr(c, 'volume', 0.0)
            } for c in m15_candles])
            
            # Ensure numeric types
            for col in ['open', 'high', 'low', 'close', 'volume']:
                h1_df[col] = pd.to_numeric(h1_df[col], errors='coerce')
                m15_df[col] = pd.to_numeric(m15_df[col], errors='coerce')
            
            # Sanitize NaNs
            h1_df = h1_df.replace([np.inf, -np.inf], np.nan).ffill().bfill().fillna(0.0)
            m15_df = m15_df.replace([np.inf, -np.inf], np.nan).ffill().bfill().fillna(0.0)
            
            # Calculate ATR for H1
            h1_df['tr'] = np.maximum(
                h1_df['high'] - h1_df['low'],
                np.maximum(
                    abs(h1_df['high'] - h1_df['close'].shift(1)),
                    abs(h1_df['low'] - h1_df['close'].shift(1))
                )
            )
            h1_df['atr'] = h1_df['tr'].rolling(window=self.atr_period, min_periods=1).mean()
            
            # Calculate RSI for M15
            m15_df['delta'] = m15_df['close'].diff()
            m15_df['gain'] = np.where(m15_df['delta'] > 0, m15_df['delta'], 0)
            m15_df['loss'] = np.where(m15_df['delta'] < 0, -m15_df['delta'], 0)
            m15_df['avg_gain'] = m15_df['gain'].rolling(window=self.rsi_period, min_periods=1).mean()
            m15_df['avg_loss'] = m15_df['loss'].rolling(window=self.rsi_period, min_periods=1).mean()
            m15_df['rs'] = m15_df['avg_gain'] / (m15_df['avg_loss'] + 1e-10)
            m15_df['rsi'] = 100 - (100 / (1 + m15_df['rs']))
            
            # Calculate Volume MA for M15
            m15_df['vol_ma'] = m15_df['volume'].rolling(window=self.volume_ma_period, min_periods=1).mean()
            
            # Get latest values
            latest_h1 = h1_df.iloc[-1]
            latest_m15 = m15_df.iloc[-1]
            
            # Identify liquidity levels on H1 (recent highs/lows)
            recent_h1 = h1_df.iloc[-self.liquidity_lookback:]
            recent_highs = recent_h1['high'].values
            recent_lows = recent_h1['low'].values
            
            current_price = latest_m15['close']
            current_atr = latest_h1['atr']
            
            if current_atr <= 0:
                return EdgeSignal(strategy_id=self.strategy_id, symbol=symbol, direction=None, valid=False, confidence=0.0, rationale="Invalid ATR", tags=["invalid_atr"])
            
            # Check for liquidity sweep: price recently broke below recent lows or above recent highs
            # Then displaced back in the opposite direction with volume
            
            # For BUY signal:
            # 1. Price swept below recent H1 lows (liquidity grab)
            # 2. Price displaced back above the sweep level with strong M15 volume
            # 3. RSI is recovering from oversold
            
            sweep_low = np.min(recent_lows[:-1]) if len(recent_lows) > 1 else recent_lows[0]
            sweep_high = np.max(recent_highs[:-1]) if len(recent_highs) > 1 else recent_highs[0]
            
            # Check if recent M15 candles swept the level
            recent_m15 = m15_df.iloc[-5:]
            swept_low = recent_m15['low'].min() < sweep_low
            swept_high = recent_m15['high'].max() > sweep_high
            
            # Check displacement: current price is back above/below the sweep level
            displaced_up = current_price > sweep_low + (0.5 * current_atr)
            displaced_down = current_price < sweep_high - (0.5 * current_atr)
            
            # Check volume spike on displacement candle
            latest_volume = latest_m15['volume']
            vol_ma = latest_m15['vol_ma']
            volume_spike = vol_ma > 0 and latest_volume > (vol_ma * self.volume_spike_mult)
            
            # Check RSI conditions
            rsi_value = latest_m15['rsi']
            rsi_recovering_up = rsi_value > self.rsi_oversold and rsi_value < 50
            rsi_recovering_down = rsi_value < self.rsi_overbought and rsi_value > 50
            
            direction = None
            confidence = 0.0
            rationale = ""
            
            # BUY signal: swept low, displaced up, volume spike, RSI recovering
            if swept_low and displaced_up and volume_spike and rsi_recovering_up:
                direction = 'buy'
                confidence = 0.75
                rationale = f"Liquidity sweep below {sweep_low:.5f} with displacement to {current_price:.5f}, volume spike {latest_volume:.0f} vs MA {vol_ma:.0f}, RSI {rsi_value:.1f} recovering"
            
            # SELL signal: swept high, displaced down, volume spike, RSI recovering down
            elif swept_high and displaced_down and volume_spike and rsi_recovering_down:
                direction = 'sell'
                confidence = 0.75
                rationale = f"Liquidity sweep above {sweep_high:.5f} with displacement to {current_price:.5f}, volume spike {latest_volume:.0f} vs MA {vol_ma:.0f}, RSI {rsi_value:.1f} recovering down"
            
            if direction is None:
                return EdgeSignal(strategy_id=self.strategy_id, symbol=symbol, direction=None, valid=False, confidence=0.0, rationale="No liquidity sweep displacement pattern detected", tags=["no_signal"])
            
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=direction,
                valid=True,
                confidence=confidence,
                rationale=rationale,
                tags=["liquidity_sweep", "displacement", "multi_timeframe"]
            )
            
        except Exception as e:
            return EdgeSignal(strategy_id=self.strategy_id, symbol=symbol, direction=None, valid=False, confidence=0.0, rationale=f"Calculation error: {e}", tags=["error"])
