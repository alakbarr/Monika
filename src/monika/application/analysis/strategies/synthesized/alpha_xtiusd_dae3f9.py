from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal


class SynthesizedStrategy_alpha_xtiusd_dae3f9(EdgeStrategy):
    strategy_id: str = "alpha_xtiusd_dae3f9"
    applicable_symbols: set = {"XTIUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        cfg = settings or {}
        # Multi-timeframe configuration
        self.htf_timeframe: str = str(cfg.get("htf_timeframe", "H4"))
        self.ltf_timeframe: str = str(cfg.get("ltf_timeframe", "H1"))
        self.htf_lookback: int = int(cfg.get("htf_lookback", 120))
        self.ltf_lookback: int = int(cfg.get("ltf_lookback", 240))
        # Swing / structure detection
        self.swing_length: int = int(cfg.get("swing_length", 5))
        # Displacement thresholds
        self.body_ratio_min: float = float(cfg.get("body_ratio_min", 0.65))
        self.displacement_atr_mult: float = float(cfg.get("displacement_atr_mult", 1.5))
        self.atr_period: int = int(cfg.get("atr_period", 14))
        # Signal gating
        self.min_confidence: float = float(cfg.get("min_confidence", 0.55))
        self.max_recent_lookback: int = int(cfg.get("max_recent_lookback", 5))
        self._logger = logging.getLogger(__name__)

    # ---------------- helpers ----------------
    def _atr(self, highs: List[float], lows: List[float], closes: List[float], period: int) -> List[float]:
        n = len(highs)
        if n < 2 or period < 1:
            return [0.0] * n
        tr = [0.0] * n
        for i in range(1, n):
            hi, lo, pc = highs[i], lows[i], closes[i - 1]
            tr[i] = max(hi - lo, abs(hi - pc), abs(lo - pc))
        atr = [0.0] * n
        if n > period:
            seed = sum(tr[1:period + 1]) / float(period)
            atr[period] = seed
            for i in range(period + 1, n):
                atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / float(period)
        return atr

    def _find_swings(self, highs: List[float], lows: List[float], length: int) -> Dict[str, List[int]]:
        n = len(highs)
        swing_highs: List[int] = []
        swing_lows: List[int] = []
        if length <= 0 or n < 2 * length + 1:
            return {"highs": swing_highs, "lows": swing_lows}
        for i in range(length, n - length):
            is_sh = True
            for j in range(1, length + 1):
                if highs[i] <= highs[i - j] or highs[i] <= highs[i + j]:
                    is_sh = False
                    break
            if is_sh:
                swing_highs.append(i)
            is_sl = True
            for j in range(1, length + 1):
                if lows[i] >= lows[i - j] or lows[i] >= lows[i + j]:
                    is_sl = False
                    break
            if is_sl:
                swing_lows.append(i)
        return {"highs": swing_highs, "lows": swing_lows}

    def _htf_bias(self, highs: List[float], lows: List[float], closes: List[float]) -> str:
        min_bars = max(2 * self.swing_length + 2, 20)
        if len(closes) < min_bars:
            return "neutral"
        swings = self._find_swings(highs, lows, self.swing_length)
        sh = swings["highs"]
        sl = swings["lows"]
        if len(sh) < 2 or len(sl) < 2:
            return "neutral"
        last_sh, prev_sh = sh[-1], sh[-2]
        last_sl, prev_sl = sl[-1], sl[-2]
        higher_high = highs[last_sh] > highs[prev_sh]
        higher_low = lows[last_sl] > lows[prev_sl]
        lower_high = highs[last_sh] < highs[prev_sh]
        lower_low = lows[last_sl] < lows[prev_sl]
        if higher_high and higher_low:
            return "bullish"
        if lower_high and lower_low:
            return "bearish"
        return "neutral"

    def _detect_sweep_displacement(self, candles: List[Any]) -> Optional[Dict[str, Any]]:
        n = len(candles)
        if n < 2 * self.swing_length + 5:
            return None
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        opens = [c.open for c in candles]
        closes = [c.close for c in candles]
        atr_series = self._atr(highs, lows, closes, self.atr_period)
        swings = self._find_swings(highs, lows, self.swing_length)
        swing_highs = swings["highs"]
        swing_lows = swings["lows"]
        if not swing_highs and not swing_lows:
            return None
        # Scan only the most recent completed candles for fresh setups
        start = max(2 * self.swing_length + 1, n - self.max_recent_lookback)
        for i in range(n - 1, start - 1, -1):
            hi, lo, op, cl = highs[i], lows[i], opens[i], closes[i]
            rng = hi - lo
            if rng <= 0.0:
                continue
            body = abs(cl - op)
            current_atr = atr_series[i] if i < len(atr_series) else 0.0
            if current_atr <= 0.0:
                continue
            body_ratio = body / rng
            range_vs_atr = rng / current_atr
            if body_ratio < self.body_ratio_min:
                continue
            if range_vs_atr < self.displacement_atr_mult:
                continue
            # Bullish setup: sweep a prior swing low + bullish displacement closing back above it
            swept_low_level: Optional[float] = None
            for sh_idx in swing_lows:
                if sh_idx >= i:
                    continue
                if lo < lows[sh_idx]:
                    swept_low_level = lows[sh_idx]
                    break
            if cl > op and swept_low_level is not None and cl > swept_low_level:
                return {
                    "direction": "buy",
                    "sweep_index": i,
                    "swept_level": swept_low_level,
                    "entry_price": cl,
                    "stop_loss": lo,
                    "range_vs_atr": range_vs_atr,
                    "body_ratio": body_ratio,
                }
            # Bearish setup: sweep a prior swing high + bearish displacement closing back below it
            swept_high_level: Optional[float] = None
            for sh_idx in swing_highs:
                if sh_idx >= i:
                    continue
                if hi > highs[sh_idx]:
                    swept_high_level = highs[sh_idx]
                    break
            if cl < op and swept_high_level is not None and cl < swept_high_level:
                return {
                    "direction": "sell",
                    "sweep_index": i,
                    "swept_level": swept_high_level,
                    "entry_price": cl,
                    "stop_loss": hi,
                    "range_vs_atr": range_vs_atr,
                    "body_ratio": body_ratio,
                }
        return None

    # ---------------- main entry ----------------
    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            htf_candles = await self.get_historical_candles(
                session=session, symbol=symbol,
                timeframe=self.htf_timeframe, limit=self.htf_lookback,
            )
            if not htf_candles or len(htf_candles) < 2 * self.swing_length + 2:
                return EdgeSignal(
                    strategy_id=self.strategy_id, symbol=symbol,
                    direction=None, valid=False, confidence=0.0,
                    rationale=f"Insufficient {self.htf_timeframe} candle history for HTF bias",
                    tags=["insufficient_data", self.htf_timeframe],
                )
            ltf_candles = await self.get_historical_candles(
                session=session, symbol=symbol,
                timeframe=self.ltf_timeframe, limit=self.ltf_lookback,
            )
            if not ltf_candles or len(ltf_candles) < 2 * self.swing_length + 5:
                return EdgeSignal(
                    strategy_id=self.strategy_id, symbol=symbol,
                    direction=None, valid=False, confidence=0.0,
                    rationale=f"Insufficient {self.ltf_timeframe} candle history for LTF setup",
                    tags=["insufficient_data", self.ltf_timeframe],
                )
            htf_highs = [c.high for c in htf_candles]
            htf_lows = [c.low for c in htf_candles]
            htf_closes = [c.close for c in htf_candles]
            bias = self._htf_bias(htf_highs, htf_lows, htf_closes)
            if bias == "neutral":
                return EdgeSignal(
                    strategy_id=self.strategy_id, symbol=symbol,
                    direction=None, valid=False, confidence=0.0,
                    rationale=f"HTF {self.htf_timeframe} structure is neutral; no directional bias",
                    tags=["neutral_bias", self.htf_timeframe],
                )
            setup = self._detect_sweep_displacement(ltf_candles)
            if setup is None:
                return EdgeSignal(
                    strategy_id=self.strategy_id, symbol=symbol,
                    direction=None, valid=False, confidence=0.0,
                    rationale=(
                        f"No fresh liquidity-sweep + displacement on {self.ltf_timeframe} "
                        f"within last {self.max_recent_lookback} candles"
                    ),
                    tags=["no_setup", "liquidity_sweep", self.ltf_timeframe],
                )
            # Confluence filter: LTF direction must agree with HTF bias
            if setup["direction"] == "buy" and bias != "bullish":
                return EdgeSignal(
                    strategy_id=self.strategy_id, symbol=symbol,
                    direction=None, valid=False, confidence=0.0,
                    rationale="LTF bullish sweep+displacement conflicts with bearish HTF bias",
                    tags=["bias_conflict", "multi_timeframe"],
                )
            if setup["direction"] == "sell" and bias != "bearish":
                return EdgeSignal(
                    strategy_id=self.strategy_id, symbol=symbol,
                    direction=None, valid=False, confidence=0.0,
                    rationale="LTF bearish sweep+displacement conflicts with bullish HTF bias",
                    tags=["bias_conflict", "multi_timeframe"],
                )
            # Confidence scaled by displacement strength
            base = 0.55
            range_bonus = max(0.0, (setup["range_vs_atr"] - self.displacement_atr_mult) * 0.08)
            body_bonus = max(0.0, (setup["body_ratio"] - self.body_ratio_min) * 0.4)
            confidence = base + range_bonus + body_bonus
            if confidence > 0.95:
                confidence = 0.95
            if confidence < self.min_confidence:
                confidence = self.min_confidence
            direction = setup["direction"]
            entry = float(setup["entry_price"])
            stop = float(setup["stop_loss"])
            swept = float(setup["swept_level"])
            rationale = (
                f"HTF {self.htf_timeframe} bias: {bias}. "
                f"LTF {self.ltf_timeframe} swept liquidity at {swept:.2f} then displaced {direction} "
                f"(body_ratio={setup['body_ratio']:.2f}, range/ATR={setup['range_vs_atr']:.2f}). "
                f"Entry={entry:.2f}, invalidation={stop:.2f}."
            )
            tags = [
                "multi_timeframe",
                "liquidity_sweep",
                "displacement",
                bias,
                self.htf_timeframe,
                self.ltf_timeframe,
                direction,
            ]
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=direction,
                valid=True,
                confidence=float(confidence),
                rationale=rationale,
                tags=tags,
            )
        except Exception as exc:
            self._logger.exception("evaluate() failed for %s: %s", symbol, exc)
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Strategy evaluation error: {exc}",
                tags=["error"],
            )