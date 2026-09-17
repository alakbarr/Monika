from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xauusd_754250(EdgeStrategy):
    strategy_id: str = "alpha_xauusd_754250"
    applicable_symbols: set = {"XAUUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.htf_lookback = int(self.settings.get("htf_lookback", 24))
        self.atr_period = int(self.settings.get("atr_period", 14))
        self.displacement_mult = float(self.settings.get("displacement_mult", 0.75))
        self.min_confidence = float(self.settings.get("min_confidence", 0.60))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            # Fetch Multi-Timeframe Candles (H1 for HTF liquidity levels, M15 for execution displacement)
            h1_candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe='H1', limit=100)
            m15_candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe='M15', limit=100)

            if not h1_candles or len(h1_candles) < 30 or not m15_candles or len(m15_candles) < 30:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient MTF candle data for evaluation",
                    tags=["insufficient_data"]
                )

            df_h1 = self._parse_candles(h1_candles)
            df_m15 = self._parse_candles(m15_candles)

            if df_h1.empty or df_m15.empty:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Failed to parse candle data into DataFrame",
                    tags=["data_error"]
                )

            # HTF Analysis: Identify Liquidity Levels and Higher Timeframe Trend Bias
            df_h1['htf_high'] = df_h1['high'].shift(1).rolling(window=self.htf_lookback, min_periods=5).max()
            df_h1['htf_low'] = df_h1['low'].shift(1).rolling(window=self.htf_lookback, min_periods=5).min()
            df_h1['ema50'] = df_h1['close'].ewm(span=50, adjust=False).mean()

            htf_sweep_high = float(df_h1['htf_high'].iloc[-1])
            htf_sweep_low = float(df_h1['htf_low'].iloc[-1])
            htf_ema50 = float(df_h1['ema50'].iloc[-1])

            # LTF Analysis: Calculate ATR and Range Metrics
            tr = np.maximum(
                df_m15['high'] - df_m15['low'],
                np.maximum(
                    (df_m15['high'] - df_m15['close'].shift(1)).abs(),
                    (df_m15['low'] - df_m15['close'].shift(1)).abs()
                )
            )
            df_m15['atr'] = tr.rolling(window=self.atr_period, min_periods=1).mean().ffill().bfill()

            m15_curr = df_m15.iloc[-1]
            m15_prev = df_m15.iloc[-2]

            curr_open = float(m15_curr['open'])
            curr_high = float(m15_curr['high'])
            curr_low = float(m15_curr['low'])
            curr_close = float(m15_curr['close'])
            curr_atr = float(m15_curr['atr'])

            prev_high = float(m15_prev['high'])
            prev_low = float(m15_prev['low'])

            if math.isnan(curr_atr) or curr_atr <= 0:
                curr_atr = max(curr_high - curr_low, 1.0)

            # Measure displacement characteristics
            body_size = abs(curr_close - curr_open)
            candle_range = max(curr_high - curr_low, 1e-6)
            body_ratio = body_size / candle_range

            direction = None
            confidence = 0.0
            rationale_parts = []
            tags = ["liquidity_sweep", "displacement"]

            # Bullish Liquidity Sweep & Displacement Logic
            swept_htf_low = (curr_low < htf_sweep_low or prev_low < htf_sweep_low)
            bullish_displacement = (curr_close > curr_open) and (body_size >= self.displacement_mult * curr_atr)
            bullish_close_reclaim = curr_close > htf_sweep_low

            if swept_htf_low and bullish_displacement and bullish_close_reclaim:
                direction = "buy"
                sweep_depth = (htf_sweep_low - min(curr_low, prev_low)) / curr_atr
                trend_alignment = 1.1 if curr_close > htf_ema50 else 0.95
                confidence = min(0.95, (0.65 + 0.15 * min(sweep_depth, 1.5) + 0.15 * body_ratio) * trend_alignment)
                
                rationale_parts.append(f"Bullish liquidity sweep of HTF low ({htf_sweep_low:.2f}).")
                rationale_parts.append(f"Strong displacement body ({body_size:.2f}) > {self.displacement_mult}x ATR ({curr_atr:.2f}).")
                tags.append("bullish_displacement")

            # Bearish Liquidity Sweep & Displacement Logic
            swept_htf_high = (curr_high > htf_sweep_high or prev_high > htf_sweep_high)
            bearish_displacement = (curr_close < curr_open) and (body_size >= self.displacement_mult * curr_atr)
            bearish_close_reclaim = curr_close < htf_sweep_high

            if swept_htf_high and bearish_displacement and bearish_close_reclaim and direction is None:
                direction = "sell"
                sweep_depth = (max(curr_high, prev_high) - htf_sweep_high) / curr_atr
                trend_alignment = 1.1 if curr_close < htf_ema50 else 0.95
                confidence = min(0.95, (0.65 + 0.15 * min(sweep_depth, 1.5) + 0.15 * body_ratio) * trend_alignment)

                rationale_parts.append(f"Bearish liquidity sweep of HTF high ({htf_sweep_high:.2f}).")
                rationale_parts.append(f"Strong displacement body ({body_size:.2f}) > {self.displacement_mult}x ATR ({curr_atr:.2f}).")
                tags.append("bearish_displacement")

            if direction is None or confidence < self.min_confidence:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=round(confidence, 4),
                    rationale="No liquidity sweep displacement trigger satisfied",
                    tags=["neutral"]
                )

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=direction,
                valid=True,
                confidence=round(confidence, 4),
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

    def _parse_candles(self, candles: List[Any]) -> pd.DataFrame:
        data = []
        for c in candles:
            try:
                o = float(c.open)
                h = float(c.high)
                l = float(c.low)
                cl = float(c.close)
                v = float(c.volume)
            except (AttributeError, TypeError):
                o = float(c['open'])
                h = float(c['high'])
                l = float(c['low'])
                cl = float(c['close'])
                v = float(c.get('volume', 0.0))
            data.append({'open': o, 'high': h, 'low': l, 'close': cl, 'volume': v})
        return pd.DataFrame(data)
