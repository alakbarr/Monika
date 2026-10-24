from datetime import datetime
import json
from typing import Optional

from sqlalchemy import select

import monika.core.primitives.clock as clock
from monika.application.analysis.strategies.base_strategy import EdgeSignal, EdgeStrategy
from monika.application.analysis.strategies.registry import StrategyRegistry
from monika.core.validation.indicator_sanitizer import safe_float
from monika.infrastructure.database.models import PriceOHLCV, TechnicalIndicator


@StrategyRegistry.register
class XAUTrendEngine(EdgeStrategy):
    strategy_id = "xau_trend_engine"
    applicable_symbols = {"XAUUSD"}
    compatible_regimes = {"TREND", "STRONG_TREND", "WEAK_TREND"}
    factor_family = "trend"

    async def evaluate(self, session, symbol: str, settings: dict, as_of: Optional[datetime] = None) -> EdgeSignal:
        now = as_of or clock.now()
        n = int(self.cfg.get("donchian_period", 20))
        tf = self.cfg.get("timeframe", "H1")

        fast_row = (
            await session.execute(
                select(TechnicalIndicator)
                .where(
                    TechnicalIndicator.symbol == symbol,
                    TechnicalIndicator.timeframe == tf,
                    TechnicalIndicator.indicator_name == f"EMA_{self.cfg.get('ema_fast', 20)}",
                    TechnicalIndicator.timestamp <= now,
                )
                .order_by(TechnicalIndicator.timestamp.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        slow_row = (
            await session.execute(
                select(TechnicalIndicator)
                .where(
                    TechnicalIndicator.symbol == symbol,
                    TechnicalIndicator.timeframe == tf,
                    TechnicalIndicator.indicator_name == f"EMA_{self.cfg.get('ema_slow', 50)}",
                    TechnicalIndicator.timestamp <= now,
                )
                .order_by(TechnicalIndicator.timestamp.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        bars_res = await session.execute(
            select(PriceOHLCV)
            .where(PriceOHLCV.symbol == symbol, PriceOHLCV.timeframe == tf, PriceOHLCV.timestamp <= now)
            .order_by(PriceOHLCV.timestamp.desc())
            .limit(max(n + 15, 60))
        )
        bars = (
            bars_res.scalars().all()
            if hasattr(bars_res, "scalars")
            else (bars_res if isinstance(bars_res, list) else [])
        )
        if not bars:
            raw_candles = await self.get_historical_candles(
                session=session,
                symbol=symbol,
                timeframe=tf,
                limit=max(n + 15, 60),
                as_of=now,
            )
            bars = list(reversed(raw_candles))

        if len(bars) < n + 5:
            return EdgeSignal(
                self.strategy_id, symbol, None, False, 0.0, rationale=f"insufficient {tf} history ({len(bars)} bars)"
            )

        fast = None
        slow = None
        if fast_row and slow_row:
            fast_raw = json.loads(fast_row.value_json) if fast_row.value_json else None
            slow_raw = json.loads(slow_row.value_json) if slow_row.value_json else None
            fast_val = fast_raw.get("value", fast_raw) if isinstance(fast_raw, dict) else fast_raw
            slow_val = slow_raw.get("value", slow_raw) if isinstance(slow_raw, dict) else slow_raw
            fast, slow = safe_float(fast_val), safe_float(slow_val)

        if fast is None or slow is None:
            # Fallback: compute EMA directly from candle close prices
            import pandas as pd

            closes = pd.Series([float(b.close) for b in reversed(bars)])
            if len(closes) >= int(self.cfg.get("ema_slow", 50)):
                fast = float(closes.ewm(span=int(self.cfg.get("ema_fast", 20)), adjust=False).mean().iloc[-1])
                slow = float(closes.ewm(span=int(self.cfg.get("ema_slow", 50)), adjust=False).mean().iloc[-1])
            elif len(closes) >= n + 5:
                fast = float(
                    closes.ewm(span=min(len(closes) // 2, int(self.cfg.get("ema_fast", 20))), adjust=False)
                    .mean()
                    .iloc[-1]
                )
                slow = float(closes.ewm(span=len(closes), adjust=False).mean().iloc[-1])
            else:
                return EdgeSignal(self.strategy_id, symbol, None, False, 0.0, rationale=f"EMA data unavailable on {tf}")

        latest = bars[0]
        channel = bars[1 : n + 1]
        ch_high, ch_low = max(b.high for b in channel), min(b.low for b in channel)
        ema_bull, ema_bear = fast > slow, fast < slow
        breakout_up, breakout_down = float(latest.close) > ch_high, float(latest.close) < ch_low

        size_mult = float(self.cfg.get("size_multiplier", 0.8))
        entry_p = float(latest.close)
        ch_mid = (ch_high + ch_low) / 2.0

        # Enforce minimum volatility buffer on Gold ($3.00) to avoid broker spread suicide
        min_gold_sl = max(3.0, (ch_high - ch_low) * 0.15)
        if ema_bull and breakout_up:
            sl_dist = max(min_gold_sl, entry_p - ch_mid)
            sl_p = round(entry_p - sl_dist, 2)
            tp_p = round(entry_p + sl_dist * 1.5, 2)
            return EdgeSignal(
                self.strategy_id,
                symbol,
                "buy",
                True,
                confidence=0.7,
                entry_price=entry_p,
                stop_loss=sl_p,
                take_profit=tp_p,
                rationale=f"EMA{self.cfg.get('ema_fast', 20)}>{self.cfg.get('ema_slow', 50)} + Donchian({n}) breakout",
                tags=["xau_trend", "trend"],
                exit_style="trend_trailing",
                factor_family="trend",
                meta={"size_multiplier": size_mult},
            )
        if ema_bear and breakout_down:
            sl_dist = max(min_gold_sl, ch_mid - entry_p)
            sl_p = round(entry_p + sl_dist, 2)
            tp_p = round(entry_p - sl_dist * 1.5, 2)
            return EdgeSignal(
                self.strategy_id,
                symbol,
                "sell",
                True,
                confidence=0.7,
                entry_price=entry_p,
                stop_loss=sl_p,
                take_profit=tp_p,
                rationale=f"EMA{self.cfg.get('ema_fast', 20)}<{self.cfg.get('ema_slow', 50)} + Donchian({n}) breakdown",
                tags=["xau_trend", "trend"],
                exit_style="trend_trailing",
                factor_family="trend",
                meta={"size_multiplier": size_mult},
            )
        return EdgeSignal(self.strategy_id, symbol, None, False, 0.0, rationale="no EMA+Donchian confluence")
