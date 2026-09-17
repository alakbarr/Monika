"""
OutcomeEvaluator: High-fidelity trade outcome evaluation against historical OHLCV data.
Includes realistic asset-specific dynamic spreads, slippage, and lot-sized swap costs.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from sqlalchemy import select
from database.db import get_session
from database.models import PriceOHLCV, BacktestTrade
from risk.position_sizing import DEFAULT_INSTRUMENTS

logger = logging.getLogger("TradingAgent.OutcomeEvaluator")

# Realistic broker market friction profile across asset classes (FX, Metals, Energy, Crypto)
ASSET_FRICTION_PROFILE = {
    # Major & Minor FX
    "EURUSD": {"spread_pips": 1.2, "slippage_pips": 0.4},
    "GBPUSD": {"spread_pips": 1.5, "slippage_pips": 0.5},
    "USDJPY": {"spread_pips": 1.3, "slippage_pips": 0.4},
    "AUDUSD": {"spread_pips": 1.4, "slippage_pips": 0.5},
    "NZDUSD": {"spread_pips": 1.8, "slippage_pips": 0.6},
    "USDCAD": {"spread_pips": 1.6, "slippage_pips": 0.5},
    "USDCHF": {"spread_pips": 1.5, "slippage_pips": 0.5},
    "EURJPY": {"spread_pips": 1.8, "slippage_pips": 0.6},
    "GBPJPY": {"spread_pips": 2.2, "slippage_pips": 0.8},
    # Commodities & Metals
    "XAUUSD": {"spread_pips": 30.0, "slippage_pips": 10.0},
    "XAGUSD": {"spread_pips": 3.0, "slippage_pips": 1.5},
    "XTIUSD": {"spread_pips": 4.0, "slippage_pips": 2.0},
    "XBRUSD": {"spread_pips": 4.0, "slippage_pips": 2.0},
    # Crypto (wider spreads + volatility slippage)
    "BTCUSD": {"spread_pips": 20.0, "slippage_pips": 10.0},
    "ETHUSD": {"spread_pips": 15.0, "slippage_pips": 8.0},
    "SOLUSD": {"spread_pips": 12.0, "slippage_pips": 6.0},
}


class OutcomeEvaluator:
    def __init__(
        self,
        max_holding_hours: int = 72,
        custom_friction_profile: Optional[Dict[str, Dict[str, float]]] = None,
        latency_ms: float = 0.0,
        commission_per_lot_usd: float = 0.0,
    ):
        self.max_holding_hours = max_holding_hours
        self.latency_ms = latency_ms
        self.commission_per_lot_usd = commission_per_lot_usd
        self.friction_profile = dict(ASSET_FRICTION_PROFILE)
        if custom_friction_profile:
            for sym, prof in custom_friction_profile.items():
                self.friction_profile[sym] = dict(prof)

    @staticmethod
    def get_contract_size(symbol: str) -> float:
        """Return standardized contract size for an asset."""
        sym = (symbol or "").upper()
        if "XTI" in sym or "WTI" in sym:
            return 100.0
        if "XBR" in sym or "BRENT" in sym:
            return 1000.0
        if "XAU" in sym:
            return 100.0
        if "BTC" in sym:
            return 1.0
        return 100_000.0

    _get_contract_size = get_contract_size

    async def calibrate_from_db(self, session, lookback_days: int = 30) -> Dict[str, Dict[str, float]]:
        """
        Calibrate dynamic asset friction profiles from historical paper/live execution logs.
        Calculates empirical average slippage and spread per symbol.
        """
        from database.models import PaperTradeRecord
        from sqlalchemy import select
        import utils.clock as clock
        
        since = clock.now() - timedelta(days=lookback_days)
        stmt = (
            select(PaperTradeRecord)
            .where(PaperTradeRecord.status == 'closed')
            .where(PaperTradeRecord.closed_at >= since)
        )
        trades = (await session.execute(stmt)).scalars().all()
        
        calibrated = {}
        for t in trades:
            if t.symbol and t.slippage_applied is not None:
                calibrated.setdefault(t.symbol, []).append(float(t.slippage_applied))
                
        for sym, slips in calibrated.items():
            if len(slips) >= 5:
                avg_slip = sum(slips) / len(slips)
                existing = self.friction_profile.get(sym, {"spread_pips": 1.5, "slippage_pips": 0.5})
                existing["slippage_pips"] = round(max(0.2, avg_slip), 2)
                self.friction_profile[sym] = existing
                logger.info(f"Calibrated empirical friction for {sym}: slippage={existing['slippage_pips']} pips (N={len(slips)})")

        return self.friction_profile

    async def simulate_risk_gate(self, trade: BacktestTrade, risk_gate: Optional[Any] = None) -> tuple[bool, str]:
        """
        Simulate live RiskGate evaluation against backtest trade setup.
        Rejects invalid R:R ratio, extreme spreads, or explicit RiskGate rejection.
        """
        if risk_gate is None:
            return True, ""

        if hasattr(risk_gate, "evaluate"):
            try:
                from risk.position_sizing import SizingResult
                from database.db import get_session
                lots = float(getattr(trade, "executed_lots", getattr(trade, "lots", 0.1)) or 0.1)
                risk_usd = float(getattr(trade, "risk_usd", 100.0) or 100.0)
                entry_p = float(trade.entry_price or 0.0)
                sl_p = float(trade.stop_loss or 0.0)
                tp_p = float(trade.take_profit) if trade.take_profit is not None else None
                eq = float(getattr(self, "equity", 10000.0) or 10000.0)
                sl_dist = abs(entry_p - sl_p)
                tp_dist = abs(tp_p - entry_p) if tp_p is not None else 0.0
                rr = (tp_dist / sl_dist) if sl_dist > 0 and tp_p is not None else None
                sizing = SizingResult(
                    symbol=str(trade.symbol or ""),
                    direction=str(trade.direction or "buy"),
                    entry_price=entry_p,
                    stop_loss=sl_p,
                    take_profit=tp_p,
                    account_equity=eq,
                    risk_percent=round((risk_usd / eq) * 100.0, 2) if eq > 0 else 1.0,
                    risk_amount_usd=risk_usd,
                    sl_distance_price=sl_dist,
                    sl_distance_pips=sl_dist * 10000.0,
                    pip_value_per_lot=10.0,
                    raw_lots=lots,
                    recommended_lots=lots,
                    rr_ratio=rr,
                    is_valid=True,
                )
                async with get_session() as session:
                    res = await risk_gate.evaluate(
                        session=session,
                        symbol=trade.symbol,
                        direction=trade.direction,
                        sizing=sizing,
                        account_equity=getattr(self, "equity", 10000.0) or 10000.0,
                        is_backtest=True,
                    )
                if hasattr(res, "approved") and not res.approved:
                    reasons = getattr(res, "rejection_reasons", ["RiskGate rejected"])
                    return False, "; ".join(reasons)
            except Exception as e:
                logger.debug(f"Simulated RiskGate.evaluate fallback: {e}")

        r_dist = abs(trade.entry_price - trade.stop_loss)
        reward_dist = abs(trade.take_profit - trade.entry_price)
        min_rr = getattr(risk_gate, "min_rr_ratio", 1.3) if risk_gate else 1.3
        if r_dist > 0 and (reward_dist / r_dist) < (min_rr - 1e-4):
            return False, f"RR ratio {reward_dist/r_dist:.2f} < minimum {min_rr}"

        sym_profile = self.friction_profile.get(trade.symbol, {})
        spread_pips = sym_profile.get("spread_pips", 1.5)
        max_spread = getattr(risk_gate, "max_spread_pips", 60.0) if risk_gate else 60.0
        if spread_pips > max_spread:
            return False, f"Spread {spread_pips} pips exceeds maximum {max_spread}"

        return True, ""

    async def evaluate_trade(
        self,
        trade: BacktestTrade,
        apply_costs: bool = False,
        risk_gate: Optional[Any] = None,
        simulate_guardian: bool = False,
        atr_pips: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate a trade against historical H1 OHLCV data.
        Returns outcome details including pips, percentage, dollar PnL, and cost friction.
        """
        if trade.entry_time.tzinfo is None:
            trade_entry_time = trade.entry_time.replace(tzinfo=timezone.utc)
        else:
            trade_entry_time = trade.entry_time

        # Simulated RiskGate entry rejection parity check
        if risk_gate is not None:
            approved, reason = await self.simulate_risk_gate(trade, risk_gate)
            if not approved:
                return {
                    "exit_time": trade_entry_time,
                    "exit_price": trade.entry_price,
                    "exit_reason": "risk_gate_rejected",
                    "rejection_reasons": [reason],
                    "pnl_pips": 0.0,
                    "pnl_pct": 0.0,
                    "pnl_usd": 0.0,
                    "swap_cost_usd": 0.0,
                    "friction_pips": 0.0,
                }

        end_time = trade_entry_time + timedelta(hours=self.max_holding_hours)

        async with get_session() as session:
            stmt = (
                select(PriceOHLCV)
                .where(PriceOHLCV.symbol == trade.symbol)
                .where(PriceOHLCV.timeframe == "H1")
                .where(PriceOHLCV.timestamp >= trade_entry_time)
                .where(PriceOHLCV.timestamp <= end_time)
                .order_by(PriceOHLCV.timestamp.asc())
            )
            bars = (await session.execute(stmt)).scalars().all()

        if not bars:
            return {
                "exit_time": end_time,
                "exit_price": trade.entry_price,
                "exit_reason": "no_data",
                "pnl_pips": 0.0,
                "pnl_pct": 0.0,
                "pnl_usd": 0.0,
                "swap_cost_usd": 0.0,
                "friction_pips": 0.0,
            }

        outcome = None
        sym_profile = self.friction_profile.get(trade.symbol, {"spread_pips": 1.5, "slippage_pips": 0.5})
        spread_pips = sym_profile.get("spread_pips", 1.5)
        spec = DEFAULT_INSTRUMENTS.get(trade.symbol)
        pip_size = getattr(spec, "pip_size", 0.0001) if spec else 0.0001
        spread_pip = spread_pips * pip_size
        for bar in bars:
            # Simulated PositionGuardian Friday market close liquidation parity
            if simulate_guardian:
                bar_dt = bar.timestamp
                if bar_dt.weekday() == 4 and bar_dt.hour >= 20 and "BTC" not in trade.symbol and "ETH" not in trade.symbol:
                    # R-4 parity: Friday close protection skips losing positions (close_if_profitable)
                    unrealized_pnl = (bar.close - trade.entry_price) if trade.direction.lower() == "buy" else (trade.entry_price - bar.close)
                    if unrealized_pnl > 0:
                        outcome = self._calculate_outcome(
                            trade, bar.timestamp, bar.close, "friday_close",
                            bar=bar, apply_costs=apply_costs, atr_pips=atr_pips
                        )
                        break

            if trade.direction.lower() == "buy":
                # Check SL first (conservative)
                if bar.low <= trade.stop_loss:
                    outcome = self._calculate_outcome(trade, bar.timestamp, trade.stop_loss, "sl_hit", bar=bar, apply_costs=apply_costs, atr_pips=atr_pips)
                    break
                if bar.high >= trade.take_profit:
                    outcome = self._calculate_outcome(trade, bar.timestamp, trade.take_profit, "tp_hit", bar=bar, apply_costs=apply_costs, atr_pips=atr_pips)
                    break
            elif trade.direction.lower() == "sell":
                # Posisi SELL ditutup pada harga ASK (Bid + Spread)
                ask_high = bar.high + spread_pip
                ask_low = bar.low + spread_pip
                # Check SL first
                if ask_high >= trade.stop_loss:
                    outcome = self._calculate_outcome(trade, bar.timestamp, trade.stop_loss, "sl_hit", bar=bar, apply_costs=apply_costs, atr_pips=atr_pips)
                    break
                if ask_low <= trade.take_profit:
                    outcome = self._calculate_outcome(trade, bar.timestamp, trade.take_profit, "tp_hit", bar=bar, apply_costs=apply_costs, atr_pips=atr_pips)
                    break

        if outcome is None:
            last_bar = bars[-1]
            outcome = self._calculate_outcome(trade, last_bar.timestamp, last_bar.close, "timeout", bar=last_bar, apply_costs=apply_costs, atr_pips=atr_pips)

        # Apply holding swap costs based on calculated lot size
        if apply_costs:
            try:
                from utils.market.swap_estimator import estimate_swap_cost
                holding_hours = max(1.0, (outcome["exit_time"] - trade_entry_time).total_seconds() / 3600.0)
                lots = getattr(trade, "executed_lots", None) or 0.1
                swap = await estimate_swap_cost(trade.symbol, trade.direction, lots, holding_hours, start_time=trade_entry_time)
                outcome["swap_cost_usd"] = round(swap, 2)
                # Deduct swap from pnl_usd
                outcome["pnl_usd"] = round(outcome["pnl_usd"] + swap, 2)
            except Exception as e:
                logger.debug(f"Swap estimation failed: {e}")
                outcome["swap_cost_usd"] = 0.0
        else:
            outcome["swap_cost_usd"] = 0.0

        return outcome

    def _get_session_spread_multiplier(self, dt: datetime) -> float:
        """
        Dynamic spread multiplier based on trading session and rollover hours.
        Rollover (20:55 - 21:30 UTC): 3.5x spread widening
        Asian session (21:30 - 06:00 UTC): 1.8x spread
        London/NY overlap (12:00 - 16:00 UTC): 1.0x baseline (maximum liquidity)
        Other hours: 1.2x
        """
        hour = dt.hour
        minute = dt.minute
        if (hour == 20 and minute >= 55) or (hour == 21 and minute <= 30):
            return 3.5
        if hour >= 21 or hour < 6:
            return 1.8
        if 12 <= hour <= 16:
            return 1.0
        return 1.2

    def _get_volatility_slippage(self, bar: PriceOHLCV, base_slippage: float, pip_size: float, atr_pips: Optional[float] = None) -> float:
        """Dynamic slippage scaling with intraday bar range volatility and ATR."""
        if not bar or pip_size <= 0:
            return base_slippage
        bar_range_pips = (bar.high - bar.low) / pip_size
        typical_range_pips = atr_pips if (atr_pips is not None and atr_pips > 0) else 20.0
        ratio = max(1.0, min(4.0, bar_range_pips / typical_range_pips))
        return round(base_slippage * ratio, 2)

    def _get_volatility_spread_multiplier(self, bar: Optional[PriceOHLCV], pip_size: float) -> float:
        """
        Dynamic spread widening multiplier based on intraday bar volatility shock.
        During news events or volatility surges (bar range > 2x typical), market makers widen spreads significantly.
        """
        if not bar or pip_size <= 0:
            return 1.0
        bar_range_pips = (bar.high - bar.low) / pip_size
        typical_range_pips = 20.0
        if bar_range_pips > typical_range_pips * 2.0:
            # Spread widens up to 2.5x during extreme volatility shocks
            return min(2.5, 1.0 + ((bar_range_pips - (typical_range_pips * 2.0)) / (typical_range_pips * 3.0)))
        return 1.0

    def _calculate_outcome(
        self,
        trade: BacktestTrade,
        exit_time: datetime,
        exit_price: float,
        reason: str,
        bar: Optional[PriceOHLCV] = None,
        apply_costs: bool = False,
        atr_pips: Optional[float] = None,
    ) -> Dict[str, Any]:
        spec = DEFAULT_INSTRUMENTS.get(trade.symbol)
        if spec:
            pip_size = spec.pip_size
            contract_size = spec.contract_size
        elif "JPY" in trade.symbol:
            pip_size = 0.01
            contract_size = 100_000.0
        elif "XAU" in trade.symbol:
            pip_size = 0.01
            contract_size = 100.0
        elif "BTC" in trade.symbol:
            pip_size = 1.0
            contract_size = 1.0
        elif "XTI" in trade.symbol or "WTI" in trade.symbol:
            pip_size = 0.01
            contract_size = 100.0
        elif "XBR" in trade.symbol or "BRENT" in trade.symbol:
            pip_size = 0.01
            contract_size = 1_000.0
        else:
            pip_size = 0.0001
            contract_size = 100_000.0

        # Realistic Weekend Gap Slippage Check (Non-crypto)
        if bar and getattr(bar, "open", None) is not None and "BTC" not in trade.symbol and "ETH" not in trade.symbol:
            # Check if bar opened with gap past stop loss
            if trade.direction.lower() == "buy" and reason == "sl_hit":
                if bar.open < trade.stop_loss:
                    exit_price = bar.open  # Gapped through SL -> filled at open price
            elif trade.direction.lower() == "sell" and reason == "sl_hit":
                if bar.open > trade.stop_loss:
                    exit_price = bar.open  # Gapped through SL -> filled at open price

        if trade.direction.lower() == "buy":
            gross_pnl_pips = (exit_price - trade.entry_price) / pip_size
            price_delta = exit_price - trade.entry_price
        else:
            gross_pnl_pips = (trade.entry_price - exit_price) / pip_size
            price_delta = trade.entry_price - exit_price

        friction_pips = 0.0
        commission_usd = 0.0
        lots = getattr(trade, "executed_lots", None) or 0.1
        if apply_costs:
            friction_cfg = self.friction_profile.get(
                trade.symbol,
                {"spread_pips": getattr(spec, "stops_level_pips", 1.5) or 1.5, "slippage_pips": 0.5}
            )
            base_spread = friction_cfg.get("spread_pips", 1.5)
            base_slippage = friction_cfg.get("slippage_pips", 0.5)
            
            # Session-aware and volatility-shock spread multiplier
            session_mult = self._get_session_spread_multiplier(exit_time)
            vol_spread_mult = self._get_volatility_spread_multiplier(bar, pip_size) if bar else 1.0
            effective_spread = base_spread * session_mult * vol_spread_mult
            
            # Volatility-adjusted slippage with ATR
            effective_slippage = self._get_volatility_slippage(bar, base_slippage, pip_size, atr_pips=atr_pips) if bar else base_slippage
            
            # Latency model: execution latency delay induces micro-slippage penalty
            latency_slippage_pips = (self.latency_ms / 1000.0) * (base_slippage * 0.2)

            if trade.direction.lower() == "sell" and reason in ("sl_hit", "tp_hit"):
                # Spread is already factored into Ask-based SL/TP exit trigger
                friction_pips = effective_slippage + latency_slippage_pips
            else:
                friction_pips = effective_spread + effective_slippage + latency_slippage_pips
            commission_usd = round(self.commission_per_lot_usd * lots, 2)

        net_pnl_pips = gross_pnl_pips - friction_pips
        friction_price = friction_pips * pip_size
        net_price_delta = price_delta - friction_price

        if trade.entry_price > 0:
            net_pnl_pct = (net_price_delta / trade.entry_price) * 100.0
        else:
            net_pnl_pct = 0.0

        # Calculate exact dollar PnL using instrument pip value per lot
        pip_val = getattr(spec, "pip_value_per_lot", None)
        if not pip_val or pip_val <= 0:
            if pip_size > 0 and exit_price > 0:
                if trade.symbol.endswith("USD"):
                    pip_val = pip_size * contract_size
                elif trade.symbol.startswith("USD"):
                    pip_val = (pip_size * contract_size) / exit_price
                elif trade.symbol == "BTCUSD":
                    pip_val = pip_size * 1.0
                elif trade.symbol.endswith("JPY"):
                    # Convert JPY pip value (e.g. 1000 JPY) to USD using approximate rate (~150)
                    pip_val = (pip_size * contract_size) / 150.0
                else:
                    pip_val = 10.0
            else:
                pip_val = 10.0

        net_usd = (lots * net_pnl_pips * pip_val) - commission_usd
        gross_usd = lots * gross_pnl_pips * pip_val
        friction_usd = (lots * friction_pips * pip_val) + commission_usd

        return {
            "exit_time": exit_time,
            "exit_price": exit_price,
            "exit_reason": reason,
            "pnl_pips": round(net_pnl_pips, 1),
            "pnl_pct": round(net_pnl_pct, 4),
            "pnl_usd": round(net_usd, 2),
            "friction_pips": round(friction_pips, 1),
            "friction_usd": round(friction_usd, 2),
            "commission_usd": round(commission_usd, 2),
            "latency_ms": self.latency_ms,
        }
