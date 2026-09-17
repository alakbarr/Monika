from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_audusd_abe552(EdgeStrategy):
    strategy_id: str = "alpha_audusd_abe552"
    applicable_symbols: set = {"AUDUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.htf_swing_lookback: int = int(self.settings.get("htf_swing_lookback", 20))
        self.sweep_threshold_pips: float = float(self.settings.get("sweep_threshold_pips", 0.0003))
        self.displacement_multiplier: float = float(self.settings.get("displacement_multiplier", 1.4))
        self.atr_period: int = int(self.settings.get("atr_period", 14))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            if symbol.upper() not in self.applicable_symbols:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale=f"Symbol {symbol} not supported by this strategy.",
                    tags=["unsupported_symbol"]
                )

            # Fetch Higher Timeframe (H4) and Execution Timeframe (M15) candles
            htf_candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe='H4', limit=60)
            ltf_candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe='M15', limit=100)

            if not htf_candles or len(htf_candles) < self.htf_swing_lookback + 5:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient HTF candle data for liquidity level detection.",
                    tags=["insufficient_data"]
                )

            if not ltf_candles or len(ltf_candles) < self.atr_period + 10:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient LTF candle data for displacement confirmation.",
                    tags=["insufficient_data"]
                )

            # Parse HTF data into DataFrame
            htf_data = []
            for c in htf_candles:
                htf_data.append({
                    "open": float(c.open if hasattr(c, "open") else c["open"]),
                    "high": float(c.high if hasattr(c, "high") else c["high"]),
                    "low": float(c.low if hasattr(c, "low") else c["low"]),
                    "close": float(c.close if hasattr(c, "close") else c["close"]),
                })
            df_htf = pd.DataFrame(htf_data)

            # Parse LTF data into DataFrame
            ltf_data = []
            for c in ltf_candles:
                ltf_data.append({
                    "open": float(c.open if hasattr(c, "open") else c["open"]),
                    "high": float(c.high if hasattr(c, "high") else c["high"]),
                    "low": float(c.low if hasattr(c, "low") else c["low"]),
                    "close": float(c.close if hasattr(c, "close") else c["close"]),
                })
            df_ltf = pd.DataFrame(ltf_data)

            # Clean and sanitize data
            df_htf = df_htf.replace([np.inf, -np.inf], np.nan).ffill().bfill()
            df_ltf = df_ltf.replace([np.inf, -np.inf], np.nan).ffill().bfill()

            # Calculate HTF Liquidity Pools (Swing Highs and Swing Lows)
            recent_htf = df_htf.iloc[:-1]  # Exclude unclosed/current HTF candle
            swing_high = float(recent_htf['high'].tail(self.htf_swing_lookback).max())
            swing_low = float(recent_htf['low'].tail(self.htf_swing_lookback).min())

            # LTF ATR Calculation
            high_low = df_ltf['high'] - df_ltf['low']
            high_close_prev = (df_ltf['high'] - df_ltf['close'].shift(1)).abs()
            low_close_prev = (df_ltf['low'] - df_ltf['close'].shift(1)).abs()
            true_range = pd.concat([high_low, high_close_prev, low_close_prev], axis=1).max(axis=1)
            atr_series = true_range.rolling(window=self.atr_period, min_periods=1).mean().fillna(0.0010)

            curr_atr = float(atr_series.iloc[-1])
            if curr_atr <= 0:
                curr_atr = 0.0005

            latest = df_ltf.iloc[-1]
            prev1 = df_ltf.iloc[-2]
            prev2 = df_ltf.iloc[-3]

            direction = None
            confidence = 0.0
            rationale_parts = []
            tags = ["liquidity_sweep", "displacement"]

            # Evaluate Bullish Liquidity Sweep & Displacement
            # Scenario: Price sweeps below HTF Swing Low, then prints a strong bullish displacement candle
            recent_lows = df_ltf['low'].iloc[-4:].min()
            sweep_low = recent_lows <= (swing_low + self.sweep_threshold_pips)
            bullish_body = latest['close'] - latest['open']
            bullish_range = latest['high'] - latest['low']
            is_bullish_displacement = (
                bullish_body > (curr_atr * self.displacement_multiplier) and
                latest['close'] > swing_low and
                (latest['close'] - latest['low']) / (bullish_range if bullish_range > 0 else 1.0) >= 0.65
            )

            # Evaluate Bearish Liquidity Sweep & Displacement
            # Scenario: Price sweeps above HTF Swing High, then prints a strong bearish displacement candle
            recent_highs = df_ltf['high'].iloc[-4:].max()
            sweep_high = recent_highs >= (swing_high - self.sweep_threshold_pips)
            bearish_body = latest['open'] - latest['close']
            bearish_range = latest['high'] - latest['low']
            is_bearish_displacement = (
                bearish_body > (curr_atr * self.displacement_multiplier) and
                latest['close'] < swing_high and
                (latest['high'] - latest['close']) / (bearish_range if bearish_range > 0 else 1.0) >= 0.65
            )

            if sweep_low and is_bullish_displacement:
                direction = "buy"
                disp_ratio = bullish_body / curr_atr
                base_conf = 0.65 + min(0.25, (disp_ratio - self.displacement_multiplier) * 0.15)
                confidence = float(np.clip(base_conf, 0.50, 0.95))
                rationale_parts.append(
                    f"Bullish liquidity sweep below H4 swing low ({swing_low:.5f}) with strong M15 displacement "
                    f"(body: {bullish_body:.5f}, ATR: {curr_atr:.5f}, ratio: {disp_ratio:.2f})."
                )
                tags.append("bullish_displacement")

            elif sweep_high and is_bearish_displacement:
                direction = "sell"
                disp_ratio = bearish_body / curr_atr
                base_conf = 0.65 + min(0.25, (disp_ratio - self.displacement_multiplier) * 0.15)
                confidence = float(np.clip(base_conf, 0.50, 0.95))
                rationale_parts.append(
                    f"Bearish liquidity sweep above H4 swing high ({swing_high:.5f}) with strong M15 displacement "
                    f"(body: {bearish_body:.5f}, ATR: {curr_atr:.5f}, ratio: {disp_ratio:.2f})."
                )
                tags.append("bearish_displacement")

            if direction is not None:
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
                rationale=f"No multi-timeframe liquidity sweep displacement pattern identified on {symbol}.",
                tags=["no_setup"]
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