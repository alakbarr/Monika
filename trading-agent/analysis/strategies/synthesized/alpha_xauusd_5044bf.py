from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xauusd_5044bf(EdgeStrategy):
    strategy_id: str = "alpha_xauusd_5044bf"
    applicable_symbols: set = {"XAUUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.base_period: int = int(self.settings.get("base_period", 24))
        self.vol_ma_period: int = int(self.settings.get("vol_ma_period", 20))
        self.rvol_threshold: float = float(self.settings.get("rvol_threshold", 1.25))
        self.atr_period: int = int(self.settings.get("atr_period", 14))
        self.timeframe: str = str(self.settings.get("timeframe", "H1"))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        if symbol not in self.applicable_symbols:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale="Symbol not applicable for Volume-weighted dynamic Donchian strategy.",
                tags=["ineligible_symbol"]
            )

        limit_needed = max(self.base_period, self.vol_ma_period, self.atr_period) + 30
        candles = await self.get_historical_candles(
            session=session,
            symbol=symbol,
            timeframe=self.timeframe,
            limit=limit_needed
        )

        if not candles or len(candles) < max(self.base_period, self.vol_ma_period, self.atr_period) + 5:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale="Insufficient historical candle data for evaluation.",
                tags=["insufficient_data"]
            )

        highs = np.array([float(c.high) for c in candles], dtype=np.float64)
        lows = np.array([float(c.low) for c in candles], dtype=np.float64)
        closes = np.array([float(c.close) for c in candles], dtype=np.float64)
        volumes = np.array([float(c.volume) for c in candles], dtype=np.float64)

        # 1. Compute ATR for volatility normalisation
        tr_list: List[float] = []
        for i in range(1, len(candles)):
            hl = highs[i] - lows[i]
            hc = abs(highs[i] - closes[i - 1])
            lc = abs(lows[i] - closes[i - 1])
            tr_list.append(max(hl, hc, lc))
        
        atr_series = pd.Series(tr_list).rolling(window=self.atr_period).mean().to_numpy()
        current_atr = atr_series[-1] if len(atr_series) > 0 and not np.isnan(atr_series[-1]) else (highs[-1] - lows[-1])

        # 2. Volume Analysis & Dynamic Period Adaptation
        vol_series = pd.Series(volumes)
        vol_ma = vol_series.rolling(window=self.vol_ma_period).mean().to_numpy()
        current_vol_ma = vol_ma[-1] if not np.isnan(vol_ma[-1]) and vol_ma[-1] > 0 else 1.0
        
        current_vol = volumes[-1]
        rvol = current_vol / current_vol_ma if current_vol_ma > 0 else 1.0

        # Adjust lookback window dynamically based on volume intensity
        # High volume compresses lookback to react faster to sudden institutional breakouts
        vol_factor = np.clip(rvol, 0.6, 1.8)
        dynamic_period = int(np.clip(round(self.base_period / vol_factor), 10, self.base_period * 2))

        # 3. Dynamic Donchian Channels (computed on preceding bars excluding current bar)
        prior_highs = highs[-(dynamic_period + 1):-1]
        prior_lows = lows[-(dynamic_period + 1):-1]
        prior_volumes = volumes[-(dynamic_period + 1):-1]

        if len(prior_highs) < dynamic_period:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale="Dynamic lookback window calculation failed due to size constraints.",
                tags=["calc_error"]
            )

        donchian_high = np.max(prior_highs)
        donchian_low = np.min(prior_lows)

        # Volume-weighted reference level
        total_prior_vol = np.sum(prior_volumes)
        if total_prior_vol > 0:
            vw_midpoint = float(np.sum((prior_highs + prior_lows) / 2.0 * prior_volumes) / total_prior_vol)
        else:
            vw_midpoint = float((donchian_high + donchian_low) / 2.0)

        current_close = closes[-1]
        current_open = float(candles[-1].open)

        # 4. Expansion & Breakout Detection
        channel_width = donchian_high - donchian_low
        normalized_width = channel_width / current_atr if current_atr > 0 else 1.0

        direction: Optional[str] = None
        confidence: float = 0.0
        reasons: List[str] = []
        tags: List[str] = []

        is_bullish_breakout = (current_close > donchian_high) and (current_close > current_open)
        is_bearish_breakout = (current_close < donchian_low) and (current_close < current_open)

        if is_bullish_breakout and rvol >= self.rvol_threshold:
            direction = "buy"
            breakout_magnitude = (current_close - donchian_high) / current_atr if current_atr > 0 else 0.5
            base_conf = 0.60 + min(0.15, (rvol - self.rvol_threshold) * 0.1) + min(0.15, breakout_magnitude * 0.1)
            confidence = float(np.clip(base_conf, 0.55, 0.90))
            reasons.append(f"Bullish Dynamic Donchian expansion above {donchian_high:.2f}")
            reasons.append(f"Volume surge RVOL: {rvol:.2f}x (threshold: {self.rvol_threshold:.2f}x)")
            reasons.append(f"VW-Midpoint: {vw_midpoint:.2f}, Dynamic Lookback: {dynamic_period} bars")
            tags.extend(["donchian_expansion", "bullish_breakout", "high_volume"])

        elif is_bearish_breakout and rvol >= self.rvol_threshold:
            direction = "sell"
            breakout_magnitude = (donchian_low - current_close) / current_atr if current_atr > 0 else 0.5
            base_conf = 0.60 + min(0.15, (rvol - self.rvol_threshold) * 0.1) + min(0.15, breakout_magnitude * 0.1)
            confidence = float(np.clip(base_conf, 0.55, 0.90))
            reasons.append(f"Bearish Dynamic Donchian expansion below {donchian_low:.2f}")
            reasons.append(f"Volume surge RVOL: {rvol:.2f}x (threshold: {self.rvol_threshold:.2f}x)")
            reasons.append(f"VW-Midpoint: {vw_midpoint:.2f}, Dynamic Lookback: {dynamic_period} bars")
            tags.extend(["donchian_expansion", "bearish_breakout", "high_volume"])

        valid = direction is not None

        if not valid:
            rationale = (
                f"Consolidation inside channel [{donchian_low:.2f} - {donchian_high:.2f}] "
                f"or insufficient volume expansion (RVOL: {rvol:.2f}x)."
            )
            tags.append("neutral_market")
        else:
            rationale = " | ".join(reasons)

        return EdgeSignal(
            strategy_id=self.strategy_id,
            symbol=symbol,
            direction=direction,
            valid=valid,
            confidence=confidence,
            rationale=rationale,
            tags=tags
        )