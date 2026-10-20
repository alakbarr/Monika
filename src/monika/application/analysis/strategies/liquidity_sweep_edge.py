from datetime import datetime
from typing import Optional

import monika.core.primitives.clock as clock
from monika.application.analysis.calculators.liquidity_sweep_detector import detect_liquidity_sweep
from monika.application.analysis.strategies.base_strategy import EdgeSignal, EdgeStrategy
from monika.application.analysis.strategies.registry import StrategyRegistry


@StrategyRegistry.register
class LiquiditySweepStructuralShift(EdgeStrategy):
    strategy_id = "liquidity_sweep"
    applicable_symbols = {"XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD"}
    compatible_regimes = {
        "RANGE",
        "RANGING",
        "VOLATILE_CHOP",
        "WEAK_TREND",
        "TREND",
        "STRONG_TREND",
        "SQUEEZE_CONSOLIDATION",
    }
    factor_family = "breakout"

    async def evaluate(self, session, symbol: str, settings: dict, as_of: Optional[datetime] = None) -> EdgeSignal:
        now = as_of or clock.now()
        r = await detect_liquidity_sweep(session, symbol, settings, as_of=now)
        if not r.get("structure_confirmed"):
            return EdgeSignal(self.strategy_id, symbol, None, False, 0.0, rationale=str(r.get("reasons")))
        conf = 0.75 if r.get("volume_confirmed") else 0.45
        require_vol = self.cfg.get("require_volume_confirmation", False)
        if require_vol and not r.get("volume_confirmed"):
            return EdgeSignal(self.strategy_id, symbol, None, False, 0.0, rationale="volume not confirmed, hard-gated")

        direction = "buy" if r["valid_for_direction"] == "buy" else "sell"

        candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe="H1", limit=2, as_of=now)
        if not candles:
            entry_price = float(r.get("sweep_price", 0.0) or r.get("entry_price", 0.0) or 1.0)
        else:
            entry_price = float(candles[-1].close)
        from monika.application.analysis.calculators.intraday_level_optimizer import _get_atr

        atr = await _get_atr(session, symbol)
        if not atr or atr <= 0:
            atr = entry_price * 0.0050

        buf = atr * 0.10
        sweep_price = r.get("sweep_price", entry_price)

        if direction == "buy":
            stop_loss = round(min(sweep_price - buf, entry_price - (atr * 0.5)), 5)
            risk = entry_price - stop_loss
            if risk <= 0:
                stop_loss = round(entry_price - (atr * 1.0), 5)
                risk = entry_price - stop_loss
            take_profit = round(entry_price + (risk * 2.0), 5)
        else:
            stop_loss = round(max(sweep_price + buf, entry_price + (atr * 0.5)), 5)
            risk = stop_loss - entry_price
            if risk <= 0:
                stop_loss = round(entry_price + (atr * 1.0), 5)
                risk = stop_loss - entry_price
            take_profit = round(entry_price - (risk * 2.0), 5)

        sig = EdgeSignal(
            strategy_id=self.strategy_id,
            symbol=symbol,
            direction=direction,
            valid=True,
            confidence=conf,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            ttl_minutes=45,
            factor_family="breakout",
            exit_style="intraday_adr",
            rationale="; ".join(r.get("reasons", [])),
            tags=["liquidity_sweep", "reversal", "breakout"],
            meta=r,
        )
        return sig
