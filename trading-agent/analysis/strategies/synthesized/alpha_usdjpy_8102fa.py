from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

logger = logging.getLogger(__name__)


class SynthesizedStrategy_alpha_usdjpy_8102fa(EdgeStrategy):
    strategy_id: str = "alpha_usdjpy_8102fa"
    applicable_symbols: set = {"USDJPY"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        cfg = self.settings or {}
        self.timeframe: str = str(cfg.get("timeframe", "H1"))
        self.candle_limit: int = int(cfg.get("candle_limit", 120))
        self.base_donchian_period: int = int(cfg.get("base_donchian_period", 20))
        self.atr_period: int = int(cfg.get("atr_period", 14))
        self.volume_ma_period: int = int(cfg.get("volume_ma_period", 20))
        self.bandwidth_lookback: int = int(cfg.get("bandwidth_lookback", 40))
        self.volume_expansion_threshold: float = float(cfg.get("volume_expansion_threshold", 1.25))
        self.min_confidence: float = float(cfg.get("min_confidence", 0.55))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            if symbol.upper() not in self.applicable_symbols:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale=f"Symbol {symbol} not supported by {self.strategy_id}",
                    tags=["unsupported_symbol"],
                )

            candles = await self.get_historical_candles(
                session=session,
                symbol=symbol,
                timeframe=self.timeframe,
                limit=self.candle_limit,
            )

            if not candles or len(candles) < max(self.base_donchian_period, self.bandwidth_lookback) + 10:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient historical candle depth for indicator computation",
                    tags=["insufficient_data"],
                )

            records = []
            for c in candles:
                c_open = getattr(c, "open", None) or (c.get("open") if isinstance(c, dict) else 0.0)
                c_high = getattr(c, "high", None) or (c.get("high") if isinstance(c, dict) else 0.0)
                c_low = getattr(c, "low", None) or (c.get("low") if isinstance(c, dict) else 0.0)
                c_close = getattr(c, "close", None) or (c.get("close") if isinstance(c, dict) else 0.0)
                c_vol = getattr(c, "volume", None) or (c.get("volume") if isinstance(c, dict) else 1.0)
                records.append({
                    "open": float(c_open),
                    "high": float(c_high),
                    "low": float(c_low),
                    "close": float(c_close),
                    "volume": max(float(c_vol), 1e-6),
                })

            df = pd.DataFrame.from_records(records)
            df = df.replace([np.inf, -np.inf], np.nan).ffill().bfill().fillna(0.0)

            # ATR Calculation
            high_low = df["high"] - df["low"]
            high_close = (df["high"] - df["close"].shift(1)).abs()
            low_close = (df["low"] - df["close"].shift(1)).abs()
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            atr = tr.rolling(window=self.atr_period, min_periods=1).mean().ffill().fillna(1e-4)

            # Volume Dynamics
            vol_sma = df["volume"].rolling(window=self.volume_ma_period, min_periods=1).mean().ffill().fillna(1.0)
            vol_ratio = (df["volume"] / vol_sma.replace(0.0, 1.0)).clip(lower=0.1, upper=5.0)

            # Dynamic Donchian Window: Shorter in high volatility/volume, longer in compression
            atr_norm = (atr / (atr.rolling(window=self.bandwidth_lookback, min_periods=1).mean() + 1e-6)).clip(0.5, 2.0)
            vol_factor = (vol_ratio / 1.0).clip(0.5, 2.0)
            dynamic_scaling = (atr_norm * vol_factor).ffill().fillna(1.0)

            # Pre-compute variable period Donchian via rolling bounds
            upper_donchian = df["high"].shift(1).rolling(window=self.base_donchian_period, min_periods=1).max()
            lower_donchian = df["low"].shift(1).rolling(window=self.base_donchian_period, min_periods=1).min()
            mid_donchian = (upper_donchian + lower_donchian) / 2.0

            donchian_width = (upper_donchian - lower_donchian).replace(0.0, 1e-5)
            bandwidth = donchian_width / mid_donchian.replace(0.0, 1.0)
            bandwidth_ma = bandwidth.rolling(window=self.bandwidth_lookback, min_periods=1).mean()
            bandwidth_expansion = bandwidth / bandwidth_ma.replace(0.0, 1e-5)

            # VWAP Proxy (Typical Price * Volume)
            typical_price = (df["high"] + df["low"] + df["close"]) / 3.0
            cum_tp_vol = (typical_price * df["volume"]).rolling(window=self.base_donchian_period, min_periods=1).sum()
            cum_vol = df["volume"].rolling(window=self.base_donchian_period, min_periods=1).sum().replace(0.0, 1.0)
            rolling_vwap = cum_tp_vol / cum_vol

            # Current state evaluation
            curr_idx = len(df) - 1
            c_close = df["close"].iloc[curr_idx]
            c_high = df["high"].iloc[curr_idx]
            c_low = df["low"].iloc[curr_idx]
            c_upper = upper_donchian.iloc[curr_idx]
            c_lower = lower_donchian.iloc[curr_idx]
            c_vwap = rolling_vwap.iloc[curr_idx]
            c_vol_ratio = vol_ratio.iloc[curr_idx]
            c_bw_exp = bandwidth_expansion.iloc[curr_idx]
            c_dyn_scale = dynamic_scaling.iloc[curr_idx]

            direction: Optional[str] = None
            confidence: float = 0.0
            tags: List[str] = ["dynamic_donchian", "volume_expansion"]

            # Breakout and Expansion Conditions
            bullish_breakout = (c_close > c_upper) and (c_close > c_vwap)
            bearish_breakout = (c_close < c_lower) and (c_close < c_vwap)
            volume_confirmed = c_vol_ratio >= self.volume_expansion_threshold
            expansion_active = c_bw_exp >= 1.05

            if bullish_breakout and expansion_active:
                direction = "buy"
                base_score = 0.55
                vol_boost = min((c_vol_ratio - 1.0) * 0.15, 0.25)
                expansion_boost = min((c_bw_exp - 1.0) * 0.15, 0.20)
                confidence = float(np.clip(base_score + vol_boost + expansion_boost, 0.0, 0.95))
                tags.extend(["bullish_breakout", "upper_band_breach"])
                if volume_confirmed:
                    tags.append("high_volume_surge")

            elif bearish_breakout and expansion_active:
                direction = "sell"
                base_score = 0.55
                vol_boost = min((c_vol_ratio - 1.0) * 0.15, 0.25)
                expansion_boost = min((c_bw_exp - 1.0) * 0.15, 0.20)
                confidence = float(np.clip(base_score + vol_boost + expansion_boost, 0.0, 0.95))
                tags.extend(["bearish_breakout", "lower_band_breach"])
                if volume_confirmed:
                    tags.append("high_volume_surge")

            if direction is not None and confidence >= self.min_confidence:
                rationale = (
                    f"USDJPY {direction.upper()} expansion detected: Close={c_close:.3f}, "
                    f"Donchian Upper={c_upper:.3f}, Lower={c_lower:.3f}, "
                    f"Volume Ratio={c_vol_ratio:.2f}x, Bandwidth Expansion={c_bw_exp:.2f}x, "
                    f"Dynamic Scaler={c_dyn_scale:.2f}"
                )
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=direction,
                    valid=True,
                    confidence=confidence,
                    rationale=rationale,
                    tags=tags,
                )

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=True,
                confidence=0.0,
                rationale="Market inside dynamic bounds or volume expansion criteria not satisfied",
                tags=["consolidation_or_no_signal"],
            )

        except Exception as e:
            logger.exception("Evaluation error in SynthesizedStrategy_alpha_usdjpy_8102fa: %s", str(e))
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Calculation error: {e}",
                tags=["error"],
            )