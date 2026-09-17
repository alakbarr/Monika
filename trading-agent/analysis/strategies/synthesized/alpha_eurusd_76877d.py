from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_eurusd_76877d(EdgeStrategy):
    strategy_id: str = "alpha_eurusd_76877d"
    applicable_symbols: set = {"EURUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.base_lookback: int = int(self.settings.get("base_lookback", 20))
        self.min_lookback: int = int(self.settings.get("min_lookback", 10))
        self.max_lookback: int = int(self.settings.get("max_lookback", 45))
        self.volume_ma_period: int = int(self.settings.get("volume_ma_period", 20))
        self.atr_period: int = int(self.settings.get("atr_period", 14))
        self.expansion_mult: float = float(self.settings.get("expansion_mult", 0.5))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            candles = await self.get_historical_candles(
                session=session,
                symbol=symbol,
                timeframe='H1',
                limit=120
            )

            if not candles or len(candles) < max(self.max_lookback + 10, self.volume_ma_period + 10):
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient historical candle data for volume-weighted dynamic Donchian calculation.",
                    tags=["insufficient_data"]
                )

            # Build DataFrame safely
            records = []
            for c in candles:
                c_open = float(c.open if hasattr(c, 'open') else c['open'])
                c_high = float(c.high if hasattr(c, 'high') else c['high'])
                c_low = float(c.low if hasattr(c, 'low') else c['low'])
                c_close = float(c.close if hasattr(c, 'close') else c['close'])
                c_vol = float(c.volume if hasattr(c, 'volume') else c['volume'])
                records.append({
                    'open': c_open,
                    'high': c_high,
                    'low': c_low,
                    'close': c_close,
                    'volume': c_vol if c_vol > 0 else 1.0
                })

            df = pd.DataFrame(records)

            # ATR Calculation
            df['prev_close'] = df['close'].shift(1)
            df['tr1'] = df['high'] - df['low']
            df['tr2'] = (df['high'] - df['prev_close']).abs()
            df['tr3'] = (df['low'] - df['prev_close']).abs()
            df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
            df['atr'] = df['tr'].rolling(window=self.atr_period, min_periods=1).mean().ffill().bfill()

            # Volume Moving Average & Volume Force
            df['vol_ma'] = df['volume'].rolling(window=self.volume_ma_period, min_periods=1).mean().ffill().bfill()
            df['vol_ratio'] = (df['volume'] / (df['vol_ma'] + 1e-8)).replace([np.inf, -np.inf], 1.0).fillna(1.0)

            # Typical Price & VWAP Approximation
            df['tp'] = (df['high'] + df['low'] + df['close']) / 3.0
            df['cum_vp'] = (df['tp'] * df['volume']).rolling(window=self.base_lookback, min_periods=1).sum()
            df['cum_v'] = df['volume'].rolling(window=self.base_lookback, min_periods=1).sum()
            df['vwap'] = (df['cum_vp'] / (df['cum_v'] + 1e-8)).ffill().bfill()

            # Dynamic Donchian Lookback based on Volume Activity
            # High volume activity shrinks the lookback to catch explosive breakouts quickly; lower volume increases lookback
            raw_dynamic_lookback = (self.base_lookback / (df['vol_ratio'] ** 0.5)).clip(
                lower=self.min_lookback,
                upper=self.max_lookback
            ).ffill().bfill()
            df['dyn_lookback'] = raw_dynamic_lookback.round().fillna(self.base_lookback).astype(int)

            # Calculate Dynamic Donchian Channels
            upper_donchian = np.zeros(len(df))
            lower_donchian = np.zeros(len(df))

            highs = df['high'].values
            lows = df['low'].values
            dyn_lb_vals = df['dyn_lookback'].values

            for i in range(len(df)):
                lb = dyn_lb_vals[i]
                start_idx = max(0, i - lb)
                upper_donchian[i] = np.max(highs[start_idx:i]) if i > 0 else highs[0]
                lower_donchian[i] = np.min(lows[start_idx:i]) if i > 0 else lows[0]

            df['upper_donchian'] = upper_donchian
            df['lower_donchian'] = lower_donchian

            # Volume-Weighted Expansion Bands
            df['channel_width'] = df['upper_donchian'] - df['lower_donchian']
            df['channel_width_ma'] = df['channel_width'].rolling(window=self.base_lookback, min_periods=1).mean().ffill().bfill()
            df['is_expanding'] = df['channel_width'] > (df['channel_width_ma'] * (1.0 + self.expansion_mult * 0.1))

            curr = df.iloc[-1]
            prev = df.iloc[-2]

            curr_close = float(curr['close'])
            prev_upper = float(prev['upper_donchian'])
            prev_lower = float(prev['lower_donchian'])
            curr_vwap = float(curr['vwap'])
            curr_vol_ratio = float(curr['vol_ratio'])
            curr_atr = float(curr['atr'])
            is_expanding = bool(curr['is_expanding'])

            direction: Optional[str] = None
            confidence: float = 0.0
            rationale_parts: List[str] = []
            tags: List[str] = ["vw_donchian"]

            # Breakout Expansion Logic
            bullish_breakout = (curr_close > prev_upper) and (curr_close > curr_vwap) and (curr_vol_ratio > 1.1)
            bearish_breakout = (curr_close < prev_lower) and (curr_close < curr_vwap) and (curr_vol_ratio > 1.1)

            if bullish_breakout:
                direction = "buy"
                tags.extend(["donchian_breakout", "volume_expansion", "bullish"])
                breakout_magnitude = (curr_close - prev_upper) / (curr_atr + 1e-8)
                base_conf = 0.60
                conf_vol_boost = min(0.20, (curr_vol_ratio - 1.0) * 0.15)
                conf_mag_boost = min(0.15, breakout_magnitude * 0.10)
                confidence = float(np.clip(base_conf + conf_vol_boost + conf_mag_boost, 0.55, 0.92))
                rationale_parts.append(
                    f"EURUSD Bullish Donchian breakout at {curr_close:.5f} above {prev_upper:.5f} "
                    f"with {curr_vol_ratio:.2f}x volume surge and VWAP alignment ({curr_vwap:.5f})."
                )
            elif bearish_breakout:
                direction = "sell"
                tags.extend(["donchian_breakout", "volume_expansion", "bearish"])
                breakdown_magnitude = (prev_lower - curr_close) / (curr_atr + 1e-8)
                base_conf = 0.60
                conf_vol_boost = min(0.20, (curr_vol_ratio - 1.0) * 0.15)
                conf_mag_boost = min(0.15, breakdown_magnitude * 0.10)
                confidence = float(np.clip(base_conf + conf_vol_boost + conf_mag_boost, 0.55, 0.92))
                rationale_parts.append(
                    f"EURUSD Bearish Donchian breakdown at {curr_close:.5f} below {prev_lower:.5f} "
                    f"with {curr_vol_ratio:.2f}x volume surge and VWAP alignment ({curr_vwap:.5f})."
                )
            else:
                tags.append("neutral_channel")
                rationale_parts.append(
                    f"EURUSD consolidating within dynamic Donchian boundaries "
                    f"[{prev_lower:.5f}, {prev_upper:.5f}], Volume ratio: {curr_vol_ratio:.2f}."
                )

            if is_expanding:
                tags.append("volatility_expansion")

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=direction,
                valid=(direction is not None),
                confidence=confidence,
                rationale=" | ".join(rationale_parts),
                tags=tags
            )

        except Exception as e:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Calculation error: {e}",
                tags=["error"]
            )
