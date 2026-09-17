from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xtiusd_403155(EdgeStrategy):
    strategy_id: str = "alpha_xtiusd_403155"
    applicable_symbols: set = {"XTIUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.htf_lookback: int = self.settings.get("htf_lookback", 40)
        self.ltf_lookback: int = self.settings.get("ltf_lookback", 60)
        self.swing_pivot_len: int = self.settings.get("swing_pivot_len", 3)
        self.displacement_mult: float = self.settings.get("displacement_mult", 1.4)
        self.min_confidence: float = self.settings.get("min_confidence", 0.65)

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            # Fetch High Timeframe (H4) candles for liquidity levels
            htf_candles = await self.get_historical_candles(
                session=session, symbol=symbol, timeframe='H4', limit=self.htf_lookback
            )
            # Fetch Lower Timeframe (M15) candles for liquidity sweep & displacement validation
            ltf_candles = await self.get_historical_candles(
                session=session, symbol=symbol, timeframe='M15', limit=self.ltf_lookback
            )

            if not htf_candles or len(htf_candles) < 20 or not ltf_candles or len(ltf_candles) < 30:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient multi-timeframe candle data for liquidity sweep analysis.",
                    tags=["insufficient_data"]
                )

            # Build HTF DataFrame
            htf_df = pd.DataFrame([
                {
                    'open': float(c.open if hasattr(c, 'open') else c['open']),
                    'high': float(c.high if hasattr(c, 'high') else c['high']),
                    'low': float(c.low if hasattr(c, 'low') else c['low']),
                    'close': float(c.close if hasattr(c, 'close') else c['close']),
                }
                for c in htf_candles
            ]).replace([np.inf, -np.inf], np.nan).ffill().bfill()

            # Build LTF DataFrame
            ltf_df = pd.DataFrame([
                {
                    'open': float(c.open if hasattr(c, 'open') else c['open']),
                    'high': float(c.high if hasattr(c, 'high') else c['high']),
                    'low': float(c.low if hasattr(c, 'low') else c['low']),
                    'close': float(c.close if hasattr(c, 'close') else c['close']),
                }
                for c in ltf_candles
            ]).replace([np.inf, -np.inf], np.nan).ffill().bfill()

            # Compute HTF Swing Highs and Lows (Liquidity Pools)
            p = self.swing_pivot_len
            htf_highs = htf_df['high'].values
            htf_lows = htf_df['low'].values
            
            swing_highs = []
            swing_lows = []
            
            for i in range(p, len(htf_df) - 1):
                is_pivot_high = all(htf_highs[i] >= htf_highs[i - j] for j in range(1, p + 1)) and \
                               all(htf_highs[i] >= htf_highs[i + j] for j in range(1, min(p + 1, len(htf_df) - i)))
                is_pivot_low = all(htf_lows[i] <= htf_lows[i - j] for j in range(1, p + 1)) and \
                              all(htf_lows[i] <= htf_lows[i + j] for j in range(1, min(p + 1, len(htf_df) - i)))
                
                if is_pivot_high:
                    swing_highs.append(float(htf_highs[i]))
                if is_pivot_low:
                    swing_lows.append(float(htf_lows[i]))

            if not swing_highs or not swing_lows:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="No clear HTF swing liquidity pools identified.",
                    tags=["no_liquidity_levels"]
                )

            recent_htf_high = swing_highs[-1]
            recent_htf_low = swing_lows[-1]

            # LTF Analysis: Calculate ATR and Candle Bodies
            ltf_df['tr'] = np.maximum(
                ltf_df['high'] - ltf_df['low'],
                np.maximum(
                    np.abs(ltf_df['high'] - ltf_df['close'].shift(1)),
                    np.abs(ltf_df['low'] - ltf_df['close'].shift(1))
                )
            ).fillna(ltf_df['high'] - ltf_df['low'])
            
            ltf_df['atr'] = ltf_df['tr'].rolling(window=14, min_periods=1).mean()
            ltf_df['body'] = np.abs(ltf_df['close'] - ltf_df['open'])

            # Look for recent sweep and displacement in the last 5 LTF candles
            check_window = ltf_df.iloc[-5:].copy()
            current_candle = ltf_df.iloc[-1]
            current_atr = max(float(current_candle['atr']), 1e-4)

            bullish_sweep = False
            bearish_sweep = False

            # Check for Bearish Liquidity Sweep (Swept HTF high, then reversed down with displacement)
            swept_high_bars = check_window[check_window['high'] > recent_htf_high]
            if not swept_high_bars.empty:
                # Price breached HTF high but current bar is closing below that level
                if current_candle['close'] < recent_htf_high:
                    # Displacement: bearish candle with body exceeding multiple of ATR
                    if current_candle['close'] < current_candle['open'] and current_candle['body'] >= (self.displacement_mult * current_atr):
                        bearish_sweep = True

            # Check for Bullish Liquidity Sweep (Swept HTF low, then reversed up with displacement)
            swept_low_bars = check_window[check_window['low'] < recent_htf_low]
            if not swept_low_bars.empty:
                # Price breached HTF low but current bar is closing above that level
                if current_candle['close'] > recent_htf_low:
                    # Displacement: bullish candle with body exceeding multiple of ATR
                    if current_candle['close'] > current_candle['open'] and current_candle['body'] >= (self.displacement_mult * current_atr):
                        bullish_sweep = True

            direction = None
            confidence = 0.0
            rationale_parts = []
            tags = ["liquidity_sweep"]

            if bullish_sweep and not bearish_sweep:
                direction = "buy"
                displacement_strength = min(1.0, float(current_candle['body'] / (2.5 * current_atr)))
                confidence = float(np.clip(0.60 + (displacement_strength * 0.35), 0.0, 0.95))
                rationale_parts.append(
                    f"HTF sell-side liquidity at {recent_htf_low:.2f} swept on LTF with strong bullish displacement "
                    f"(body={current_candle['body']:.2f}, ATR={current_atr:.2f})."
                )
                tags.extend(["bullish_displacement", "buy_side_sweep"])

            elif bearish_sweep and not bullish_sweep:
                direction = "sell"
                displacement_strength = min(1.0, float(current_candle['body'] / (2.5 * current_atr)))
                confidence = float(np.clip(0.60 + (displacement_strength * 0.35), 0.0, 0.95))
                rationale_parts.append(
                    f"HTF buy-side liquidity at {recent_htf_high:.2f} swept on LTF with strong bearish displacement "
                    f"(body={current_candle['body']:.2f}, ATR={current_atr:.2f})."
                )
                tags.extend(["bearish_displacement", "sell_side_sweep"])

            if direction and confidence >= self.min_confidence:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=direction,
                    valid=True,
                    confidence=confidence,
                    rationale=" ".join(rationale_parts),
                    tags=tags
                )

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale="No active multi-timeframe liquidity sweep displacement pattern detected.",
                tags=["neutral"]
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