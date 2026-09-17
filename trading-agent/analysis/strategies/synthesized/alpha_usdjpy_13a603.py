from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_usdjpy_13a603(EdgeStrategy):
    strategy_id: str = "alpha_usdjpy_13a603"
    applicable_symbols: set = {"USDJPY"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        # Hyperparameters for the multi-timeframe liquidity sweep displacement strategy
        self.htf_ema_fast = int(self.settings.get('htf_ema_fast', 21))
        self.htf_ema_slow = int(self.settings.get('htf_ema_slow', 55))
        self.swing_lookback = int(self.settings.get('swing_lookback', 5))
        self.atr_period = int(self.settings.get('atr_period', 14))
        self.displacement_atr_mult = float(self.settings.get('displacement_atr_mult', 1.5))
        self.sweep_wick_ratio = float(self.settings.get('sweep_wick_ratio', 0.55))
        self.fvg_lookback = int(self.settings.get('fvg_lookback', 3))
        self.risk_atr_mult = float(self.settings.get('risk_atr_mult', 1.2))
        self.reward_atr_mult = float(self.settings.get('reward_atr_mult', 2.0))
        self.confidence_threshold = float(self.settings.get('confidence_threshold', 0.55))
        self.htf_limit = int(self.settings.get('htf_limit', 200))
        self.mtf_limit = int(self.settings.get('mtf_limit', 200))
        self.ltf_limit = int(self.settings.get('ltf_limit', 100))
        self.logger = logging.getLogger(__name__)

    def _to_df(self, candles: List[Any]) -> pd.DataFrame:
        rows = []
        for c in candles:
            # Support both attribute access and dict access
            if isinstance(c, dict):
                rows.append({
                    'open': float(c.get('open', 0.0)),
                    'high': float(c.get('high', 0.0)),
                    'low': float(c.get('low', 0.0)),
                    'close': float(c.get('close', 0.0)),
                    'volume': float(c.get('volume', 0.0) or 0.0),
                })
            else:
                rows.append({
                    'open': float(getattr(c, 'open', 0.0)),
                    'high': float(getattr(c, 'high', 0.0)),
                    'low': float(getattr(c, 'low', 0.0)),
                    'close': float(getattr(c, 'close', 0.0)),
                    'volume': float(getattr(c, 'volume', 0.0) or 0.0),
                })
        return pd.DataFrame(rows)

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            # Fetch HTF, MTF, LTF candle history
            htf_candles = await self.get_historical_candles(
                session=session, symbol=symbol, timeframe='H1', limit=self.htf_limit
            )
            mtf_candles = await self.get_historical_candles(
                session=session, symbol=symbol, timeframe='M15', limit=self.mtf_limit
            )
            ltf_candles = await self.get_historical_candles(
                session=session, symbol=symbol, timeframe='M5', limit=self.ltf_limit
            )

            if not htf_candles or not mtf_candles or not ltf_candles:
                return EdgeSignal(
                    strategy_id=self.strategy_id, symbol=symbol,
                    direction=None, valid=False, confidence=0.0,
                    rationale='Insufficient candle history across timeframes',
                    tags=['no_data']
                )

            htf_df = self._to_df(htf_candles)
            mtf_df = self._to_df(mtf_candles)
            ltf_df = self._to_df(ltf_candles)

            # Sanitize
            for df in (htf_df, mtf_df, ltf_df):
                df.replace([np.inf, -np.inf], np.nan, inplace=True)
                df.ffill(inplace=True)
                df.bfill(inplace=True)
                df.fillna(0.0, inplace=True)

            # === HTF: Trend via EMA crossover + swing structure ===
            htf_df['ema_fast'] = htf_df['close'].ewm(span=self.htf_ema_fast, adjust=False).mean()
            htf_df['ema_slow'] = htf_df['close'].ewm(span=self.htf_ema_slow, adjust=False).mean()
            htf_trend_up = htf_df['ema_fast'].iloc[-1] > htf_df['ema_slow'].iloc[-1]
            htf_trend_down = htf_df['ema_fast'].iloc[-1] < htf_df['ema_slow'].iloc[-1]

            # Identify recent swing highs/lows on HTF (liquidity pools)
            highs = htf_df['high'].values
            lows = htf_df['low'].values
            lb = self.swing_lookback
            recent_swing_highs = []
            recent_swing_lows = []
            for i in range(lb, len(htf_df) - lb):
                if highs[i] == max(highs[i-lb:i+lb+1]):
                    recent_swing_highs.append((i, highs[i]))
                if lows[i] == min(lows[i-lb:i+lb+1]):
                    recent_swing_lows.append((i, lows[i]))
            if not recent_swing_highs or not recent_swing_lows:
                return EdgeSignal(
                    strategy_id=self.strategy_id, symbol=symbol,
                    direction=None, valid=False, confidence=0.0,
                    rationale='Not enough swing structure on HTF',
                    tags=['no_structure']
                )

            latest_swing_high = recent_swing_highs[-1][1]
            latest_swing_low = recent_swing_lows[-1][1]

            # === MTF: Liquidity sweep + displacement detection ===
            mtf_df['atr'] = self._atr(mtf_df, self.atr_period)
            mtf_atr = mtf_df['atr'].iloc[-1] if not math.isnan(mtf_df['atr'].iloc[-1]) else 0.001

            # Look back across last N MTF candles
            lookback_window = min(len(mtf_df) - 1, 20)
            sweep_long = False  # Swept below swing low then closed above
            sweep_short = False
            displacement_long = False
            displacement_short = False

            sweep_idx = -1
            for i in range(len(mtf_df) - lookback_window, len(mtf_df) - 1):
                candle_low = mtf_df['low'].iloc[i]
                candle_high = mtf_df['high'].iloc[i]
                candle_close = mtf_df['close'].iloc[i]
                candle_open = mtf_df['open'].iloc[i]
                candle_range = candle_high - candle_low
                if candle_range <= 0:
                    continue
                upper_wick = candle_high - max(candle_open, candle_close)
                lower_wick = min(candle_open, candle_close) - candle_low

                # Bearish sweep: wick above swing high with high wick ratio
                if (candle_high > latest_swing_high and 
                    candle_close < latest_swing_high and 
                    upper_wick / candle_range >= self.sweep_wick_ratio):
                    sweep_short = True
                    sweep_idx = i

                # Bullish sweep: wick below swing low
                if (candle_low < latest_swing_low and 
                    candle_close > latest_swing_low and 
                    lower_wick / candle_range >= self.sweep_wick_ratio):
                    sweep_long = True
                    sweep_idx = i

            # Displacement: large body candle in trend direction after sweep
            if sweep_short and htf_trend_up:
                for j in range(sweep_idx + 1, len(mtf_df)):
                    candle = mtf_df.iloc[j]
                    body = abs(candle['close'] - candle['open'])
                    if body >= mtf_atr * self.displacement_atr_mult and candle['close'] > candle['open']:
                        displacement_short = True
                        break

            if sweep_long and htf_trend_down:
                for j in range(sweep_idx + 1, len(mtf_df)):
                    candle = mtf_df.iloc[j]
                    body = abs(candle['close'] - candle['open'])
                    if body >= mtf_atr * self.displacement_atr_mult and candle['close'] < candle['open']:
                        displacement_long = True
                        break

            # === LTF: Entry confirmation via micro structure ===
            ltf_df['atr'] = self._atr(ltf_df, self.atr_period)
            ltf_atr = ltf_df['atr'].iloc[-1] if not math.isnan(ltf_df['atr'].iloc[-1]) else 0.001
            ltf_close = ltf_df['close'].iloc[-1]

            direction = None
            entry = None
            sl = None
            tp = None
            confidence = 0.0
            rationale_parts = []
            tags = []

            if sweep_short and displacement_short and htf_trend_up:
                # Look for LTF pullback into FVG or 50% of displacement candle
                if ltf_close < mtf_df['close'].iloc[-1]:
                    entry = ltf_close
                    sl = latest_swing_high + ltf_atr * 0.5
                    tp = entry - (sl - entry) * (self.reward_atr_mult / self.risk_atr_mult)
                    direction = 'sell'
                    confidence = 0.7
                    rationale_parts.append('Bearish sweep of HTF high')
                    rationale_parts.append('Displacement candle after sweep')
                    rationale_parts.append('LTF pullback confirmed')
                    tags = ['sweep_dislacement', 'htf_up', 'short_setup']

            elif sweep_long and displacement_long and htf_trend_down:
                if ltf_close > mtf_df['close'].iloc[-1]:
                    entry = ltf_close
                    sl = latest_swing_low - ltf_atr * 0.5
                    tp = entry + (entry - sl) * (self.reward_atr_mult / self.risk_atr_mult)
                    direction = 'buy'
                    confidence = 0.7
                    rationale_parts.append('Bullish sweep of HTF low')
                    rationale_parts.append('Displacement candle after sweep')
                    rationale_parts.append('LTF pullback confirmed')
                    tags = ['sweep_dislacement', 'htf_down', 'long_setup']

            # Adjust confidence with EMA separation strength
            if direction:
                ema_sep = abs(htf_df['ema_fast'].iloc[-1] - htf_df['ema_slow'].iloc[-1])
                ema_norm = ema_sep / max(htf_df['close'].iloc[-1], 1e-9)
                confidence = min(0.95, confidence + min(0.2, ema_norm * 50))
                rationale = ' | '.join(rationale_parts)
                valid = confidence >= self.confidence_threshold
                return EdgeSignal(
                    strategy_id=self.strategy_id, symbol=symbol,
                    direction=direction, valid=valid, confidence=float(confidence),
                    rationale=rationale, tags=tags
                )

            return EdgeSignal(
                strategy_id=self.strategy_id, symbol=symbol,
                direction=None, valid=False, confidence=0.0,
                rationale='No valid sweep+displacement setup detected',
                tags=['no_setup']
            )

        except Exception as e:
            return EdgeSignal(
                strategy_id=self.strategy_id, symbol=symbol,
                direction=None, valid=False, confidence=0.0,
                rationale=f'Calculation error: {e}',
                tags=['error']
            )

    def _atr(self, df: pd.DataFrame, period: int) -> pd.Series:
        high = df['high']
        low = df['low']
        close = df['close']
        prev_close = close.shift(1)
        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs()
        ], axis=1).max(axis=1)
        atr = tr.ewm(span=period, adjust=False).mean()
        return atr.bfill().fillna(0.0)