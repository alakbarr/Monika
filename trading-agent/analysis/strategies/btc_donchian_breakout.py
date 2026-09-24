import statistics
from sqlalchemy import select
from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from analysis.strategies.registry import StrategyRegistry
from database.models import PriceOHLCV
import utils.clock as clock

@StrategyRegistry.register
class BTCDonchianBreakout(EdgeStrategy):
    strategy_id = "btc_donchian_breakout"
    applicable_symbols = {'BTCUSD'}
    compatible_regimes = {'TREND', 'STRONG_TREND', 'EXPANDING_FAST'}
    factor_family = 'breakout'

    async def evaluate(self, session, symbol, settings) -> EdgeSignal:
        now = clock.now()
        n = self.cfg.get('donchian_period', 20)
        bars = (await session.execute(select(PriceOHLCV).where(
            PriceOHLCV.symbol == symbol, PriceOHLCV.timeframe == 'H4',
            PriceOHLCV.timestamp <= now
        ).order_by(PriceOHLCV.timestamp.desc()).limit(n + 20))).scalars().all()
        if len(bars) < n + 10:
            return EdgeSignal(self.strategy_id, symbol, None, False, 0.0, rationale="insufficient H4 history")

        latest, channel, vol_hist = bars[0], bars[1:n+1], [b.volume for b in bars[1:21] if b.volume]
        ch_high, ch_low = max(b.high for b in channel), min(b.low for b in channel)
        if len(vol_hist) < 10:
            return EdgeSignal(self.strategy_id, symbol, None, False, 0.0, rationale="insufficient volume history")

        mean_v, std_v = statistics.mean(vol_hist), statistics.pstdev(vol_hist) or 1e-9
        z = ((latest.volume or 0) - mean_v) / std_v
        min_z = self.cfg.get('volume_zscore_min', 1.5)
        if z < min_z:
            return EdgeSignal(self.strategy_id, symbol, None, False, 0.0, rationale=f"volume z={z:.2f} < {min_z}")

        if latest.close > ch_high:
            return EdgeSignal(self.strategy_id, symbol, 'buy', True, confidence=min(1.0, z / (min_z * 2)),
                               rationale=f"Donchian({n}) breakout, vol z={z:.2f}", tags=["btc_donchian", "trend", "breakout"],
                               exit_style='trend_trailing', ttl_minutes=120, factor_family='breakout',
                               meta={"size_multiplier": self.cfg.get('size_multiplier', 0.6)})
        if latest.close < ch_low:
            return EdgeSignal(self.strategy_id, symbol, 'sell', True, confidence=min(1.0, z / (min_z * 2)),
                               rationale=f"Donchian({n}) breakdown, vol z={z:.2f}", tags=["btc_donchian", "trend", "breakout"],
                               exit_style='trend_trailing', ttl_minutes=120, factor_family='breakout',
                               meta={"size_multiplier": self.cfg.get('size_multiplier', 0.6)})
        return EdgeSignal(self.strategy_id, symbol, None, False, 0.0, rationale="no breakout")
