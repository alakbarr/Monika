from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal


class SynthesizedStrategy_alpha_usdjpy_41ec5b(EdgeStrategy):
    strategy_id: str = "alpha_usdjpy_41ec5b"
    applicable_symbols: set = {"USDJPY"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        # Define hyperparameters here
        self.atr_period: int = int(self.settings.get('atr_period', 14))
        self.atr_avg_period: int = int(self.settings.get('atr_avg_period', 30))
        self.atr_exhaustion_threshold: float = float(self.settings.get('atr_exhaustion_threshold', 0.85))
        self.mean_period: int = int(self.settings.get('mean_period', 20))
        self.std_period: int = int(self.settings.get('std_period', 20))
        self.z_entry_threshold: float = float(self.settings.get('z_entry_threshold', 1.6))
        self.min_required: int = max(self.atr_period, self.atr_avg_period, self.mean_period, self.std_period) + 10

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            candles = await self.get_historical_candles(
                session=session, symbol=symbol, timeframe='H1', limit=120
            )

            if candles is None or len(candles) < self.min_required:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale=f"Insufficient candle history: need {self.min_required}, got {0 if candles is None else len(candles)}",
                    tags=['no_data']
                )

            # Build numpy arrays from candle objects (support c.high / c['high'])
            highs = np.array([float(c['high'] if isinstance(c, dict) else c.high) for c in candles], dtype=np.float64)
            lows = np.array([float(c['low'] if isinstance(c, dict) else c.low) for c in candles], dtype=np.float64)
            closes = np.array([float(c['close'] if isinstance(c, dict) else c.close) for c in candles], dtype=np.float64)

            # Sanitize inputs
            highs = np.nan_to_num(highs, nan=0.0, posinf=0.0, neginf=0.0)
            lows = np.nan_to_num(lows, nan=0.0, posinf=0.0, neginf=0.0)
            closes = np.nan_to_num(closes, nan=0.0, posinf=0.0, neginf=0.0)

            df = pd.DataFrame({'high': highs, 'low': lows, 'close': closes})

            # True Range
            prev_close = df['close'].shift(1)
            tr1 = df['high'] - df['low']
            tr2 = (df['high'] - prev_close).abs()
            tr3 = (df['low'] - prev_close).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1).fillna(0.0)

            # ATR via rolling mean with min_periods=1 for stability
            atr_series = tr.rolling(window=self.atr_period, min_periods=1).mean()

            # Long-run average ATR for exhaustion detection
            atr_avg_series = atr_series.rolling(window=self.atr_avg_period, min_periods=1).mean()

            # Mean (SMA) and rolling std for z-score
            mean_series = df['close'].rolling(window=self.mean_period, min_periods=1).mean()
            std_series = df['close'].rolling(window=self.std_period, min_periods=1).std().fillna(0.0)

            # Get latest values
            current_close = float(df['close'].iloc[-1])
            current_atr = float(atr_series.iloc[-1])
            current_atr_avg = float(atr_avg_series.iloc[-1])
            current_mean = float(mean_series.iloc[-1])
            current_std = float(std_series.iloc[-1])

            if not np.isfinite(current_close) or not np.isfinite(current_atr) or not np.isfinite(current_atr_avg) or not np.isfinite(current_mean):
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Non-finite indicator values",
                    tags=['nan_error']
                )

            if current_atr_avg <= 0.0 or current_std <= 0.0:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="ATR average or std non-positive; cannot compute signal",
                    tags=['invalid_indicator']
                )

            atr_ratio = current_atr / current_atr_avg
            atr_exhausted = atr_ratio < self.atr_exhaustion_threshold

            z_score = (current_close - current_mean) / current_std
            oversold = z_score <= -self.z_entry_threshold
            overbought = z_score >= self.z_entry_threshold

            if not atr_exhausted:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale=f"ATR not exhausted (ratio={atr_ratio:.3f} >= {self.atr_exhaustion_threshold:.3f}); z={z_score:.2f}",
                    tags=['no_signal', 'atr_active']
                )

            # Confidence scales with magnitude of deviation and degree of ATR contraction
            # atr_gap: how much below the threshold (capped), z_mag: magnitude of z-score (capped)
            atr_gap = max(0.0, self.atr_exhaustion_threshold - atr_ratio) / max(self.atr_exhaustion_threshold, 1e-9)
            atr_gap = min(atr_gap, 1.0)
            z_mag = min(abs(z_score) / 3.0, 1.0)
            confidence = float(min(1.0, 0.35 + 0.45 * z_mag + 0.20 * atr_gap))

            if oversold:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction='buy',
                    valid=True,
                    confidence=confidence,
                    rationale=f"Mean reversion buy: z={z_score:.2f} below -{self.z_entry_threshold}, ATR exhausted ratio={atr_ratio:.3f}",
                    tags=['mean_reversion', 'atr_exhaustion', 'buy', 'usdjpy']
                )
            elif overbought:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction='sell',
                    valid=True,
                    confidence=confidence,
                    rationale=f"Mean reversion sell: z={z_score:.2f} above {self.z_entry_threshold}, ATR exhausted ratio={atr_ratio:.3f}",
                    tags=['mean_reversion', 'atr_exhaustion', 'sell', 'usdjpy']
                )
            else:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale=f"ATR exhausted (ratio={atr_ratio:.3f}) but z={z_score:.2f} within ±{self.z_entry_threshold}; no reversion edge",
                    tags=['no_signal', 'within_band']
                )

        except Exception as e:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Calculation error: {e}",
                tags=['error']
            )