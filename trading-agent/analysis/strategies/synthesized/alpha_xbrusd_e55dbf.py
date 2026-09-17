from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal


class SynthesizedStrategy_alpha_xbrusd_e55dbf(EdgeStrategy):
    strategy_id: str = "alpha_xbrusd_e55dbf"
    applicable_symbols: set = {"XBRUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        # Define hyperparameters
        s = settings or {}
        self.htf_timeframe = s.get('htf_timeframe', 'H4')
        self.ltf_timeframe = s.get('ltf_timeframe', 'H1')
        self.swing_window = int(s.get('swing_window', 10))
        self.atr_period = int(s.get('atr_period', 14))
        self.displacement_mult = float(s.get('displacement_mult', 1.5))
        self.sweep_lookback = int(s.get('sweep_lookback', 8))
        self.min_confidence = float(s.get('min_confidence', 0.6))
        self.htf_limit = int(s.get('htf_limit', 200))
        self.ltf_limit = int(s.get('ltf_limit', 200))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            # Fetch higher timeframe (HTF) candles for liquidity level identification
            htf_candles = await self.get_historical_candles(
                session=session, symbol=symbol, timeframe=self.htf_timeframe, limit=self.htf_limit
            )
            # Fetch lower timeframe (LTF) candles for displacement confirmation
            ltf_candles = await self.get_historical_candles(
                session=session, symbol=symbol, timeframe=self.ltf_timeframe, limit=self.ltf_limit
            )

            min_required = max(self.swing_window * 2 + 5, self.atr_period + 5)
            if not htf_candles or not ltf_candles or len(htf_candles) < min_required or len(ltf_candles) < min_required:
                return EdgeSignal(
                    strategy_id=self.strategy_id, symbol=symbol, direction=None,
                    valid=False, confidence=0.0, rationale='Insufficient candle history for evaluation',
                    tags=['insufficient_data']
                )

            # Convert candles to DataFrames using direct attribute access
            htf_df = pd.DataFrame([
                {
                    'open': float(c.open),
                    'high': float(c.high),
                    'low': float(c.low),
                    'close': float(c.close),
                }
                for c in htf_candles
            ])
            ltf_df = pd.DataFrame([
                {
                    'open': float(c.open),
                    'high': float(c.high),
                    'low': float(c.low),
                    'close': float(c.close),
                }
                for c in ltf_candles
            ])

            # Sanitize any NaN/Inf in price arrays
            for col in ('open', 'high', 'low', 'close'):
                htf_df[col] = htf_df[col].replace([np.inf, -np.inf], np.nan).ffill().bfill()
                ltf_df[col] = ltf_df[col].replace([np.inf, -np.inf], np.nan).ffill().bfill()

            # --- Identify HTF swing highs/lows (liquidity pools) ---
            win = self.swing_window
            # Centered rolling to find confirmed pivots
            htf_roll_max = htf_df['high'].rolling(window=2 * win + 1, center=True, min_periods=win + 1).max()
            htf_roll_min = htf_df['low'].rolling(window=2 * win + 1, center=True, min_periods=win + 1).min()
            htf_df['is_swing_high'] = (htf_df['high'] == htf_roll_max) & htf_df['high'].notna()
            htf_df['is_swing_low'] = (htf_df['low'] == htf_roll_min) & htf_df['low'].notna()

            # Exclude the most recent unconfirmed candle from pivot set
            confirmed_mask = pd.Series([True] * len(htf_df), index=htf_df.index)
            confirmed_mask.iloc[-1] = False

            swing_highs = htf_df.loc[htf_df['is_swing_high'] & confirmed_mask, 'high'].tail(5).tolist()
            swing_lows = htf_df.loc[htf_df['is_swing_low'] & confirmed_mask, 'low'].tail(5).tolist()

            if not swing_highs or not swing_lows:
                return EdgeSignal(
                    strategy_id=self.strategy_id, symbol=symbol, direction=None,
                    valid=False, confidence=0.0, rationale='No confirmed HTF swing liquidity levels detected',
                    tags=['no_swings']
                )

            # Pick the most relevant nearby liquidity levels
            htf_resistance = max(swing_highs[-3:]) if len(swing_highs) >= 3 else swing_highs[-1]
            htf_support = min(swing_lows[-3:]) if len(swing_lows) >= 3 else swing_lows[-1]

            # --- LTF ATR calculation for displacement sizing ---
            prev_close = ltf_df['close'].shift(1)
            tr1 = ltf_df['high'] - ltf_df['low']
            tr2 = (ltf_df['high'] - prev_close).abs()
            tr3 = (ltf_df['low'] - prev_close).abs()
            ltf_df['tr'] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1).fillna(0.0)
            ltf_df['atr'] = ltf_df['tr'].rolling(window=self.atr_period, min_periods=1).mean()
            current_atr = float(ltf_df['atr'].iloc[-1])

            if not np.isfinite(current_atr) or current_atr <= 0:
                return EdgeSignal(
                    strategy_id=self.strategy_id, symbol=symbol, direction=None,
                    valid=False, confidence=0.0, rationale='Invalid ATR (non-finite or non-positive)',
                    tags=['invalid_atr']
                )

            # --- Sweep detection on LTF within lookback window ---
            recent = ltf_df.tail(self.sweep_lookback)
            recent_low = float(recent['low'].min())
            recent_high = float(recent['high'].max())

            # Sweep: wick beyond liquidity level but current close back inside
            swept_low = (recent_low < htf_support)
            swept_high = (recent_high > htf_resistance)

            current_open = float(ltf_df['open'].iloc[-1])
            current_close = float(ltf_df['close'].iloc[-1])
            current_high = float(ltf_df['high'].iloc[-1])
            current_low = float(ltf_df['low'].iloc[-1])
            body = current_close - current_open

            bullish_displacement = body >= self.displacement_mult * current_atr
            bearish_displacement = (-body) >= self.displacement_mult * current_atr

            closed_back_above_support = current_close > htf_support
            closed_back_below_resistance = current_close < htf_resistance

            # --- Generate signal ---
            direction = None
            confidence = 0.0
            rationale_parts = []
            tags = ['multi_timeframe', 'liquidity_sweep_displacement']

            if swept_low and bullish_displacement and closed_back_above_support:
                direction = 'buy'
                # Stronger confidence if displacement is large and sweep is clean
                size_factor = min(body / (self.displacement_mult * current_atr), 2.0)
                confidence = float(min(0.95, 0.6 + 0.15 * size_factor))
                rationale_parts.append(
                    f'Swept HTF support {htf_support:.4f} (low={recent_low:.4f}) then closed above'
                )
                rationale_parts.append(
                    f'Bullish LTF displacement body={body:.4f} >= {self.displacement_mult}x ATR({current_atr:.4f})'
                )
                tags.append('bullish_sweep')

            elif swept_high and bearish_displacement and closed_back_below_resistance:
                direction = 'sell'
                size_factor = min((-body) / (self.displacement_mult * current_atr), 2.0)
                confidence = float(min(0.95, 0.6 + 0.15 * size_factor))
                rationale_parts.append(
                    f'Swept HTF resistance {htf_resistance:.4f} (high={recent_high:.4f}) then closed below'
                )
                rationale_parts.append(
                    f'Bearish LTF displacement body={body:.4f} >= {self.displacement_mult}x ATR({current_atr:.4f})'
                )
                tags.append('bearish_sweep')

            else:
                tags.append('no_setup')
                # Identify which condition failed for transparency
                if swept_low and not bullish_displacement:
                    rationale_parts.append('LTF swept HTF support but no bullish displacement')
                elif swept_high and not bearish_displacement:
                    rationale_parts.append('LTF swept HTF resistance but no bearish displacement')
                elif not swept_low and not swept_high:
                    rationale_parts.append('No liquidity sweep of HTF levels detected')
                else:
                    rationale_parts.append('Setup criteria incomplete')

            valid = (direction is not None) and (confidence >= self.min_confidence)

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=direction,
                valid=bool(valid),
                confidence=float(confidence),
                rationale=' | '.join(rationale_parts) if rationale_parts else 'No rationale',
                tags=tags
            )

        except Exception as e:
            logging.getLogger(__name__).exception("Error in SynthesizedStrategy_alpha_xbrusd_e55dbf")
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f'Calculation error: {e}',
                tags=['error']
            )