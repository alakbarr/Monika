from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xtiusd_1793d0(EdgeStrategy):
    strategy_id: str = "alpha_xtiusd_1793d0"
    applicable_symbols: set = {"XTIUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.h1_swing_window: int = int(self.settings.get("h1_swing_window", 10))
        self.m15_lookback: int = int(self.settings.get("m15_lookback", 16))
        self.atr_period: int = int(self.settings.get("atr_period", 14))
        self.displacement_body_min: float = float(self.settings.get("displacement_body_min", 0.60))
        self.min_displacement_atr_mult: float = float(self.settings.get("min_displacement_atr_mult", 1.1))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            if symbol not in self.applicable_symbols:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale=f"Symbol {symbol} is not supported by {self.strategy_id}",
                    tags=["unsupported_symbol"]
                )

            # Retrieve Multi-Timeframe Candle Data (H1 for macro key levels, M15 for execution structure)
            h1_candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe='H1', limit=120)
            m15_candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe='M15', limit=120)

            if not h1_candles or len(h1_candles) < 30 or not m15_candles or len(m15_candles) < 40:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient MTF candle history for liquidity sweep analysis",
                    tags=["insufficient_data"]
                )

            # Convert H1 Candles to DataFrame
            h1_data = []
            for c in h1_candles:
                h1_data.append({
                    'open': float(c.open if hasattr(c, 'open') else c['open']),
                    'high': float(c.high if hasattr(c, 'high') else c['high']),
                    'low': float(c.low if hasattr(c, 'low') else c['low']),
                    'close': float(c.close if hasattr(c, 'close') else c['close']),
                    'volume': float(c.volume if hasattr(c, 'volume') else c.get('volume', 0.0))
                })
            df_h1 = pd.DataFrame(h1_data)

            # Convert M15 Candles to DataFrame
            m15_data = []
            for c in m15_candles:
                m15_data.append({
                    'open': float(c.open if hasattr(c, 'open') else c['open']),
                    'high': float(c.high if hasattr(c, 'high') else c['high']),
                    'low': float(c.low if hasattr(c, 'low') else c['low']),
                    'close': float(c.close if hasattr(c, 'close') else c['close']),
                    'volume': float(c.volume if hasattr(c, 'volume') else c.get('volume', 0.0))
                })
            df_m15 = pd.DataFrame(m15_data)

            # Identify H1 Swing Highs and Swing Lows (ignoring current incomplete/latest bar)
            h1_window = max(3, self.h1_swing_window)
            df_h1_prev = df_h1.iloc[:-1].copy()

            swing_highs = []
            swing_lows = []
            for i in range(h1_window, len(df_h1_prev) - h1_window):
                window_high = df_h1_prev['high'].iloc[i - h1_window:i + h1_window + 1].max()
                window_low = df_h1_prev['low'].iloc[i - h1_window:i + h1_window + 1].min()

                if df_h1_prev['high'].iloc[i] == window_high:
                    swing_highs.append(df_h1_prev['high'].iloc[i])
                if df_h1_prev['low'].iloc[i] == window_low:
                    swing_lows.append(df_h1_prev['low'].iloc[i])

            if not swing_highs or not swing_lows:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="No distinct H1 swing liquidity pools identified",
                    tags=["no_swing_levels"]
                )

            key_resistance = max(swing_highs[-3:])
            key_support = min(swing_lows[-3:])

            # Calculate M15 ATR for volatility benchmarking
            df_m15['tr'] = np.maximum(
                df_m15['high'] - df_m15['low'],
                np.maximum(
                    np.abs(df_m15['high'] - df_m15['close'].shift(1)),
                    np.abs(df_m15['low'] - df_m15['close'].shift(1))
                )
            ).bfill().fillna(0.0)
            df_m15['atr'] = df_m15['tr'].rolling(window=self.atr_period, min_periods=1).mean().bfill().fillna(0.0)

            # Analyze latest M15 action
            curr = df_m15.iloc[-1]
            prev = df_m15.iloc[-2]
            lookback_m15 = df_m15.iloc[-self.m15_lookback:]

            curr_range = max(curr['high'] - curr['low'], 1e-6)
            curr_body = abs(curr['close'] - curr['open'])
            curr_body_ratio = curr_body / curr_range
            curr_atr = curr['atr'] if curr['atr'] > 0 else curr_range

            # Bullish Liquidity Sweep & Displacement Detection
            # Condition 1: Price swept below key H1 support level within recent M15 bars
            recent_low = lookback_m15['low'].min()
            swept_low = recent_low < key_support

            # Condition 2: Strong bullish displacement candle
            bullish_displacement = (
                swept_low
                and curr['close'] > curr['open']
                and curr['close'] > key_support
                and curr_body_ratio >= self.displacement_body_min
                and curr_range >= (self.min_displacement_atr_mult * curr_atr)
                and curr['close'] > prev['high']
            )

            # Bearish Liquidity Sweep & Displacement Detection
            # Condition 1: Price swept above key H1 resistance level within recent M15 bars
            recent_high = lookback_m15['high'].max()
            swept_high = recent_high > key_resistance

            # Condition 2: Strong bearish displacement candle
            bearish_displacement = (
                swept_high
                and curr['close'] < curr['open']
                and curr['close'] < key_resistance
                and curr_body_ratio >= self.displacement_body_min
                and curr_range >= (self.min_displacement_atr_mult * curr_atr)
                and curr['close'] < prev['low']
            )

            # Directional Resolution and Confidence Scoring
            if bullish_displacement and not bearish_displacement:
                sweep_magnitude = (key_support - recent_low) / curr_atr
                confidence_score = min(0.92, 0.65 + (sweep_magnitude * 0.1) + (curr_body_ratio * 0.15))
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction='buy',
                    valid=True,
                    confidence=round(confidence_score, 4),
                    rationale=(
                        f"Bullish liquidity sweep below H1 support {key_support:.2f} (Low: {recent_low:.2f}) "
                        f"with strong M15 displacement back above level. Body ratio: {curr_body_ratio:.2f}, "
                        f"ATR Multiple: {(curr_range / curr_atr):.2f}"
                    ),
                    tags=["liquidity_sweep", "bullish_displacement", "mtf_structure", "xtiusd"]
                )

            elif bearish_displacement and not bullish_displacement:
                sweep_magnitude = (recent_high - key_resistance) / curr_atr
                confidence_score = min(0.92, 0.65 + (sweep_magnitude * 0.1) + (curr_body_ratio * 0.15))
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction='sell',
                    valid=True,
                    confidence=round(confidence_score, 4),
                    rationale=(
                        f"Bearish liquidity sweep above H1 resistance {key_resistance:.2f} (High: {recent_high:.2f}) "
                        f"with strong M15 displacement back below level. Body ratio: {curr_body_ratio:.2f}, "
                        f"ATR Multiple: {(curr_range / curr_atr):.2f}"
                    ),
                    tags=["liquidity_sweep", "bearish_displacement", "mtf_structure", "xtiusd"]
                )

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale="No MTF liquidity sweep and displacement pattern detected",
                tags=["neutral"]
            )
        except Exception as e:
            return EdgeSignal(strategy_id=getattr(self, 'strategy_id', 'unknown'), symbol=getattr(self, 'symbol', 'unknown'), direction=None, valid=False, confidence=0.0, rationale=f'Calculation error: {e}', tags=['error'])

