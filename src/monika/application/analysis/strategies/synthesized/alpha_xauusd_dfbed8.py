from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xauusd_dfbed8(EdgeStrategy):
    strategy_id: str = "alpha_xauusd_dfbed8"
    applicable_symbols: set = {"XAUUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.timeframe = self.settings.get("timeframe", "H1")
        self.limit = self.settings.get("limit", 100)
        self.donchian_period = self.settings.get("donchian_period", 20)
        self.atr_period = self.settings.get("atr_period", 14)
        self.volume_ma_period = self.settings.get("volume_ma_period", 20)
        self.min_vol_ratio = self.settings.get("min_vol_ratio", 1.1)
        self.expansion_threshold = self.settings.get("expansion_threshold", 1.05)

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
                    tags=["incompatible_symbol"]
                )

            merged_settings = {**self.settings, **(settings or {})}
            timeframe = merged_settings.get("timeframe", self.timeframe)
            limit = int(merged_settings.get("limit", self.limit))
            donchian_period = int(merged_settings.get("donchian_period", self.donchian_period))
            atr_period = int(merged_settings.get("atr_period", self.atr_period))
            vol_period = int(merged_settings.get("volume_ma_period", self.volume_ma_period))
            min_vol_ratio = float(merged_settings.get("min_vol_ratio", self.min_vol_ratio))
            expansion_threshold = float(merged_settings.get("expansion_threshold", self.expansion_threshold))

            candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe=timeframe, limit=limit)
            min_required = max(donchian_period, atr_period, vol_period) + 5
            if not candles or len(candles) < min_required:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale=f"Insufficient candle data (got {len(candles) if candles else 0}, required {min_required})",
                    tags=["insufficient_data"]
                )

            records = []
            for c in candles:
                if hasattr(c, 'close'):
                    records.append({
                        'open': float(c.open),
                        'high': float(c.high),
                        'low': float(c.low),
                        'close': float(c.close),
                        'volume': float(getattr(c, 'volume', 1.0) or 1.0)
                    })
                elif isinstance(c, dict):
                    records.append({
                        'open': float(c.get('open', 0.0)),
                        'high': float(c.get('high', 0.0)),
                        'low': float(c.get('low', 0.0)),
                        'close': float(c.get('close', 0.0)),
                        'volume': float(c.get('volume', 1.0) or 1.0)
                    })

            df = pd.DataFrame(records)
            if len(df) < min_required:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="DataFrame length insufficient after parsing records",
                    tags=["insufficient_data"]
                )

            # Data cleaning and numerical stabilization
            df['high'] = df['high'].replace([np.inf, -np.inf], np.nan).ffill().bfill()
            df['low'] = df['low'].replace([np.inf, -np.inf], np.nan).ffill().bfill()
            df['close'] = df['close'].replace([np.inf, -np.inf], np.nan).ffill().bfill()
            df['volume'] = df['volume'].replace([np.inf, -np.inf], np.nan).fillna(1.0)
            df['volume'] = df['volume'].apply(lambda x: 1.0 if x <= 0 else x)

            # ATR Calculation
            prev_close = df['close'].shift(1)
            tr1 = df['high'] - df['low']
            tr2 = (df['high'] - prev_close).abs()
            tr3 = (df['low'] - prev_close).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr = tr.rolling(window=atr_period, min_periods=1).mean().ffill().bfill()

            # Shifted Donchian Channels to detect breakout relative to preceding channel bounds
            donchian_high = df['high'].shift(1).rolling(window=donchian_period, min_periods=donchian_period).max()
            donchian_low = df['low'].shift(1).rolling(window=donchian_period, min_periods=donchian_period).min()

            channel_width = donchian_high - donchian_low
            avg_channel_width = channel_width.rolling(window=donchian_period, min_periods=1).mean()
            expansion_ratio = (channel_width / avg_channel_width.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).ffill().bfill().fillna(1.0)

            # Volume-Weighted Dynamic Multipliers
            vol_ma = df['volume'].rolling(window=vol_period, min_periods=1).mean()
            vol_ratio = (df['volume'] / vol_ma.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).ffill().bfill().fillna(1.0)

            # Moving averages for trend context confirmation
            ema_20 = df['close'].ewm(span=20, adjust=False).mean()
            ema_50 = df['close'].ewm(span=50, adjust=False).mean()

            curr_close = float(df['close'].iloc[-1])
            prev_donchian_high = float(donchian_high.iloc[-1])
            prev_donchian_low = float(donchian_low.iloc[-1])
            curr_vol_ratio = float(vol_ratio.iloc[-1])
            curr_expansion = float(expansion_ratio.iloc[-1])
            curr_ema20 = float(ema_20.iloc[-1])
            curr_ema50 = float(ema_50.iloc[-1])

            if pd.isna(prev_donchian_high) or pd.isna(prev_donchian_low):
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Donchian channel calculation returned NaN values",
                    tags=["nan_value"]
                )

            is_bullish_breakout = curr_close > prev_donchian_high and curr_vol_ratio >= min_vol_ratio and curr_expansion >= expansion_threshold
            is_bearish_breakout = curr_close < prev_donchian_low and curr_vol_ratio >= min_vol_ratio and curr_expansion >= expansion_threshold

            direction = None
            valid = True
            confidence = 0.0
            rationale_msg = ""

            if is_bullish_breakout:
                direction = "buy"
                base_conf = 0.55
                vol_boost = min(0.20, max(0.0, (curr_vol_ratio - 1.0) * 0.15))
                exp_boost = min(0.15, max(0.0, (curr_expansion - 1.0) * 0.15))
                trend_boost = 0.10 if curr_ema20 > curr_ema50 else 0.0
                confidence = float(np.clip(base_conf + vol_boost + exp_boost + trend_boost, 0.0, 1.0))
                rationale_msg = (
                    f"XAUUSD Bullish Donchian Expansion: Close {curr_close:.2f} > Upper {prev_donchian_high:.2f}. "
                    f"Vol Ratio: {curr_vol_ratio:.2f}x (threshold {min_vol_ratio:.2f}x), "
                    f"Channel Expansion: {curr_expansion:.2f}x (threshold {expansion_threshold:.2f}x)."
                )
            elif is_bearish_breakout:
                direction = "sell"
                base_conf = 0.55
                vol_boost = min(0.20, max(0.0, (curr_vol_ratio - 1.0) * 0.15))
                exp_boost = min(0.15, max(0.0, (curr_expansion - 1.0) * 0.15))
                trend_boost = 0.10 if curr_ema20 < curr_ema50 else 0.0
                confidence = float(np.clip(base_conf + vol_boost + exp_boost + trend_boost, 0.0, 1.0))
                rationale_msg = (
                    f"XAUUSD Bearish Donchian Expansion: Close {curr_close:.2f} < Lower {prev_donchian_low:.2f}. "
                    f"Vol Ratio: {curr_vol_ratio:.2f}x (threshold {min_vol_ratio:.2f}x), "
                    f"Channel Expansion: {curr_expansion:.2f}x (threshold {expansion_threshold:.2f}x)."
                )
            else:
                rationale_msg = (
                    f"No Donchian Expansion signal for XAUUSD. Close: {curr_close:.2f}, "
                    f"Donchian Bounds: [{prev_donchian_low:.2f}, {prev_donchian_high:.2f}], "
                    f"Vol Ratio: {curr_vol_ratio:.2f}x, Channel Expansion: {curr_expansion:.2f}x."
                )

            tags = ["xauusd", "donchian", "volume_weighted", "breakout"]
            if direction:
                tags.append(f"{direction}_signal")

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=direction,
                valid=valid,
                confidence=confidence,
                rationale=rationale_msg,
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
