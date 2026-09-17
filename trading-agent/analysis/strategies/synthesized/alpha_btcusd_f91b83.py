from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_btcusd_f91b83(EdgeStrategy):
    strategy_id: str = "alpha_btcusd_f91b83"
    applicable_symbols: set = {"BTCUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        cfg = settings or {}
        self.htf_timeframe: str = str(cfg.get("htf_timeframe", "H1"))
        self.ltf_timeframe: str = str(cfg.get("ltf_timeframe", "M15"))
        self.htf_swing_window: int = int(cfg.get("htf_swing_window", 5))
        self.ltf_swing_window: int = int(cfg.get("ltf_swing_window", 3))
        self.sweep_lookback: int = int(cfg.get("sweep_lookback", 6))
        self.atr_period: int = int(cfg.get("atr_period", 14))
        self.displacement_body_ratio: float = float(cfg.get("displacement_body_ratio", 0.55))
        self.displacement_atr_mult: float = float(cfg.get("displacement_atr_mult", 1.25))
        self.volume_mult_threshold: float = float(cfg.get("volume_mult_threshold", 1.20))

    def _candles_to_df(self, candles: List[Any]) -> pd.DataFrame:
        if not candles:
            return pd.DataFrame()
        records: List[Dict[str, float]] = []
        for c in candles:
            if isinstance(c, dict):
                records.append({
                    "open": float(c.get("open", 0.0)),
                    "high": float(c.get("high", 0.0)),
                    "low": float(c.get("low", 0.0)),
                    "close": float(c.get("close", 0.0)),
                    "volume": float(c.get("volume", 0.0)),
                })
            else:
                records.append({
                    "open": float(c.open),
                    "high": float(c.high),
                    "low": float(c.low),
                    "close": float(c.close),
                    "volume": float(c.volume),
                })
        return pd.DataFrame(records)

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            if symbol not in self.applicable_symbols:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale=f"Symbol {symbol} not supported",
                    tags=["unsupported_symbol"]
                )

            htf_candles = await self.get_historical_candles(
                session=session, symbol=symbol, timeframe=self.htf_timeframe, limit=80
            )
            ltf_candles = await self.get_historical_candles(
                session=session, symbol=symbol, timeframe=self.ltf_timeframe, limit=100
            )

            if not htf_candles or len(htf_candles) < 30 or not ltf_candles or len(ltf_candles) < 40:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient historical candle data for multi-timeframe evaluation",
                    tags=["insufficient_data"]
                )

            htf_df = self._candles_to_df(htf_candles)
            ltf_df = self._candles_to_df(ltf_candles)

            if htf_df.empty or ltf_df.empty:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Failed to structure candle dataframes",
                    tags=["data_parse_error"]
                )

            # 1. Identify HTF Liquidity Pools (Swing Highs and Lows)
            k_htf = self.htf_swing_window
            htf_len = len(htf_df)
            htf_swing_highs: List[float] = []
            htf_swing_lows: List[float] = []

            for i in range(k_htf, htf_len - 1):
                high_val = htf_df["high"].iloc[i]
                low_val = htf_df["low"].iloc[i]
                is_high = True
                is_low = True
                for j in range(i - k_htf, i + k_htf + 1):
                    if j != i and 0 <= j < htf_len:
                        if htf_df["high"].iloc[j] >= high_val:
                            is_high = False
                        if htf_df["low"].iloc[j] <= low_val:
                            is_low = False
                if is_high:
                    htf_swing_highs.append(high_val)
                if is_low:
                    htf_swing_lows.append(low_val)

            # Consider only the most recent key liquidity levels
            recent_htf_highs = htf_swing_highs[-6:] if htf_swing_highs else []
            recent_htf_lows = htf_swing_lows[-6:] if htf_swing_lows else []

            if not recent_htf_highs and not recent_htf_lows:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="No clear HTF swing liquidity levels identified",
                    tags=["no_htf_levels"]
                )

            # 2. LTF Calculations: ATR, Volume Baseline, Candle Dynamics
            ltf_high = ltf_df["high"]
            ltf_low = ltf_df["low"]
            ltf_close = ltf_df["close"]
            ltf_open = ltf_df["open"]
            ltf_volume = ltf_df["volume"]

            tr1 = ltf_high - ltf_low
            tr2 = (ltf_high - ltf_close.shift(1)).abs()
            tr3 = (ltf_low - ltf_close.shift(1)).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr = tr.rolling(window=self.atr_period, min_periods=1).mean().ffill().bfill().fillna(1.0)
            vol_sma = ltf_volume.rolling(window=20, min_periods=1).mean().ffill().bfill().fillna(1.0)

            curr_idx = len(ltf_df) - 1
            curr_close = float(ltf_close.iloc[curr_idx])
            curr_open = float(ltf_open.iloc[curr_idx])
            curr_high = float(ltf_high.iloc[curr_idx])
            curr_low = float(ltf_low.iloc[curr_idx])
            curr_vol = float(ltf_volume.iloc[curr_idx])
            curr_atr = float(atr.iloc[curr_idx])
            avg_vol = float(vol_sma.iloc[curr_idx])

            # 3. Liquidity Sweep Scan across lookback window
            lookback_start = max(0, curr_idx - self.sweep_lookback)
            bullish_sweep_detected = False
            bearish_sweep_detected = False
            swept_level = 0.0

            # Check Bullish Sweep: Low dipped below HTF Swing Low but LTF closed back above it
            for level in recent_htf_lows:
                for idx in range(lookback_start, curr_idx + 1):
                    bar_low = float(ltf_low.iloc[idx])
                    bar_close = float(ltf_close.iloc[idx])
                    if bar_low < level and (bar_close >= level or curr_close > level):
                        bullish_sweep_detected = True
                        swept_level = level
                        break
                if bullish_sweep_detected:
                    break

            # Check Bearish Sweep: High spiked above HTF Swing High but LTF closed back below it
            for level in recent_htf_highs:
                for idx in range(lookback_start, curr_idx + 1):
                    bar_high = float(ltf_high.iloc[idx])
                    bar_close = float(ltf_close.iloc[idx])
                    if bar_high > level and (bar_close <= level or curr_close < level):
                        bearish_sweep_detected = True
                        swept_level = level
                        break
                if bearish_sweep_detected:
                    break

            # 4. Displacement Metrics
            candle_range = max(curr_high - curr_low, 1e-6)
            candle_body = abs(curr_close - curr_open)
            body_ratio = candle_body / candle_range
            is_large_range = candle_range >= (self.displacement_atr_mult * curr_atr)
            is_volume_spike = curr_vol >= (self.volume_mult_threshold * avg_vol)
            has_momentum_body = body_ratio >= self.displacement_body_ratio

            # Check Fair Value Gap (FVG) creation on LTF
            bullish_fvg = False
            bearish_fvg = False
            if curr_idx >= 2:
                # Bullish FVG: Current low is higher than candle [i-2] high
                if float(ltf_low.iloc[curr_idx]) > float(ltf_high.iloc[curr_idx - 2]):
                    bullish_fvg = True
                # Bearish FVG: Current high is lower than candle [i-2] low
                if float(ltf_high.iloc[curr_idx]) < float(ltf_low.iloc[curr_idx - 2]):
                    bearish_fvg = True

            # Structure Displacement Checks
            direction: Optional[str] = None
            confidence: float = 0.0
            rationale_parts: List[str] = []
            tags: List[str] = ["liquidity_sweep_displacement"]

            # Bullish Displacement Setup
            if bullish_sweep_detected and curr_close > curr_open:
                displacement_valid = has_momentum_body and (is_large_range or is_volume_spike or bullish_fvg)
                if displacement_valid:
                    direction = "buy"
                    base_conf = 0.68
                    if is_volume_spike:
                        base_conf += 0.08
                        rationale_parts.append(f"Volume spike ({curr_vol:.1f} vs avg {avg_vol:.1f})")
                    if bullish_fvg:
                        base_conf += 0.08
                        rationale_parts.append("Bullish FVG displacement formed")
                    if is_large_range:
                        base_conf += 0.06
                        rationale_parts.append(f"Strong ATR expansion ({candle_range:.1f} >= {curr_atr * self.displacement_atr_mult:.1f})")
                    confidence = min(0.92, base_conf)
                    rationale_parts.append(f"Bullish liquidity sweep of HTF low at {swept_level:.2f} with strong LTF displacement")
                    tags.extend(["bullish_sweep", "fvg_displacement" if bullish_fvg else "body_displacement"])

            # Bearish Displacement Setup
            elif bearish_sweep_detected and curr_close < curr_open:
                displacement_valid = has_momentum_body and (is_large_range or is_volume_spike or bearish_fvg)
                if displacement_valid:
                    direction = "sell"
                    base_conf = 0.68
                    if is_volume_spike:
                        base_conf += 0.08
                        rationale_parts.append(f"Volume spike ({curr_vol:.1f} vs avg {avg_vol:.1f})")
                    if bearish_fvg:
                        base_conf += 0.08
                        rationale_parts.append("Bearish FVG displacement formed")
                    if is_large_range:
                        base_conf += 0.06
                        rationale_parts.append(f"Strong ATR expansion ({candle_range:.1f} >= {curr_atr * self.displacement_atr_mult:.1f})")
                    confidence = min(0.92, base_conf)
                    rationale_parts.append(f"Bearish liquidity sweep of HTF high at {swept_level:.2f} with strong LTF displacement")
                    tags.extend(["bearish_sweep", "fvg_displacement" if bearish_fvg else "body_displacement"])

            if direction is not None:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=direction,
                    valid=True,
                    confidence=round(confidence, 4),
                    rationale="; ".join(rationale_parts),
                    tags=tags
                )

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale="No HTF liquidity sweep with LTF displacement criteria met",
                tags=["neutral", "monitoring"]
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
