from datetime import datetime
import json
from typing import Any, Optional

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

        candles = await self.get_historical_candles(
            session=session,
            symbol=symbol,
            timeframe=tf,
            limit=max(n + 15, 60),
            as_of=now,
        )
        if candles:
            bars = list(reversed(candles))
        else:
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

        fast_row = None
        slow_row = None

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
            # High-performance zero-DB native Rust EMA calculation directly from bars
            import numpy as np
            from monika.core.native.rust_bridge import ema_f64

            close_vals = np.array(
                [
                    float(getattr(b, "close", b.get("close", 0.0) if isinstance(b, dict) else 0.0))
                    for b in reversed(bars)
                ],
                dtype=np.float64,
            )
            fast_period = int(self.cfg.get("ema_fast", 20))
            slow_period = int(self.cfg.get("ema_slow", 50))
            if len(close_vals) >= slow_period:
                e_fast = ema_f64(close_vals, fast_period)
                e_slow = ema_f64(close_vals, slow_period)
                if e_fast is not None and e_slow is not None and not np.isnan(e_fast[-1]) and not np.isnan(e_slow[-1]):
                    fast = float(e_fast[-1])
                    slow = float(e_slow[-1])

            if fast is None or slow is None:
                import pandas as pd

                closes = pd.Series(close_vals)
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

        def _px(item: Any, field: str) -> float:
            return float(getattr(item, field, item.get(field, 0.0) if isinstance(item, dict) else 0.0))

        latest = bars[0]
        channel = bars[1 : n + 1]
        ch_high = max(_px(b, "high") for b in channel)
        ch_low = min(_px(b, "low") for b in channel)
        ema_bull, ema_bear = fast > slow, fast < slow
        breakout_up = _px(latest, "close") > ch_high
        breakout_down = _px(latest, "close") < ch_low

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
