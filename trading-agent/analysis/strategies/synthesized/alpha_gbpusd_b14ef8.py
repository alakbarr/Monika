from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_gbpusd_b14ef8(EdgeStrategy):
    strategy_id: str = "alpha_gbpusd_b14ef8"
    applicable_symbols: set = {"GBPUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        cfg = settings or {}
        self.h1_lookback: int = int(cfg.get("h1_lookback", 30))
        self.m15_lookback: int = int(cfg.get("m15_lookback", 60))
        self.displacement_mult: float = float(cfg.get("displacement_mult", 1.1))
        self.atr_period: int = int(cfg.get("atr_period", 14))

    def _candles_to_df(self, candles: List[Any]) -> pd.DataFrame:
        if not candles:
            return pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume'])
        
        records = []
        for c in candles:
            if isinstance(c, dict):
                records.append({
                    'open': float(c.get('open', 0.0)),
                    'high': float(c.get('high', 0.0)),
                    'low': float(c.get('low', 0.0)),
                    'close': float(c.get('close', 0.0)),
                    'volume': float(c.get('volume', 0.0)),
                })
            else:
                records.append({
                    'open': float(getattr(c, 'open', 0.0)),
                    'high': float(getattr(c, 'high', 0.0)),
                    'low': float(getattr(c, 'low', 0.0)),
                    'close': float(getattr(c, 'close', 0.0)),
                    'volume': float(getattr(c, 'volume', 0.0)),
                })
        
        df = pd.DataFrame(records)
        df = df.replace([np.inf, -np.inf], np.nan).ffill().bfill().fillna(0.0)
        return df

    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        high = df['high']
        low = df['low']
        close = df['close']
        prev_close = close.shift(1)
        
        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period, min_periods=1).mean()
        return atr.replace([np.inf, -np.inf], np.nan).ffill().bfill().fillna(0.0)

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            if symbol not in self.applicable_symbols:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale=f"Symbol {symbol} not supported by this strategy.",
                    tags=["unsupported_symbol"]
                )

            # Fetch multi-timeframe candle data
            candles_h1 = await self.get_historical_candles(session=session, symbol=symbol, timeframe='H1', limit=100)
            candles_m15 = await self.get_historical_candles(session=session, symbol=symbol, timeframe='M15', limit=100)

            df_h1 = self._candles_to_df(candles_h1)
            df_m15 = self._candles_to_df(candles_m15)

            if len(df_h1) < self.h1_lookback or len(df_m15) < self.atr_period + 5:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient historical candle data for multi-timeframe analysis.",
                    tags=["insufficient_data"]
                )

            # Extract Higher Timeframe (H1) key liquidity levels
            # Excluding recent 2 bars to ensure established structural high/low
            h1_window = df_h1.iloc[-(self.h1_lookback + 2):-2]
            h1_liquidity_high = float(h1_window['high'].max())
            h1_liquidity_low = float(h1_window['low'].min())

            # Lower Timeframe (M15) ATR & Volume Analysis
            df_m15['atr'] = self._calculate_atr(df_m15, self.atr_period)
            df_m15['vol_ma'] = df_m15['volume'].rolling(window=20, min_periods=1).mean().replace([np.inf, -np.inf], np.nan).ffill().bfill().fillna(0.0)

            recent_m15 = df_m15.tail(6).copy().reset_index(drop=True)
            latest_m15 = recent_m15.iloc[-1]
            curr_close = float(latest_m15['close'])
            curr_atr = float(latest_m15['atr'])

            if curr_atr <= 0:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Invalid zero ATR value.",
                    tags=["data_error"]
                )

            # Check for Liquidity Sweeps in recent 5 M15 candles
            recent_lows = recent_m15['low'].values
            recent_highs = recent_m15['high'].values
            recent_opens = recent_m15['open'].values
            recent_closes = recent_m15['close'].values
            recent_volumes = recent_m15['volume'].values
            recent_vol_mas = recent_m15['vol_ma'].values
            recent_atrs = recent_m15['atr'].values

            sell_side_swept = False
            buy_side_swept = False
            swept_idx = -1

            for i in range(len(recent_m15) - 1):  # Check recent completed or ongoing bars
                if recent_lows[i] < h1_liquidity_low:
                    sell_side_swept = True
                    swept_idx = i
                    break

            for i in range(len(recent_m15) - 1):
                if recent_highs[i] > h1_liquidity_high:
                    buy_side_swept = True
                    swept_idx = i
                    break

            direction = None
            confidence = 0.0
            rationale_parts = []
            tags = ["liquidity_sweep"]

            # Evaluate Bullish Multi-timeframe Displacement
            if sell_side_swept and curr_close > h1_liquidity_low:
                # Look for bullish displacement bar following or during the sweep
                displacement_found = False
                max_body_ratio = 0.0
                vol_boost = False

                for i in range(max(0, swept_idx), len(recent_m15)):
                    body = recent_closes[i] - recent_opens[i]
                    atr_val = max(1e-6, recent_atrs[i])
                    body_ratio = body / atr_val

                    if body_ratio >= self.displacement_mult:
                        displacement_found = True
                        max_body_ratio = max(max_body_ratio, body_ratio)
                        if recent_vol_mas[i] > 0 and recent_volumes[i] >= 1.3 * recent_vol_mas[i]:
                            vol_boost = True

                if displacement_found:
                    direction = 'buy'
                    base_conf = 0.65
                    disp_bonus = min(0.18, (max_body_ratio - self.displacement_mult) * 0.1)
                    vol_bonus = 0.10 if vol_boost else 0.0
                    confidence = min(0.95, base_conf + disp_bonus + vol_bonus)

                    rationale_parts.append(
                        f"Bullish sweep of H1 low ({h1_liquidity_low:.5f}). "
                        f"M15 reclaimed level with strong displacement body ratio {max_body_ratio:.2f}x ATR."
                    )
                    tags.extend(["sell_side_liquidity_swept", "bullish_displacement"])

            # Evaluate Bearish Multi-timeframe Displacement
            elif buy_side_swept and curr_close < h1_liquidity_high:
                displacement_found = False
                max_body_ratio = 0.0
                vol_boost = False

                for i in range(max(0, swept_idx), len(recent_m15)):
                    body = recent_opens[i] - recent_closes[i]
                    atr_val = max(1e-6, recent_atrs[i])
                    body_ratio = body / atr_val

                    if body_ratio >= self.displacement_mult:
                        displacement_found = True
                        max_body_ratio = max(max_body_ratio, body_ratio)
                        if recent_vol_mas[i] > 0 and recent_volumes[i] >= 1.3 * recent_vol_mas[i]:
                            vol_boost = True

                if displacement_found:
                    direction = 'sell'
                    base_conf = 0.65
                    disp_bonus = min(0.18, (max_body_ratio - self.displacement_mult) * 0.1)
                    vol_bonus = 0.10 if vol_boost else 0.0
                    confidence = min(0.95, base_conf + disp_bonus + vol_bonus)

                    rationale_parts.append(
                        f"Bearish sweep of H1 high ({h1_liquidity_high:.5f}). "
                        f"M15 reclaimed level with strong displacement body ratio {max_body_ratio:.2f}x ATR."
                    )
                    tags.extend(["buy_side_liquidity_swept", "bearish_displacement"])

            if direction is not None and confidence > 0.5:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=direction,
                    valid=True,
                    confidence=round(confidence, 4),
                    rationale=" ".join(rationale_parts),
                    tags=tags
                )
            else:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="No multi-timeframe liquidity sweep displacement pattern confirmed.",
                    tags=["no_signal"]
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
