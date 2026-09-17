from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xauusd_59cf5d(EdgeStrategy):
    strategy_id: str = "alpha_xauusd_59cf5d"
    applicable_symbols: set = {"XAUUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        cfg = settings or {}
        self.htf_lookback: int = int(cfg.get("htf_lookback", 30))
        self.ltf_sweep_window: int = int(cfg.get("ltf_sweep_window", 4))
        self.displacement_mult: float = float(cfg.get("displacement_mult", 1.4))
        self.atr_period: int = int(cfg.get("atr_period", 14))

    def _to_dataframe(self, candles: List[Any]) -> pd.DataFrame:
        if not candles:
            return pd.DataFrame()
        records = []
        for c in candles:
            try:
                records.append({
                    "open": float(c.open),
                    "high": float(c.high),
                    "low": float(c.low),
                    "close": float(c.close),
                    "volume": float(c.volume) if hasattr(c, "volume") else 0.0
                })
            except (AttributeError, TypeError):
                if isinstance(c, dict):
                    records.append({
                        "open": float(c.get("open", 0.0)),
                        "high": float(c.get("high", 0.0)),
                        "low": float(c.get("low", 0.0)),
                        "close": float(c.get("close", 0.0)),
                        "volume": float(c.get("volume", 0.0) or 0.0)
                    })
        df = pd.DataFrame(records)
        return df

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            if symbol.upper() not in self.applicable_symbols:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale=f"Symbol {symbol} not applicable for this strategy.",
                    tags=["unsupported_symbol"]
                )

            # 1. Fetch Higher Timeframe (H1) and Lower Timeframe (M15) candles
            htf_candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe="H1", limit=100)
            ltf_candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe="M15", limit=100)

            df_htf = self._to_dataframe(htf_candles)
            df_ltf = self._to_dataframe(ltf_candles)

            if len(df_htf) < self.htf_lookback + 2 or len(df_ltf) < self.atr_period + 5:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient historical candle depth for MTF calculation.",
                    tags=["insufficient_data"]
                )

            # 2. Extract HTF Key Liquidity Levels (excluding most recent unclosed bar)
            htf_window = df_htf.iloc[-(self.htf_lookback + 1):-1]
            htf_swing_high = float(htf_window["high"].max())
            htf_swing_low = float(htf_window["low"].min())

            # 3. Calculate LTF Metrics (ATR and Body Sizes)
            df_ltf = df_ltf.copy()
            df_ltf["body"] = (df_ltf["close"] - df_ltf["open"]).abs()
            df_ltf["tr0"] = (df_ltf["high"] - df_ltf["low"]).abs()
            df_ltf["tr1"] = (df_ltf["high"] - df_ltf["close"].shift(1)).abs()
            df_ltf["tr2"] = (df_ltf["low"] - df_ltf["close"].shift(1)).abs()
            df_ltf["tr"] = df_ltf[["tr0", "tr1", "tr2"]].max(axis=1)
            df_ltf["atr"] = df_ltf["tr"].rolling(window=self.atr_period, min_periods=1).mean()
            df_ltf["avg_body"] = df_ltf["body"].rolling(window=self.atr_period, min_periods=1).mean()
            df_ltf["avg_volume"] = df_ltf["volume"].rolling(window=self.atr_period, min_periods=1).mean()

            # Sanitize NaNs
            df_ltf = df_ltf.ffill().bfill().fillna(0.0)

            latest_ltf = df_ltf.iloc[-1]
            prev_ltf = df_ltf.iloc[-2]
            recent_ltf_window = df_ltf.iloc[-self.ltf_sweep_window:]

            curr_close = float(latest_ltf["close"])
            curr_open = float(latest_ltf["open"])
            curr_high = float(latest_ltf["high"])
            curr_low = float(latest_ltf["low"])
            curr_body = float(latest_ltf["body"])
            curr_volume = float(latest_ltf["volume"])
            avg_body = float(latest_ltf["avg_body"]) if float(latest_ltf["avg_body"]) > 0 else 1.0
            avg_vol = float(latest_ltf["avg_volume"]) if float(latest_ltf["avg_volume"]) > 0 else 1.0
            atr = float(latest_ltf["atr"]) if float(latest_ltf["atr"]) > 0 else 1.0

            recent_min_low = float(recent_ltf_window["low"].min())
            recent_max_high = float(recent_ltf_window["high"].max())

            direction = None
            rationale_parts = []
            confidence = 0.0

            # 4. Long Setup: Sell-side Liquidity Sweep + Bullish Displacement
            # Sweep: Recent LTF pierced below HTF swing low
            # Rejection: Current candle closes back ABOVE the HTF swing low
            # Displacement: Strong bullish body (> displacement_mult * avg_body) and close in top 30% of range
            range_span = max(curr_high - curr_low, 1e-6)
            close_position = (curr_close - curr_low) / range_span

            bullish_sweep = recent_min_low < htf_swing_low
            bullish_rejection = curr_close > htf_swing_low
            bullish_displacement = (
                curr_close > curr_open
                and curr_body >= (avg_body * self.displacement_mult)
                and close_position >= 0.68
                and curr_close > float(prev_ltf["high"])
            )

            # 5. Short Setup: Buy-side Liquidity Sweep + Bearish Displacement
            # Sweep: Recent LTF pierced above HTF swing high
            # Rejection: Current candle closes back BELOW the HTF swing high
            # Displacement: Strong bearish body (> displacement_mult * avg_body) and close in bottom 30% of range
            bearish_sweep = recent_max_high > htf_swing_high
            bearish_rejection = curr_close < htf_swing_high
            bearish_displacement = (
                curr_close < curr_open
                and curr_body >= (avg_body * self.displacement_mult)
                and close_position <= 0.32
                and curr_close < float(prev_ltf["low"])
            )

            if bullish_sweep and bullish_rejection and bullish_displacement:
                direction = "buy"
                confidence = 0.70
                if curr_body >= 2.0 * avg_body:
                    confidence += 0.08
                if curr_volume >= 1.3 * avg_vol:
                    confidence += 0.07
                confidence = min(0.92, confidence)
                rationale_parts.append(
                    f"XAUUSD H1 liquidity sweep below {htf_swing_low:.2f} (swept to {recent_min_low:.2f}) "
                    f"with bullish displacement candle (body={curr_body:.2f} vs avg={avg_body:.2f}, close={curr_close:.2f})."
                )

            elif bearish_sweep and bearish_rejection and bearish_displacement:
                direction = "sell"
                confidence = 0.70
                if curr_body >= 2.0 * avg_body:
                    confidence += 0.08
                if curr_volume >= 1.3 * avg_vol:
                    confidence += 0.07
                confidence = min(0.92, confidence)
                rationale_parts.append(
                    f"XAUUSD H1 liquidity sweep above {htf_swing_high:.2f} (swept to {recent_max_high:.2f}) "
                    f"with bearish displacement candle (body={curr_body:.2f} vs avg={avg_body:.2f}, close={curr_close:.2f})."
                )

            if direction is not None:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=direction,
                    valid=True,
                    confidence=round(confidence, 3),
                    rationale=" | ".join(rationale_parts),
                    tags=["liquidity_sweep", "displacement", "orderblock", "xauusd", "mtf"]
                )

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"No HTF liquidity sweep displacement pattern triggered on {symbol}.",
                tags=["neutral", "no_sweep"]
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
