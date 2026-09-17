from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xbrusd_d4aee9(EdgeStrategy):
    strategy_id: str = "alpha_xbrusd_d4aee9"
    applicable_symbols: set = {"XBRUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.htf_lookback: int = int(self.settings.get("htf_lookback", 24))
        self.ltf_lookback: int = int(self.settings.get("ltf_lookback", 12))
        self.atr_period: int = int(self.settings.get("atr_period", 14))
        self.min_displacement_ratio: float = float(self.settings.get("min_displacement_ratio", 1.15))
        self.max_sweep_atr_mult: float = float(self.settings.get("max_sweep_atr_mult", 2.5))
        self.min_sweep_atr_mult: float = float(self.settings.get("min_sweep_atr_mult", 0.05))

    def _to_dataframe(self, candles: List[Any]) -> pd.DataFrame:
        records = []
        for c in candles:
            try:
                records.append({
                    "open": float(c.open),
                    "high": float(c.high),
                    "low": float(c.low),
                    "close": float(c.close),
                    "volume": float(c.volume)
                })
            except AttributeError:
                records.append({
                    "open": float(c.get("open", 0.0)),
                    "high": float(c.get("high", 0.0)),
                    "low": float(c.get("low", 0.0)),
                    "close": float(c.get("close", 0.0)),
                    "volume": float(c.get("volume", 0.0))
                })
        df = pd.DataFrame(records)
        return df

    def _compute_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift(1)).abs()
        low_close = (df["low"] - df["close"].shift(1)).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = tr.rolling(window=period, min_periods=1).mean().ffill().bfill()
        return atr

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            # 1. Fetch multi-timeframe candles: H1 for key liquidity levels, M15 for execution displacement
            htf_candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe="H1", limit=100)
            ltf_candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe="M15", limit=100)

            if not htf_candles or len(htf_candles) < self.htf_lookback + 5:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient HTF candle history",
                    tags=["insufficient_data", "htf_missing"]
                )

            if not ltf_candles or len(ltf_candles) < self.atr_period + self.ltf_lookback + 5:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient LTF candle history",
                    tags=["insufficient_data", "ltf_missing"]
                )

            htf_df = self._to_dataframe(htf_candles)
            ltf_df = self._to_dataframe(ltf_candles)

            # 2. Identify HTF Buy-Side and Sell-Side Liquidity levels (excluding active bar)
            htf_prior = htf_df.iloc[:-1]
            htf_bsl = float(htf_prior["high"].tail(self.htf_lookback).max())
            htf_ssl = float(htf_prior["low"].tail(self.htf_lookback).min())

            # 3. Calculate LTF Volatility and Displacement Metrics
            ltf_atr = self._compute_atr(ltf_df, self.atr_period)
            current_atr = float(ltf_atr.iloc[-1])
            if current_atr <= 0.0 or math.isnan(current_atr):
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Invalid LTF ATR calculation",
                    tags=["invalid_metrics"]
                )

            ltf_df["body"] = (ltf_df["close"] - ltf_df["open"]).abs()
            ltf_df["vol_sma"] = ltf_df["volume"].rolling(window=20, min_periods=1).mean().ffill().bfill()

            # Analyze recent LTF action for sweep + displacement
            recent_ltf = ltf_df.tail(self.ltf_lookback)
            latest_bar = ltf_df.iloc[-1]
            prev_bar = ltf_df.iloc[-2]

            max_ltf_high = float(recent_ltf["high"].max())
            min_ltf_low = float(recent_ltf["low"].min())

            # Liquidity Sweep Checks
            swept_bsl = max_ltf_high > htf_bsl
            swept_ssl = min_ltf_low < htf_ssl

            direction = None
            confidence = 0.0
            rationale_elements = []
            tags = ["liquidity_sweep_displacement"]

            # --- Bearish Liquidity Sweep & Displacement (Sell Setup) ---
            if swept_bsl and not swept_ssl:
                sweep_distance = max_ltf_high - htf_bsl
                sweep_atr_ratio = sweep_distance / current_atr

                if self.min_sweep_atr_mult <= sweep_atr_ratio <= self.max_sweep_atr_mult:
                    # Check for displacement: bearish close back below HTF BSL
                    is_displacing = (
                        (latest_bar["close"] < latest_bar["open"] and latest_bar["close"] < htf_bsl) or
                        (prev_bar["close"] < prev_bar["open"] and latest_bar["close"] < htf_bsl)
                    )

                    disp_body = max(float(latest_bar["body"]), float(prev_bar["body"]))
                    disp_ratio = disp_body / current_atr
                    has_power = disp_ratio >= self.min_displacement_ratio

                    # Volume verification
                    disp_vol = max(float(latest_bar["volume"]), float(prev_bar["volume"]))
                    vol_avg = float(latest_bar["vol_sma"])
                    vol_ratio = disp_vol / (vol_avg + 1e-9)

                    if is_displacing and has_power:
                        direction = "sell"
                        # Base confidence 0.60, scaling up with displacement power and volume
                        conf_calc = 0.60 + min(0.20, (disp_ratio - 1.0) * 0.15) + min(0.15, max(0.0, (vol_ratio - 1.0) * 0.10))
                        confidence = float(np.clip(conf_calc, 0.55, 0.95))
                        rationale_elements.append(
                            f"BSL swept at {htf_bsl:.2f} (peak: {max_ltf_high:.2f}, {sweep_atr_ratio:.2f} ATR). "
                            f"Bearish displacement triggered with body/ATR {disp_ratio:.2f} and volume ratio {vol_ratio:.2f}."
                        )
                        tags.extend(["bearish_sweep", "short_displacement"])

            # --- Bullish Liquidity Sweep & Displacement (Buy Setup) ---
            elif swept_ssl and not swept_bsl:
                sweep_distance = htf_ssl - min_ltf_low
                sweep_atr_ratio = sweep_distance / current_atr

                if self.min_sweep_atr_mult <= sweep_atr_ratio <= self.max_sweep_atr_mult:
                    # Check for displacement: bullish close back above HTF SSL
                    is_displacing = (
                        (latest_bar["close"] > latest_bar["open"] and latest_bar["close"] > htf_ssl) or
                        (prev_bar["close"] > prev_bar["open"] and latest_bar["close"] > htf_ssl)
                    )

                    disp_body = max(float(latest_bar["body"]), float(prev_bar["body"]))
                    disp_ratio = disp_body / current_atr
                    has_power = disp_ratio >= self.min_displacement_ratio

                    # Volume verification
                    disp_vol = max(float(latest_bar["volume"]), float(prev_bar["volume"]))
                    vol_avg = float(latest_bar["vol_sma"])
                    vol_ratio = disp_vol / (vol_avg + 1e-9)

                    if is_displacing and has_power:
                        direction = "buy"
                        conf_calc = 0.60 + min(0.20, (disp_ratio - 1.0) * 0.15) + min(0.15, max(0.0, (vol_ratio - 1.0) * 0.10))
                        confidence = float(np.clip(conf_calc, 0.55, 0.95))
                        rationale_elements.append(
                            f"SSL swept at {htf_ssl:.2f} (trough: {min_ltf_low:.2f}, {sweep_atr_ratio:.2f} ATR). "
                            f"Bullish displacement triggered with body/ATR {disp_ratio:.2f} and volume ratio {vol_ratio:.2f}."
                        )
                        tags.extend(["bullish_sweep", "long_displacement"])

            if direction is not None:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=direction,
                    valid=True,
                    confidence=round(confidence, 4),
                    rationale=" | ".join(rationale_elements),
                    tags=tags
                )

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=True,
                confidence=0.0,
                rationale=f"No confirmed liquidity sweep displacement. HTF BSL: {htf_bsl:.2f}, HTF SSL: {htf_ssl:.2f}.",
                tags=["neutral", "monitoring"]
            )

        except Exception as e:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Calculation error: {str(e)}",
                tags=["error"]
            )