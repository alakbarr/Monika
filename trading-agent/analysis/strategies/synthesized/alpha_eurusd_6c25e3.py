from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_eurusd_6c25e3(EdgeStrategy):
    strategy_id: str = "alpha_eurusd_6c25e3"
    applicable_symbols: set = {"EURUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.htf_window = self.settings.get("htf_window", 24)
        self.ltf_window = self.settings.get("ltf_window", 20)
        self.displacement_multiplier = self.settings.get("displacement_multiplier", 1.5)
        self.sweep_lookback = self.settings.get("sweep_lookback", 10)

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            # Fetch HTF (H1) and LTF (M15) candles
            htf_candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe='H1', limit=100)
            ltf_candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe='M15', limit=100)

            if not htf_candles or len(htf_candles) < 30 or not ltf_candles or len(ltf_candles) < 30:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient candle history for HTF or LTF.",
                    tags=["insufficient_data"]
                )

            # Helper to convert candles to DataFrame safely
            def to_df(candles):
                data = []
                for c in candles:
                    high = getattr(c, 'high', None) if not isinstance(c, dict) else c.get('high')
                    low = getattr(c, 'low', None) if not isinstance(c, dict) else c.get('low')
                    close = getattr(c, 'close', None) if not isinstance(c, dict) else c.get('close')
                    open_val = getattr(c, 'open', None) if not isinstance(c, dict) else c.get('open')
                    volume = getattr(c, 'volume', None) if not isinstance(c, dict) else c.get('volume')
                    
                    data.append({
                        'high': float(high) if high is not None else 0.0,
                        'low': float(low) if low is not None else 0.0,
                        'close': float(close) if close is not None else 0.0,
                        'open': float(open_val) if open_val is not None else 0.0,
                        'volume': float(volume) if volume is not None else 0.0
                    })
                df = pd.DataFrame(data)
                df = df.ffill().bfill()
                return df

            df_h1 = to_df(htf_candles)
            df_m15 = to_df(ltf_candles)

            # Calculate HTF levels (Swing Highs/Lows over htf_window, shifted to avoid lookahead)
            df_h1['htf_high'] = df_h1['high'].shift(1).rolling(window=self.htf_window, min_periods=12).max()
            df_h1['htf_low'] = df_h1['low'].shift(1).rolling(window=self.htf_window, min_periods=12).min()
            
            df_h1 = df_h1.ffill().bfill()
            
            latest_htf_high = float(df_h1['htf_high'].iloc[-1])
            latest_htf_low = float(df_h1['htf_low'].iloc[-1])

            if math.isnan(latest_htf_high) or math.isnan(latest_htf_low) or latest_htf_high == 0 or latest_htf_low == 0:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Invalid HTF levels calculated.",
                    tags=["invalid_htf_levels"]
                )

            # Calculate LTF metrics
            df_m15['body'] = (df_m15['close'] - df_m15['open']).abs()
            df_m15['avg_body'] = df_m15['body'].rolling(window=self.ltf_window, min_periods=10).mean()
            df_m15['avg_volume'] = df_m15['volume'].rolling(window=self.ltf_window, min_periods=10).mean()
            
            df_m15 = df_m15.ffill().bfill()

            # Scan the last `sweep_lookback` candles for a sweep and subsequent displacement
            direction = None
            confidence = 0.0
            rationale = "No liquidity sweep displacement pattern detected."
            tags = ["neutral"]

            n = len(df_m15)
            start_idx = max(0, n - self.sweep_lookback)

            best_bullish_signal = False
            best_bearish_signal = False
            bullish_conf = 0.0
            bearish_conf = 0.0
            bullish_rationale = ""
            bearish_rationale = ""

            for i in range(start_idx, n - 1):
                low_i = df_m15['low'].iloc[i]
                high_i = df_m15['high'].iloc[i]
                close_i = df_m15['close'].iloc[i]
                
                # 1. Check for Bullish Sweep at index i
                is_bullish_sweep = (low_i < latest_htf_low) and (close_i > low_i + 0.2 * (high_i - low_i))
                
                if is_bullish_sweep:
                    for j in range(i, n):
                        close_j = df_m15['close'].iloc[j]
                        open_j = df_m15['open'].iloc[j]
                        body_j = close_j - open_j
                        avg_body_j = max(df_m15['avg_body'].iloc[j], 0.0001)
                        volume_j = df_m15['volume'].iloc[j]
                        avg_volume_j = df_m15['avg_volume'].iloc[j]

                        is_displacement = (body_j > self.displacement_multiplier * avg_body_j) and (close_j > high_i)
                        
                        if is_displacement:
                            vol_factor = min(2.0, volume_j / max(avg_volume_j, 1.0)) if avg_volume_j > 0 else 1.0
                            body_factor = min(2.0, body_j / avg_body_j)
                            temp_conf = 0.5 + 0.2 * (body_factor - 1.0) + 0.15 * (vol_factor - 1.0)
                            temp_conf = max(0.5, min(0.95, temp_conf))
                            
                            if temp_conf > bullish_conf:
                                bullish_conf = temp_conf
                                best_bullish_signal = True
                                bullish_rationale = (
                                    f"Bullish liquidity sweep of HTF Low ({latest_htf_low:.5f}) at M15 index {i} "
                                    f"followed by strong displacement at index {j} (body: {body_j:.5f} vs avg: {avg_body_j:.5f})."
                                )

                # 2. Check for Bearish Sweep at index i
                is_bearish_sweep = (high_i > latest_htf_high) and (close_i < high_i - 0.2 * (high_i - low_i))
                
                if is_bearish_sweep:
                    for j in range(i, n):
                        close_j = df_m15['close'].iloc[j]
                        open_j = df_m15['open'].iloc[j]
                        body_j = open_j - close_j
                        avg_body_j = max(df_m15['avg_body'].iloc[j], 0.0001)
                        volume_j = df_m15['volume'].iloc[j]
                        avg_volume_j = df_m15['avg_volume'].iloc[j]

                        is_displacement = (body_j > self.displacement_multiplier * avg_body_j) and (close_j < low_i)
                        
                        if is_displacement:
                            vol_factor = min(2.0, volume_j / max(avg_volume_j, 1.0)) if avg_volume_j > 0 else 1.0
                            body_factor = min(2.0, body_j / avg_body_j)
                            temp_conf = 0.5 + 0.2 * (body_factor - 1.0) + 0.15 * (vol_factor - 1.0)
                            temp_conf = max(0.5, min(0.95, temp_conf))
                            
                            if temp_conf > bearish_conf:
                                bearish_conf = temp_conf
                                best_bearish_signal = True
                                bearish_rationale = (
                                    f"Bearish liquidity sweep of HTF High ({latest_htf_high:.5f}) at M15 index {i} "
                                    f"followed by strong displacement at index {j} (body: {body_j:.5f} vs avg: {avg_body_j:.5f})."
                                )

            # Resolve conflicting signals (prefer the one with higher confidence)
            if best_bullish_signal and best_bearish_signal:
                if bullish_conf >= bearish_conf:
                    direction = "buy"
                    confidence = bullish_conf
                    rationale = bullish_rationale
                    tags = ["bullish_sweep", "displacement", "mss"]
                else:
                    direction = "sell"
                    confidence = bearish_conf
                    rationale = bearish_rationale
                    tags = ["bearish_sweep", "displacement", "mss"]
            elif best_bullish_signal:
                direction = "buy"
                confidence = bullish_conf
                rationale = bullish_rationale
                tags = ["bullish_sweep", "displacement", "mss"]
            elif best_bearish_signal:
                direction = "sell"
                confidence = bearish_conf
                rationale = bearish_rationale
                tags = ["bearish_sweep", "displacement", "mss"]

            valid = direction is not None

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=direction,
                valid=valid,
                confidence=float(confidence) if valid else 0.0,
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