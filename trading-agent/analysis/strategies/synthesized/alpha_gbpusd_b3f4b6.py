from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_gbpusd_b3f4b6(EdgeStrategy):
    strategy_id: str = "alpha_gbpusd_b3f4b6"
    applicable_symbols: set = {"GBPUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.htf_lookback: int = int(self.settings.get("htf_lookback", 40))
        self.ltf_lookback: int = int(self.settings.get("ltf_lookback", 50))
        self.displacement_multiplier: float = float(self.settings.get("displacement_multiplier", 1.4))
        self.min_body_ratio: float = float(self.settings.get("min_body_ratio", 0.60))
        self.atr_period: int = int(self.settings.get("atr_period", 14))

    def _extract_ohlc(self, candles: List[Any]) -> Optional[pd.DataFrame]:
        if not candles or len(candles) < 20:
            return None
        data = []
        for c in candles:
            try:
                open_val = float(c.open if hasattr(c, 'open') else c['open'])
                high_val = float(c.high if hasattr(c, 'high') else c['high'])
                low_val = float(c.low if hasattr(c, 'low') else c['low'])
                close_val = float(c.close if hasattr(c, 'close') else c['close'])
                vol_val = float(c.volume if hasattr(c, 'volume') else c.get('volume', 0.0))
                data.append({
                    'open': open_val,
                    'high': high_val,
                    'low': low_val,
                    'close': close_val,
                    'volume': vol_val
                })
            except Exception:
                continue
        if len(data) < 20:
            return None
        return pd.DataFrame(data)

    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        high = df['high']
        low = df['low']
        close_prev = df['close'].shift(1)
        tr1 = high - low
        tr2 = (high - close_prev).abs()
        tr3 = (low - close_prev).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(window=period, min_periods=period).mean()

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        if symbol not in self.applicable_symbols:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale="Symbol not applicable for GBPUSD Liquidity Sweep Displacement strategy.",
                tags=["gbpusd", "liquidity_sweep", "ineligible_symbol"]
            )

        # Retrieve HTF (H4) and LTF (H1) candles
        candles_h4 = await self.get_historical_candles(session=session, symbol=symbol, timeframe='H4', limit=self.htf_lookback + 10)
        candles_h1 = await self.get_historical_candles(session=session, symbol=symbol, timeframe='H1', limit=self.ltf_lookback + 10)

        df_h4 = self._extract_ohlc(candles_h4)
        df_h1 = self._extract_ohlc(candles_h1)

        if df_h4 is None or df_h1 is None:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale="Insufficient historical candle data for multi-timeframe evaluation.",
                tags=["gbpusd", "insufficient_data"]
            )

        # 1. Identify HTF Swing Highs & Lows (Fractal-based liquidity pools)
        h4_highs = df_h4['high'].values
        h4_lows = df_h4['low'].values
        h4_closes = df_h4['close'].values
        
        # Calculate recent key HTF liquidity levels excluding the immediate last 2 completed bars
        swing_high_pool = np.max(h4_highs[-25:-2])
        swing_low_pool = np.min(h4_lows[-25:-2])

        # Check for HTF Liquidity Sweep in the last 2 H4 bars
        recent_h4_max_high = np.max(h4_highs[-3:])
        recent_h4_min_low = np.min(h4_lows[-3:])
        latest_h4_close = h4_closes[-1]

        bearish_sweep = (recent_h4_max_high > swing_high_pool) and (latest_h4_close < swing_high_pool)
        bullish_sweep = (recent_h4_min_low < swing_low_pool) and (latest_h4_close > swing_low_pool)

        # 2. LTF (H1) Displacement & Market Structure Shift Analysis
        df_h1['atr'] = self._calculate_atr(df_h1, self.atr_period)
        h1_atr = df_h1['atr'].iloc[-1]
        
        if pd.isna(h1_atr) or h1_atr <= 0:
            h1_atr = (df_h1['high'].iloc[-14:] - df_h1['low'].iloc[-14:]).mean()
            if h1_atr <= 0:
                h1_atr = 0.0010

        last_h1 = df_h1.iloc[-1]
        prev_h1 = df_h1.iloc[-2]
        
        h1_candle_range = last_h1['high'] - last_h1['low']
        h1_body_size = abs(last_h1['close'] - last_h1['open'])
        body_ratio = h1_body_size / (h1_candle_range + 1e-9)

        is_displacement = (h1_candle_range >= self.displacement_multiplier * h1_atr) and (body_ratio >= self.min_body_ratio)

        # Determine directional triggers
        h1_recent_swing_low = df_h1['low'].iloc[-10:-2].min()
        h1_recent_swing_high = df_h1['high'].iloc[-10:-2].max()

        direction = None
        confidence = 0.0
        rationale_items: List[str] = []

        if bearish_sweep:
            # Check for bearish displacement closing below previous low (MSS)
            is_bearish_displacement = is_displacement and (last_h1['close'] < last_h1['open'])
            mss_confirmed = last_h1['close'] < h1_recent_swing_low or last_h1['close'] < prev_h1['low']
            
            if is_bearish_displacement and mss_confirmed:
                direction = "sell"
                sweep_magnitude = (recent_h4_max_high - swing_high_pool) / h1_atr
                displacement_strength = h1_candle_range / h1_atr
                confidence = min(0.92, 0.65 + 0.10 * min(sweep_magnitude, 1.5) + 0.08 * min(displacement_strength / 2.0, 1.0))
                rationale_items.append(f"H4 buy-side liquidity swept at {swing_high_pool:.5f} (Peak: {recent_h4_max_high:.5f}).")
                rationale_items.append(f"H1 bearish displacement confirmed (Range: {h1_candle_range*10000:.1f} pips, Body: {body_ratio*100:.1f}%).")
                rationale_items.append("Market structure shift lower with aggressive order flow imbalance.")

        elif bullish_sweep:
            # Check for bullish displacement closing above previous high (MSS)
            is_bullish_displacement = is_displacement and (last_h1['close'] > last_h1['open'])
            mss_confirmed = last_h1['close'] > h1_recent_swing_high or last_h1['close'] > prev_h1['high']
            
            if is_bullish_displacement and mss_confirmed:
                direction = "buy"
                sweep_magnitude = (swing_low_pool - recent_h4_min_low) / h1_atr
                displacement_strength = h1_candle_range / h1_atr
                confidence = min(0.92, 0.65 + 0.10 * min(sweep_magnitude, 1.5) + 0.08 * min(displacement_strength / 2.0, 1.0))
                rationale_items.append(f"H4 sell-side liquidity swept at {swing_low_pool:.5f} (Trough: {recent_h4_min_low:.5f}).")
                rationale_items.append(f"H1 bullish displacement confirmed (Range: {h1_candle_range*10000:.1f} pips, Body: {body_ratio*100:.1f}%).")
                rationale_items.append("Market structure shift higher with aggressive order flow imbalance.")

        valid = direction is not None and confidence >= 0.65
        rationale = " | ".join(rationale_items) if valid else "No liquidity sweep displacement pattern matched on H4/H1 timeframes."
        tags = ["gbpusd", "multi_timeframe", "liquidity_sweep", "displacement"]
        if valid:
            tags.append(f"setup_{direction}")

        return EdgeSignal(
            strategy_id=self.strategy_id,
            symbol=symbol,
            direction=direction,
            valid=valid,
            confidence=round(confidence, 4),
            rationale=rationale,
            tags=tags
        )