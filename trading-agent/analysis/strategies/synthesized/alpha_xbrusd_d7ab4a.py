from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xbrusd_d7ab4a(EdgeStrategy):
    strategy_id: str = "alpha_xbrusd_d7ab4a"
    applicable_symbols: set = {"XBRUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.htf_lookback = self.settings.get("htf_lookback", 48)  # 48 hours of H1 candles
        self.ltf_sweep_lookback = self.settings.get("ltf_sweep_lookback", 8)  # 8 M15 candles (2 hours)
        self.displacement_mult = self.settings.get("displacement_mult", 1.3)
        self.atr_period = self.settings.get("atr_period", 14)
        self.ema_period = self.settings.get("ema_period", 10)

    def _candles_to_df(self, candles: List[Any]) -> pd.DataFrame:
        if not candles:
            return pd.DataFrame()
        data = []
        for c in candles:
            if hasattr(c, 'open'):
                data.append({
                    'open': float(c.open),
                    'high': float(c.high),
                    'low': float(c.low),
                    'close': float(c.close),
                    'volume': float(getattr(c, 'volume', 0.0))
                })
            elif isinstance(c, dict):
                data.append({
                    'open': float(c.get('open', 0.0)),
                    'high': float(c.get('high', 0.0)),
                    'low': float(c.get('low', 0.0)),
                    'close': float(c.get('close', 0.0)),
                    'volume': float(c.get('volume', 0.0))
                })
            else:
                try:
                    data.append({
                        'open': float(c['open']),
                        'high': float(c['high']),
                        'low': float(c['low']),
                        'close': float(c['close']),
                        'volume': float(c.get('volume', 0.0))
                    })
                except Exception:
                    pass
        return pd.DataFrame(data)

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            if symbol not in self.applicable_symbols:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale=f"Symbol {symbol} not applicable.",
                    tags=["inapplicable"]
                )

            # Fetch multi-timeframe candles
            candles_h1 = await self.get_historical_candles(session=session, symbol=symbol, timeframe='H1', limit=100)
            candles_m15 = await self.get_historical_candles(session=session, symbol=symbol, timeframe='M15', limit=100)

            df_h1 = self._candles_to_df(candles_h1)
            df_m15 = self._candles_to_df(candles_m15)

            if df_h1.empty or df_m15.empty or len(df_h1) < 10 or len(df_m15) < 20:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient historical candle data for H1 or M15.",
                    tags=["insufficient_data"]
                )

            # Calculate HTF Liquidity Levels (excluding the current/last H1 candle to avoid lookahead bias)
            lookback_h1 = min(len(df_h1) - 1, self.htf_lookback)
            htf_high = float(df_h1['high'].iloc[-lookback_h1:-1].max())
            htf_low = float(df_h1['low'].iloc[-lookback_h1:-1].min())

            # Calculate LTF Indicators
            high_low = df_m15['high'] - df_m15['low']
            high_cp = (df_m15['high'] - df_m15['close'].shift(1)).abs()
            low_cp = (df_m15['low'] - df_m15['close'].shift(1)).abs()
            df_m15['tr'] = np.maximum(high_low, np.maximum(high_cp, low_cp))
            df_m15['atr'] = df_m15['tr'].rolling(window=self.atr_period, min_periods=1).mean()
            df_m15['ema'] = df_m15['close'].ewm(span=self.ema_period, adjust=False).mean()

            # Sanitize NaNs/Infs safely
            df_m15 = df_m15.ffill().bfill().fillna(0.0)

            # Check for Liquidity Sweep on LTF
            slice_start = -min(len(df_m15), self.ltf_sweep_lookback)
            ltf_slice = df_m15.iloc[slice_start:]

            # Bullish Sweep: Low of any recent M15 candle went below htf_low, but current close is above htf_low
            swept_low = (ltf_slice['low'] < htf_low).any() and (df_m15['close'].iloc[-1] > htf_low)

            # Bearish Sweep: High of any recent M15 candle went above htf_high, but current close is below htf_high
            swept_high = (ltf_slice['high'] > htf_high).any() and (df_m15['close'].iloc[-1] < htf_high)

            # Check for Displacement Confirmation (strong momentum candle in the last 5 periods)
            disp_slice = df_m15.iloc[-5:]
            atr_val = float(df_m15['atr'].iloc[-1])
            if atr_val <= 0:
                atr_val = 0.01

            bullish_disp = False
            bearish_disp = False

            for idx in range(len(disp_slice)):
                c_open = float(disp_slice['open'].iloc[idx])
                c_close = float(disp_slice['close'].iloc[idx])
                if (c_close - c_open) > (self.displacement_mult * atr_val):
                    bullish_disp = True
                if (c_open - c_close) > (self.displacement_mult * atr_val):
                    bearish_disp = True

            direction = None
            confidence = 0.0
            rationale = "No liquidity sweep displacement setup detected."
            tags = ["neutral"]

            current_close = float(df_m15['close'].iloc[-1])
            current_ema = float(df_m15['ema'].iloc[-1])

            if swept_low and bullish_disp and (current_close > current_ema):
                direction = 'buy'
                max_body = float((disp_slice['close'] - disp_slice['open']).max())
                confidence = min(0.95, max(0.5, max_body / (atr_val * 2.0)))
                rationale = f"Bullish liquidity sweep of HTF low ({htf_low:.3f}) with M15 displacement confirmation."
                tags = ["bullish_sweep", "displacement", "xbrusd"]

            elif swept_high and bearish_disp and (current_close < current_ema):
                direction = 'sell'
                max_body = float((disp_slice['open'] - disp_slice['close']).max())
                confidence = min(0.95, max(0.5, max_body / (atr_val * 2.0)))
                rationale = f"Bearish liquidity sweep of HTF high ({htf_high:.3f}) with M15 displacement confirmation."
                tags = ["bearish_sweep", "displacement", "xbrusd"]

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=direction,
                valid=True if direction else False,
                confidence=confidence if direction else 0.0,
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
                rationale=f"Calculation error: {e}",
                tags=["error"]
            )
