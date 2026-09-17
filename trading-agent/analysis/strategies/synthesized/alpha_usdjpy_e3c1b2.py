from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_usdjpy_e3c1b2(EdgeStrategy):
    strategy_id: str = "alpha_usdjpy_e3c1b2"
    applicable_symbols: set = {"USDJPY"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.atr_period: int = int(self.settings.get("atr_period", 14))
        self.baseline_period: int = int(self.settings.get("baseline_period", 20))
        self.exhaustion_mult: float = float(self.settings.get("exhaustion_mult", 2.25))
        self.rsi_period: int = int(self.settings.get("rsi_period", 14))
        self.rsi_ob: float = float(self.settings.get("rsi_ob", 68.0))
        self.rsi_os: float = float(self.settings.get("rsi_os", 32.0))

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

            candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe='H1', limit=120)
            if not candles or len(candles) < max(self.baseline_period, self.atr_period, self.rsi_period) + 15:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient historical candle data for evaluation.",
                    tags=["insufficient_data"]
                )

            # Build DataFrame safely
            records = []
            for c in candles:
                c_open = float(c.open if hasattr(c, 'open') else c['open'])
                c_high = float(c.high if hasattr(c, 'high') else c['high'])
                c_low = float(c.low if hasattr(c, 'low') else c['low'])
                c_close = float(c.close if hasattr(c, 'close') else c['close'])
                records.append({'open': c_open, 'high': c_high, 'low': c_low, 'close': c_close})

            df = pd.DataFrame.from_records(records)
            df = df.replace([np.inf, -np.inf], np.nan).ffill().bfill()

            # Baseline (Exponential Moving Average)
            df['baseline'] = df['close'].ewm(span=self.baseline_period, adjust=False).mean()

            # Average True Range (ATR)
            prev_close = df['close'].shift(1)
            tr1 = df['high'] - df['low']
            tr2 = (df['high'] - prev_close).abs()
            tr3 = (df['low'] - prev_close).abs()
            df['tr'] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            df['atr'] = df['tr'].ewm(span=self.atr_period, adjust=False).mean()

            # Exhaustion Bands
            df['upper_exhaustion'] = df['baseline'] + (df['atr'] * self.exhaustion_mult)
            df['lower_exhaustion'] = df['baseline'] - (df['atr'] * self.exhaustion_mult)

            # ATR Stretch Metric
            atr_safe = df['atr'].replace(0.0, np.nan).ffill().fillna(1.0)
            df['atr_stretch'] = (df['close'] - df['baseline']) / atr_safe

            # Relative Strength Index (RSI)
            delta = df['close'].diff()
            gain = (delta.where(delta > 0.0, 0.0)).ewm(alpha=1.0 / self.rsi_period, adjust=False).mean()
            loss = ((-delta.where(delta < 0.0, 0.0))).ewm(alpha=1.0 / self.rsi_period, adjust=False).mean()
            rs = gain / loss.replace(0.0, np.nan)
            df['rsi'] = 100.0 - (100.0 / (1.0 + rs))
            df['rsi'] = df['rsi'].ffill().bfill().fillna(50.0)

            # Analyze latest completed state
            curr = df.iloc[-1]
            prev = df.iloc[-2]

            direction: Optional[str] = None
            confidence: float = 0.0
            rationale_parts: List[str] = []
            tags: List[str] = ["mean_reversion", "atr_exhaustion"]

            curr_close = float(curr['close'])
            curr_stretch = float(curr['atr_stretch'])
            curr_rsi = float(curr['rsi'])
            curr_upper = float(curr['upper_exhaustion'])
            curr_lower = float(curr['lower_exhaustion'])
            curr_open = float(curr['open'])

            # Bearish Exhaustion (Overextended to the upside -> Short mean-reversion)
            if (curr_close >= curr_upper or curr_stretch >= self.exhaustion_mult) and curr_rsi >= self.rsi_ob:
                # Bearish rejection or stall confirmation (close below open or wick rejection)
                is_rejection = curr_close <= curr_open or (curr['high'] - max(curr_open, curr_close)) > (curr_close - curr['low'])
                if is_rejection:
                    direction = "sell"
                    stretch_excess = max(0.0, curr_stretch - self.exhaustion_mult)
                    rsi_excess = max(0.0, curr_rsi - self.rsi_ob)
                    confidence = min(0.92, 0.65 + (stretch_excess * 0.1) + (rsi_excess * 0.01))
                    rationale_parts.append(
                        f"Upside exhaustion reached. Price: {curr_close:.3f} >= Upper Band: {curr_upper:.3f} "
                        f"(Stretch: {curr_stretch:.2f} ATRs, RSI: {curr_rsi:.1f}). Mean reversion sell indicated."
                    )
                    tags.extend(["exhaustion_short", "overbought_reversal"])

            # Bullish Exhaustion (Overextended to the downside -> Long mean-reversion)
            elif (curr_close <= curr_lower or curr_stretch <= -self.exhaustion_mult) and curr_rsi <= self.rsi_os:
                # Bullish rejection or stall confirmation (close above open or lower wick rejection)
                is_rejection = curr_close >= curr_open or (min(curr_open, curr_close) - curr['low']) > (curr['high'] - curr_close)
                if is_rejection:
                    direction = "buy"
                    stretch_excess = max(0.0, abs(curr_stretch) - self.exhaustion_mult)
                    rsi_excess = max(0.0, self.rsi_os - curr_rsi)
                    confidence = min(0.92, 0.65 + (stretch_excess * 0.1) + (rsi_excess * 0.01))
                    rationale_parts.append(
                        f"Downside exhaustion reached. Price: {curr_close:.3f} <= Lower Band: {curr_lower:.3f} "
                        f"(Stretch: {curr_stretch:.2f} ATRs, RSI: {curr_rsi:.1f}). Mean reversion buy indicated."
                    )
                    tags.extend(["exhaustion_long", "oversold_reversal"])

            if direction is not None:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=direction,
                    valid=True,
                    confidence=round(confidence, 3),
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
                    rationale=(
                        f"Price within normal ATR bounds (Stretch: {curr_stretch:.2f} ATRs, "
                        f"RSI: {curr_rsi:.1f}). No exhaustion threshold breached."
                    ),
                    tags=["neutral", "within_bounds"]
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