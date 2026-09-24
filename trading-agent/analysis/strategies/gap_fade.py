import json
from sqlalchemy import select
from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from analysis.strategies.registry import StrategyRegistry
from database.models import PriceOHLCV, TechnicalIndicator
from utils.validation.indicator_sanitizer import safe_float
import utils.clock as clock

# IMPORTANT: SESSION_OPEN_HOUR_UTC MUST be validated against the broker's actual rollover schedule.
# MT5 brokers often use EET/EEST timezones. Adjust these UTC hours so that they match the exact
# hour the broker considers the start of a new daily trading session (when the D1 bar rolls over).
SESSION_OPEN_HOUR_UTC = {'EURUSD': 8, 'GBPUSD': 8, 'AUDUSD': 0, 'USDJPY': 0, 'XAUUSD': 8, 'XTIUSD': 8, 'XBRUSD': 8, 'BTCUSD': 0}
PIP_SIZE = {
    'EURUSD': 0.0001, 'GBPUSD': 0.0001, 'AUDUSD': 0.0001, 'USDJPY': 0.01,
    'XAUUSD': 0.01, 'XTIUSD': 0.01, 'XBRUSD': 0.01, 'BTCUSD': 1.0,
}

@StrategyRegistry.register
class DailyReopenGapFade(EdgeStrategy):
    strategy_id = "gap_fade"
    applicable_symbols = set(SESSION_OPEN_HOUR_UTC.keys())
    compatible_regimes = {'RANGE', 'WEAK_TREND', 'VOLATILE_CHOP'}
    factor_family = 'mean_reversion'
    min_sample_size = 30

    async def evaluate(self, session, symbol, settings) -> EdgeSignal:
        now = clock.now()
        open_hour = SESSION_OPEN_HOUR_UTC.get(symbol)
        if open_hour is None:
            return EdgeSignal(self.strategy_id, symbol, None, False, 0.0, rationale=f"symbol {symbol} not in SESSION_OPEN_HOUR_UTC")
        minutes_since_open = (now.hour - open_hour) * 60 + now.minute
        if not (0 <= minutes_since_open <= 60):
            return EdgeSignal(self.strategy_id, symbol, None, False, 0.0, rationale="outside first-hour window")

        # NEW: only genuine weekend reopens produce a real "gap" in a continuous market
        if now.weekday() not in (0, 6):
            return EdgeSignal(self.strategy_id, symbol, None, False, 0.0,
                               rationale='not weekend reopen (Sunday/Monday UTC); weekday D1 boundaries are not genuine gaps in a continuous market')

        d1 = (await session.execute(select(PriceOHLCV).where(
            PriceOHLCV.symbol == symbol, PriceOHLCV.timeframe == 'D1',
            PriceOHLCV.timestamp <= now
        ).order_by(PriceOHLCV.timestamp.desc()).limit(2))).scalars().all()
        if len(d1) < 2:
            return EdgeSignal(self.strategy_id, symbol, None, False, 0.0, rationale="insufficient D1 history")

        prev_bar, today_bar = d1[1], d1[0]
        gap_span_hours = (today_bar.timestamp - prev_bar.timestamp).total_seconds() / 3600
        if gap_span_hours < 24:
            return EdgeSignal(self.strategy_id, symbol, None, False, 0.0,
                               rationale=f'D1 bars only {gap_span_hours:.1f}h apart — not a real weekend gap')

        prev_close = safe_float(d1[1].close)
        today_open = safe_float(d1[0].open)
        if not prev_close or not today_open:
            return EdgeSignal(self.strategy_id, symbol, None, False, 0.0, rationale="dirty price data")

        from utils.market.instrument_identity import resolve_instrument_identity
        pip = PIP_SIZE.get(symbol) or resolve_instrument_identity(symbol).pip_size or 0.0001
        gap = today_open - prev_close
        gap_pips = abs(gap) / pip

        atr_row = (await session.execute(select(TechnicalIndicator).where(
            TechnicalIndicator.symbol == symbol, TechnicalIndicator.timeframe == 'H4',
            TechnicalIndicator.indicator_name == 'ATR_14',
            TechnicalIndicator.timestamp <= now
        ).order_by(TechnicalIndicator.timestamp.desc()).limit(1))).scalar_one_or_none()
        atr = None
        if atr_row:
            raw = json.loads(atr_row.value_json)
            atr = safe_float(raw.get('atr', raw.get('value')) if isinstance(raw, dict) else raw)

        threshold = self.cfg.get('min_gap_pips', {}).get(symbol)
        if symbol == 'XAUUSD' and atr:
            threshold = max(threshold or 0, (atr * 0.25) / pip)
        if not threshold or gap_pips < threshold:
            return EdgeSignal(self.strategy_id, symbol, None, False, 0.0,
                               rationale=f"gap {gap_pips:.1f}p < threshold {threshold}")

        spread = self.cfg.get('assumed_spread_pips', {}).get(symbol, 1.5)
        slip = self.cfg.get('assumed_slippage_pips', 0.5)
        net_edge = gap_pips - spread - slip
        if net_edge <= 0:
            return EdgeSignal(self.strategy_id, symbol, None, False, 0.0, rationale="gap consumed by costs")

        direction = 'sell' if gap > 0 else 'buy'
        entry = today_open
        sl_distance = max(atr * 0.5 if atr else gap_pips * pip * 0.6, gap_pips * pip * 0.4)
        sl = entry + sl_distance if direction == 'sell' else entry - sl_distance
        tp = prev_close  # fade target: fill back to prior close
        risk, reward = abs(entry - sl), abs(entry - tp)
        if risk <= 0 or reward / risk < 1.5:
            return EdgeSignal(self.strategy_id, symbol, None, False, 0.0,
                               rationale=f"R:R {reward/risk if risk else 0:.2f} < 1.5")

        return EdgeSignal(
            self.strategy_id, symbol, direction, True,
            confidence=min(1.0, net_edge / (threshold * 2)),
            entry_price=entry, stop_loss=sl, take_profit=tp,
            max_hold_minutes=self.cfg.get('max_hold_minutes', 60), force_session_close=True,
            ttl_minutes=self.cfg.get('ttl_minutes', 60), factor_family='mean_reversion',
            rationale=f"Reopen gap {gap_pips:.1f}p (net {net_edge:.1f}p after costs), fading to prior close.",
            tags=["gap_fade", "mean_reversion"],
            meta={"gap_pips": gap_pips, "prev_close": prev_close},
        )
