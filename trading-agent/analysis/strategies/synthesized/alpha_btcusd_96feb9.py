from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_btcusd_96feb9(EdgeStrategy):
    strategy_id: str = "alpha_btcusd_96feb9"
    applicable_symbols: set = {"BTCUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        cfg = settings or {}
        self.htf_lookback: int = cfg.get("htf_lookback", 24)
        self.atr_period: int = cfg.get("atr_period", 14)
        self.displacement_mult: float = cfg.get("displacement_mult", 1.3)
        self.min_confidence: float = cfg.get("min_confidence", 0.65)

    def _candles_to_df(self, candles: List[Any]) -> pd.DataFrame:
        if not candles or len(candles) == 0:
            return pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume'])
        records = []
        for c in candles:
            try:
                o = float(c.open)
                h = float(c.high)
                l = float(c.low)
                cl = float(c.close)
                v = float(c.volume)
            except (AttributeError, TypeError):
                o = float(c.get('open', 0.0))
                h = float(c.get('high', 0.0))
                l = float(c.get('low', 0.0))
                cl = float(c.get('close', 0.0))
                v = float(c.get('volume', 0.0))
            records.append({'open': o, 'high': h, 'low': l, 'close': cl, 'volume': v})
        df = pd.DataFrame(records)
        return df.ffill().bfill().fillna(0.0)

    def _calculate_atr(self, df: pd.DataFrame, period: int) -> pd.Series:
        high = df['high']
        low = df['low']
        close_prev = df['close'].shift(1).ffill()
        tr1 = high - low
        tr2 = (high - close_prev).abs()
        tr3 = (low - close_prev).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period, min_periods=1).mean()
        return atr.replace([np.inf, -np.inf], np.nan).ffill().bfill().fillna(0.0)

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            if symbol not in self.applicable_symbols:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale=f"Symbol {symbol} not applicable for strategy {self.strategy_id}",
                    tags=["invalid_symbol"]
                )

            htf_frame = settings.get("htf", "H1") if settings else "H1"
            ltf_frame = settings.get("ltf", "M15") if settings else "M15"

            candles_htf = await self.get_historical_candles(session=session, symbol=symbol, timeframe=htf_frame, limit=100)
            candles_ltf = await self.get_historical_candles(session=session, symbol=symbol, timeframe=ltf_frame, limit=100)

            df_htf = self._candles_to_df(candles_htf)
            df_ltf = self._candles_to_df(candles_ltf)

            if len(df_htf) < 30:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale=f"Insufficient HTF candle data: {len(df_htf)} bars",
                    tags=["insufficient_data"]
                )

            if len(df_ltf) < 20:
                df_ltf = df_htf

            htf_window = min(self.htf_lookback, len(df_htf) - 2)
            if htf_window < 5:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="HTF lookback window insufficient",
                    tags=["insufficient_data"]
                )

            htf_subset = df_htf.iloc[-htf_window - 2:-2]
            buyside_liquidity = float(htf_subset['high'].max())
            sellside_liquidity = float(htf_subset['low'].min())

            atr_series = self._calculate_atr(df_ltf, period=self.atr_period)
            vol_sma_series = df_ltf['volume'].rolling(window=20, min_periods=1).mean().ffill().fillna(0.0)

            curr_candle = df_ltf.iloc[-1]
            recent_candles = df_ltf.iloc[-4:]

            curr_high = float(curr_candle['high'])
            curr_low = float(curr_candle['low'])
            curr_close = float(curr_candle['close'])
            curr_open = float(curr_candle['open'])
            curr_vol = float(curr_candle['volume'])
            curr_atr = float(atr_series.iloc[-1])
            curr_vol_sma = float(vol_sma_series.iloc[-1])

            recent_min_low = float(recent_candles['low'].min())
            recent_max_high = float(recent_candles['high'].max())

            candle_range = curr_high - curr_low

            direction = None
            confidence = 0.0
            rationale = "No liquidity sweep displacement detected"
            tags = ["liquidity_sweep", symbol]

            swept_sellside = recent_min_low < sellside_liquidity
            is_bullish_displacement = (
                swept_sellside and
                curr_close > curr_open and
                candle_range > self.displacement_mult * curr_atr and
                (curr_close - curr_low) / (candle_range + 1e-8) >= 0.60
            )

            swept_buyside = recent_max_high > buyside_liquidity
            is_bearish_displacement = (
                swept_buyside and
                curr_close < curr_open and
                candle_range > self.displacement_mult * curr_atr and
                (curr_high - curr_close) / (candle_range + 1e-8) >= 0.60
            )

            if is_bullish_displacement and not is_bearish_displacement:
                direction = "buy"
                conf = 0.60
                if candle_range > 1.8 * curr_atr:
                    conf += 0.10
                if curr_vol_sma > 0 and curr_vol > 1.3 * curr_vol_sma:
                    conf += 0.10
                if (curr_close - curr_low) / (candle_range + 1e-8) >= 0.75:
                    conf += 0.10
                confidence = min(0.95, conf)
                rationale = (f"Bullish liquidity sweep below {sellside_liquidity:.2f} "
                             f"with displacement ATR mult {candle_range / (curr_atr + 1e-8):.2f}")
                tags.extend(["bullish_sweep", "displacement_buy"])

            elif is_bearish_displacement and not is_bullish_displacement:
                direction = "sell"
                conf = 0.60
                if candle_range > 1.8 * curr_atr:
                    conf += 0.10
                if curr_vol_sma > 0 and curr_vol > 1.3 * curr_vol_sma:
                    conf += 0.10
                if (curr_high - curr_close) / (candle_range + 1e-8) >= 0.75:
                    conf += 0.10
                confidence = min(0.95, conf)
                rationale = (f"Bearish liquidity sweep above {buyside_liquidity:.2f} "
                             f"with displacement ATR mult {candle_range / (curr_atr + 1e-8):.2f}")
                tags.extend(["bearish_sweep", "displacement_sell"])

            is_valid = direction is not None and confidence >= self.min_confidence

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=direction if is_valid else None,
                valid=is_valid,
                confidence=confidence if is_valid else 0.0,
                rationale=rationale if is_valid else f"Signal invalid or low confidence: {confidence:.2f} < {self.min_confidence}",
                tags=tags
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
