import json
from sqlalchemy import select
from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from analysis.strategies.registry import StrategyRegistry
from database.models import TechnicalIndicator, PriceOHLCV
from utils.validation.indicator_sanitizer import safe_float
import utils.clock as clock

@StrategyRegistry.register
class XAUTrendEngine(EdgeStrategy):
    strategy_id = "xau_trend_engine"
    applicable_symbols = {'XAUUSD'}

    async def evaluate(self, session, symbol, settings) -> EdgeSignal:
        now = clock.now()
        fast_row = (await session.execute(select(TechnicalIndicator).where(
            TechnicalIndicator.symbol == symbol, TechnicalIndicator.timeframe == 'H4',
            TechnicalIndicator.indicator_name == f"EMA_{self.cfg.get('ema_fast', 20)}",
            TechnicalIndicator.timestamp <= now
        ).order_by(TechnicalIndicator.timestamp.desc()).limit(1))).scalar_one_or_none()
        slow_row = (await session.execute(select(TechnicalIndicator).where(
            TechnicalIndicator.symbol == symbol, TechnicalIndicator.timeframe == 'H4',
            TechnicalIndicator.indicator_name == f"EMA_{self.cfg.get('ema_slow', 50)}",
            TechnicalIndicator.timestamp <= now
        ).order_by(TechnicalIndicator.timestamp.desc()).limit(1))).scalar_one_or_none()
        if not fast_row or not slow_row:
            return EdgeSignal(self.strategy_id, symbol, None, False, 0.0, rationale="EMA data unavailable")

        fast, slow = safe_float(json.loads(fast_row.value_json)), safe_float(json.loads(slow_row.value_json))
        if fast is None or slow is None:
            return EdgeSignal(self.strategy_id, symbol, None, False, 0.0, rationale="dirty EMA values")

        n = self.cfg.get('donchian_period', 20)
        bars = (await session.execute(select(PriceOHLCV).where(
            PriceOHLCV.symbol == symbol, PriceOHLCV.timeframe == 'H4',
            PriceOHLCV.timestamp <= now
        ).order_by(PriceOHLCV.timestamp.desc()).limit(n + 1))).scalars().all()
        if len(bars) < n + 1:
            return EdgeSignal(self.strategy_id, symbol, None, False, 0.0, rationale="insufficient H4 history")

        latest, channel = bars[0], bars[1:]
        ch_high, ch_low = max(b.high for b in channel), min(b.low for b in channel)
        ema_bull, ema_bear = fast > slow, fast < slow
        breakout_up, breakout_down = latest.close > ch_high, latest.close < ch_low

        if ema_bull and breakout_up:
            return EdgeSignal(self.strategy_id, symbol, 'buy', True, confidence=0.7,
                               rationale=f"EMA{self.cfg.get('ema_fast')}>{self.cfg.get('ema_slow')} + Donchian({n}) breakout",
                               tags=["xau_trend", "trend"], exit_style='trend_trailing')
        if ema_bear and breakout_down:
            return EdgeSignal(self.strategy_id, symbol, 'sell', True, confidence=0.7,
                               rationale=f"EMA{self.cfg.get('ema_fast')}<{self.cfg.get('ema_slow')} + Donchian({n}) breakdown",
                               tags=["xau_trend", "trend"], exit_style='trend_trailing')
        return EdgeSignal(self.strategy_id, symbol, None, False, 0.0, rationale="no EMA+Donchian confluence")
