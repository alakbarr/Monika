from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xtiusd_43ae5f(EdgeStrategy):
    strategy_id: str = "alpha_xtiusd_43ae5f"
    applicable_symbols: set = {"XTIUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.timeframe: str = str(self.settings.get("timeframe", "H1"))
        self.candle_limit: int = int(self.settings.get("candle_limit", 120))
        self.min_required_candles: int = int(self.settings.get("min_required_candles", 30))
        self.base_period: int = int(self.settings.get("base_period", 20))
        self.vol_period: int = int(self.settings.get("vol_period", 20))
        self.vol_mult_threshold: float = float(self.settings.get("vol_mult_threshold", 1.15))
        self.expansion_threshold: float = float(self.settings.get("expansion_threshold", 0.5))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            merged_settings = {**self.settings, **(settings or {})}
            timeframe = str(merged_settings.get("timeframe", self.timeframe))
            limit = int(merged_settings.get("candle_limit", self.candle_limit))

            candles = await self.get_historical_candles(
                session=session,
                symbol=symbol,
                timeframe=timeframe,
                limit=limit
            )

            if not candles or len(candles) < self.min_required_candles:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale=f"Insufficient candle count ({len(candles) if candles else 0} available, minimum required {self.min_required_candles}).",
                    tags=["insufficient_data", "xtiusd"]
                )

            records = []
            for c in candles:
                try:
                    h = float(c.high)
                    l = float(c.low)
                    cl = float(c.close)
                    op = float(c.open)
                    v = float(c.volume)
                except (AttributeError, TypeError):
                    h = float(c['high'])
                    l = float(c['low'])
                    cl = float(c['close'])
                    op = float(c['open'])
                    v = float(c.get('volume', 1.0))
                records.append({'open': op, 'high': h, 'low': l, 'close': cl, 'volume': v})

            df = pd.DataFrame(records)

            # Sanitize input series against NaNs/Infs
            df = df.replace([np.inf, -np.inf], np.nan)
            df['close'] = df['close'].ffill().bfill()
            df['high'] = df['high'].ffill().bfill()
            df['low'] = df['low'].ffill().bfill()
            df['volume'] = df['volume'].fillna(0.0)

            # Volume Moving Average & Ratio
            vol_period = max(5, min(self.vol_period, len(df) - 1))
            df['vol_ma'] = df['volume'].rolling(window=vol_period, min_periods=1).mean()
            df['vol_ratio'] = np.where(df['vol_ma'] > 0, df['volume'] / df['vol_ma'], 1.0)
            df['vol_ratio'] = pd.Series(df['vol_ratio']).replace([np.inf, -np.inf], np.nan).fillna(1.0)

            # Dynamic Donchian Channel
            base_period = max(5, min(self.base_period, len(df) - 1))
            df['donchian_high'] = df['high'].shift(1).rolling(window=base_period, min_periods=1).max()
            df['donchian_low'] = df['low'].shift(1).rolling(window=base_period, min_periods=1).min()
            df['donchian_mid'] = (df['donchian_high'] + df['donchian_low']) / 2.0
            df['donchian_width'] = df['donchian_high'] - df['donchian_low']

            # Channel Width Expansion Metrics
            df['width_ma'] = df['donchian_width'].rolling(window=base_period, min_periods=1).mean()
            df['width_std'] = df['donchian_width'].rolling(window=base_period, min_periods=1).std().fillna(1e-6)
            df['width_std'] = df['width_std'].replace(0, 1e-6)
            df['expansion_z'] = (df['donchian_width'] - df['width_ma']) / df['width_std']
            df['expansion_z'] = df['expansion_z'].replace([np.inf, -np.inf], np.nan).fillna(0.0)

            # Trend Filter: EMA 50
            ema_span = min(50, max(5, len(df) // 2))
            df['ema_trend'] = df['close'].ewm(span=ema_span, adjust=False).mean()

            curr = df.iloc[-1]
            close_price = float(curr['close'])
            upper_band = float(curr['donchian_high'])
            lower_band = float(curr['donchian_low'])
            vol_ratio = float(curr['vol_ratio'])
            expansion_z = float(curr['expansion_z'])
            ema_trend = float(curr['ema_trend'])

            direction = None
            rationale_parts = []

            is_upper_breakout = close_price > upper_band
            is_lower_breakdown = close_price < lower_band
            is_volume_expanding = vol_ratio >= self.vol_mult_threshold
            is_channel_expanding = expansion_z >= self.expansion_threshold

            if is_upper_breakout and is_volume_expanding and is_channel_expanding:
                direction = 'buy'
                rationale_parts.append(
                    f"Upper Donchian breakout (Close {close_price:.2f} > Band {upper_band:.2f}) with Volume Ratio {vol_ratio:.2f} "
                    f"and Expansion Z-Score {expansion_z:.2f}."
                )
            elif is_lower_breakdown and is_volume_expanding and is_channel_expanding:
                direction = 'sell'
                rationale_parts.append(
                    f"Lower Donchian breakdown (Close {close_price:.2f} < Band {lower_band:.2f}) with Volume Ratio {vol_ratio:.2f} "
                    f"and Expansion Z-Score {expansion_z:.2f}."
                )
            else:
                rationale_parts.append(
                    f"No expansion breakout detected. Close={close_price:.2f}, Upper={upper_band:.2f}, Lower={lower_band:.2f}, "
                    f"VolRatio={vol_ratio:.2f}, ExpansionZ={expansion_z:.2f}."
                )

            if direction is None:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=True,
                    confidence=0.0,
                    rationale=" ".join(rationale_parts),
                    tags=["xtiusd", "donchian", "no_signal"]
                )

            # Confidence scoring model
            base_conf = 0.65
            vol_bonus = min(0.15, max(0.0, (vol_ratio - 1.0) * 0.1))
            exp_bonus = min(0.15, max(0.0, expansion_z * 0.05))

            trend_aligned = (direction == 'buy' and close_price > ema_trend) or (direction == 'sell' and close_price < ema_trend)
            trend_bonus = 0.05 if trend_aligned else 0.0

            raw_confidence = base_conf + vol_bonus + exp_bonus + trend_bonus
            confidence = round(float(np.clip(raw_confidence, 0.50, 0.95)), 4)

            tags = ["xtiusd", "volume_weighted", "donchian_expansion", direction]
            if trend_aligned:
                tags.append("trend_aligned")

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=direction,
                valid=True,
                confidence=confidence,
                rationale=" ".join(rationale_parts),
                tags=tags
            )

        except Exception as e:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Calculation error: {str(e)}",
                tags=["error", "xtiusd"]
            )