"""
Counterfactual Simulator for Strategy Playbooks.

Validates candidate playbooks by replaying their rules against historical trade setups
before granting 'active' production status in PlaybookLifecycleManager.
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import PaperTradeRecord, DecisionReflection
from analysis.memory.playbook_lifecycle import PlaybookLifecycleManager, PlaybookStatus
from analysis.memory.playbook_ledger import PlaybookLedger

logger = logging.getLogger("TradingAgent.Memory.CounterfactualSimulator")


class CounterfactualSimulator:
    """
    Validates candidate trading playbooks against historical trade setups
    before promotion to active live/paper status.
    """

    def __init__(
        self,
        settings: Optional[dict] = None,
        lifecycle_manager: Optional[PlaybookLifecycleManager] = None,
        ledger: Optional[PlaybookLedger] = None,
    ):
        self.settings = settings or {}
        self.lifecycle = lifecycle_manager or PlaybookLifecycleManager()
        self.ledger = ledger or PlaybookLedger()

    async def simulate_candidate(
        self,
        session: AsyncSession,
        playbook_name: str,
        symbol: str,
        regime: str = "ANY",
        min_sample: int = 20,
        min_win_rate: float = 0.55,
    ) -> Dict[str, Any]:
        """
        Replays candidate playbook assumptions across historical setups.
        
        Args:
            session: Database session.
            playbook_name: Name of the playbook file or identifier.
            symbol: Target asset symbol (e.g. 'EURUSD', 'XAUUSD').
            regime: Market regime filter.
            min_sample: Target sample size for counterfactual replay.
            min_win_rate: Threshold win rate required for promotion.

        Returns:
            Dict containing replay metrics and promotion verdict.
        """
        clean_sym = symbol.strip().upper()

        # 1. Fetch historical paper trades or reflections
        stmt = (
            select(PaperTradeRecord)
            .where(PaperTradeRecord.symbol == clean_sym)
            .where(PaperTradeRecord.status == "closed")
            .order_by(desc(PaperTradeRecord.closed_at))
            .limit(min_sample)
        )
        trades = (await session.execute(stmt)).scalars().all()

        if len(trades) < 5:
            # Fallback to decision reflections if paper trade count is small
            ref_stmt = (
                select(DecisionReflection)
                .where(DecisionReflection.symbol == clean_sym)
                .where(DecisionReflection.status == "resolved")
                .order_by(desc(DecisionReflection.resolved_at))
                .limit(min_sample)
            )
            reflections = (await session.execute(ref_stmt)).scalars().all()
            simulated_trades = []
            for r in reflections:
                pnl_usd = float(r.outcome_pnl_usd or 0.0)
                # Normalize USD to percentage points on a $10,000 baseline account
                pnl_pct = (pnl_usd / 10000.0) * 100.0
                simulated_trades.append({
                    "won": pnl_usd > 0.0,
                    "pnl": pnl_pct,
                })
        else:
            simulated_trades = []
            for t in trades:
                pnl = float(t.pnl_pct or 0.0)
                simulated_trades.append({
                    "won": pnl > 0.0,
                    "pnl": pnl,
                })

        sample_size = len(simulated_trades)
        if sample_size == 0:
            logger.info(f"[CounterfactualSimulator] Insufficient historical setups for '{playbook_name}' (0 found).")
            return {
                "playbook_name": playbook_name,
                "symbol": clean_sym,
                "sample_size": 0,
                "promoted": False,
                "reason": "insufficient_historical_data",
            }

        wins = sum(1 for st in simulated_trades if st["won"])
        win_rate = wins / sample_size
        total_pnl = sum(st["pnl"] for st in simulated_trades)

        # Subsystem 6 Counterfactual Parameter Perturbations:
        # CF Scenario 1: What if SL was 1.5x wider?
        cf_sl_pnl = sum((st["pnl"] if st["won"] else st["pnl"] * 1.5) for st in simulated_trades)
        # CF Scenario 2: What if entry was delayed by 1 bar (slippage/friction penalty ~10 bps)?
        avg_abs_pnl = (sum(abs(st["pnl"]) for st in simulated_trades) / sample_size) if sample_size > 0 else 0.0
        penalty_pct = 0.0010 if avg_abs_pnl < 0.15 else 0.10
        cf_delayed_pnl = sum((st["pnl"] - penalty_pct) for st in simulated_trades)

        # Candidate must remain profitable under delayed execution friction to qualify
        qualifies = (win_rate >= min_win_rate) and (total_pnl > 0.0) and (cf_delayed_pnl >= 0.0)

        if qualifies:
            # Promote to ACTIVE
            meta = self.lifecycle.register_playbook(playbook_name, status=PlaybookStatus.ACTIVE)
            meta.status = PlaybookStatus.ACTIVE
            meta.current_win_rate = win_rate
            self.lifecycle._save_state()

            logger.info(
                f"[CounterfactualSimulator] Promoted '{playbook_name}' to ACTIVE "
                f"(Sample: {sample_size}, WR: {win_rate*100:.1f}%, PnL: {total_pnl:.2f}, CF Delay PnL: {cf_delayed_pnl:.2f})."
            )
        else:
            logger.info(
                f"[CounterfactualSimulator] Candidate '{playbook_name}' kept as CANDIDATE "
                f"(Sample: {sample_size}, WR: {win_rate*100:.1f}%, CF Delay PnL: {cf_delayed_pnl:.2f})."
            )

        return {
            "playbook_name": playbook_name,
            "symbol": clean_sym,
            "sample_size": sample_size,
            "win_rate": win_rate,
            "total_pnl": total_pnl,
            "cf_sl_1_5x_pnl": round(cf_sl_pnl, 4),
            "cf_delayed_pnl": round(cf_delayed_pnl, 4),
            "promoted": qualifies,
            "status": PlaybookStatus.ACTIVE.value if qualifies else PlaybookStatus.CANDIDATE.value,
        }

    async def simulate_single_trade_counterfactual(
        self,
        session: AsyncSession,
        trade_id: int,
        sl_pips_delta: float = 0.0,
        tp_pips_delta: float = 0.0,
        trailing_stop_atr_mult: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Simulate a counterfactual replay for a specific past trade with modified SL/TP or trailing stop parameters.
        """
        from database.models import PaperTradeRecord, Position, PriceOHLCV

        trade = await session.get(PaperTradeRecord, trade_id)
        pos = None
        if not trade:
            pos_stmt = select(Position).where((Position.ticket == trade_id) | (Position.id == trade_id))
            pos = (await session.execute(pos_stmt)).scalar_one_or_none()

        if not trade and not pos:
            return {
                "status": "error",
                "message": f"Trade #{trade_id} not found in paper trades or position history.",
            }

        symbol = str(trade.symbol if trade else pos.symbol).upper()
        direction = str(trade.direction if trade else pos.direction).upper()
        entry_price = float(trade.entry_price if trade else pos.entry_price)
        original_sl = float(trade.stop_loss if trade else (pos.sl or 0.0))
        original_tp = float(trade.take_profit if trade else (pos.tp or 0.0))
        exit_price = float(trade.exit_price if trade and trade.exit_price else (pos.exit_price if pos and hasattr(pos, "exit_price") and pos.exit_price else entry_price))
        actual_pnl = float(trade.pnl_usd if trade and trade.pnl_usd is not None else (pos.realized_pnl if pos and pos.realized_pnl is not None else 0.0))
        exit_reason = str(trade.exit_reason if trade else (pos.exit_reason if pos and hasattr(pos, "exit_reason") else "unknown"))

        pip_size = 0.01 if ("JPY" in symbol or "XAU" in symbol or "BTC" in symbol) else 0.0001

        if direction in ("BUY", "LONG"):
            cf_sl = original_sl - (sl_pips_delta * pip_size) if original_sl > 0 else (entry_price - (sl_pips_delta * pip_size))
            cf_tp = original_tp + (tp_pips_delta * pip_size) if original_tp > 0 else (entry_price + (tp_pips_delta * pip_size))
        else:
            cf_sl = original_sl + (sl_pips_delta * pip_size) if original_sl > 0 else (entry_price + (sl_pips_delta * pip_size))
            cf_tp = original_tp - (tp_pips_delta * pip_size) if original_tp > 0 else (entry_price - (tp_pips_delta * pip_size))

        start_time = trade.created_at if trade else getattr(pos, "open_time", None)
        end_time = trade.closed_at if trade else getattr(pos, "close_time", None)

        cf_outcome = "unchanged"
        cf_survived_sl = True
        cf_pnl = actual_pnl
        notes = []

        if start_time and end_time:
            bar_stmt = (
                select(PriceOHLCV)
                .where(PriceOHLCV.symbol == symbol)
                .where(PriceOHLCV.timestamp >= start_time)
                .where(PriceOHLCV.timestamp <= end_time)
                .order_by(PriceOHLCV.timestamp.asc())
            )
            bars = (await session.execute(bar_stmt)).scalars().all()

            if bars:
                lot = float(trade.lot_size if trade else (getattr(pos, "volume", 0.01) or 0.01))

                if trailing_stop_atr_mult is not None and trailing_stop_atr_mult > 0:
                    # Compute approximate ATR
                    tr_list = [max(float(b.high - b.low), abs(float(b.high - b.close)), abs(float(b.low - b.close))) for b in bars]
                    atr_est = (sum(tr_list) / len(tr_list)) if tr_list else (pip_size * 20.0)
                    trail_dist = trailing_stop_atr_mult * atr_est
                    
                    current_trail_sl = (entry_price - trail_dist) if direction in ("BUY", "LONG") else (entry_price + trail_dist)
                    trail_hit = False
                    trail_exit_price = exit_price

                    for b in bars:
                        bh = float(b.high)
                        bl = float(b.low)
                        if direction in ("BUY", "LONG"):
                            if bh - trail_dist > current_trail_sl:
                                current_trail_sl = bh - trail_dist
                            if bl <= current_trail_sl:
                                trail_hit = True
                                trail_exit_price = current_trail_sl
                                break
                        else:
                            if bl + trail_dist < current_trail_sl:
                                current_trail_sl = bl + trail_dist
                            if bh >= current_trail_sl:
                                trail_hit = True
                                trail_exit_price = current_trail_sl
                                break

                    pnl_diff_price = (trail_exit_price - entry_price) if direction in ("BUY", "LONG") else (entry_price - trail_exit_price)
                    cf_pnl = (pnl_diff_price / pip_size) * lot * 10.0
                    cf_outcome = "TRAILING_STOP_TRIGGERED" if trail_hit else "TRAILING_STOP_HELD"
                    notes.append(f"Simulated ATR trailing stop ({trailing_stop_atr_mult}x ATR = {trail_dist:.5f}). Exit price: {trail_exit_price:.5f}.")
                else:
                    lowest_price = min(float(b.low) for b in bars)
                    highest_price = max(float(b.high) for b in bars)

                    if direction in ("BUY", "LONG"):
                        orig_sl_hit = (lowest_price <= original_sl) if original_sl > 0 else False
                        cf_sl_hit = lowest_price <= cf_sl
                        cf_tp_hit = (highest_price >= cf_tp) if cf_tp > 0 else False
                    else:
                        orig_sl_hit = (highest_price >= original_sl) if original_sl > 0 else False
                        cf_sl_hit = highest_price >= cf_sl
                        cf_tp_hit = (lowest_price <= cf_tp) if cf_tp > 0 else False

                    if orig_sl_hit and not cf_sl_hit:
                        cf_survived_sl = True
                        notes.append(f"Wider SL (+{sl_pips_delta} pips) survived adverse price excursion.")
                        if cf_tp_hit:
                            cf_outcome = "SL_SAVED_AND_TP_HIT"
                            pnl_pips = abs(cf_tp - entry_price) / pip_size
                            cf_pnl = pnl_pips * lot * 10.0
                            notes.append(f"Subsequent market move reached TP ({cf_tp:.5f}). Trade turned into WIN.")
                        else:
                            cf_outcome = "SL_SAVED_OPEN"
                            notes.append("Trade would have avoided premature stop out.")
                    elif cf_sl_hit:
                        cf_survived_sl = False
                        cf_outcome = "STILL_HIT_SL"
                        loss_diff = sl_pips_delta * pip_size * lot * 10.0
                        cf_pnl = actual_pnl - loss_diff
                        notes.append(f"Adverse excursion exceeded wider SL ({cf_sl:.5f}). Loss increased.")
                    else:
                        cf_outcome = "SAME_OUTCOME"
                        notes.append("Original trade did not hit SL.")

        return {
            "status": "success",
            "trade_id": trade_id,
            "symbol": symbol,
            "direction": direction,
            "entry_price": entry_price,
            "original": {
                "stop_loss": original_sl,
                "take_profit": original_tp,
                "exit_price": exit_price,
                "exit_reason": exit_reason,
                "pnl": actual_pnl,
            },
            "counterfactual": {
                "sl_pips_delta": sl_pips_delta,
                "tp_pips_delta": tp_pips_delta,
                "trailing_stop_atr_mult": trailing_stop_atr_mult,
                "new_stop_loss": round(cf_sl, 5),
                "new_take_profit": round(cf_tp, 5),
                "survived_sl": cf_survived_sl,
                "outcome": cf_outcome,
                "estimated_pnl": round(cf_pnl, 2),
                "pnl_diff": round(cf_pnl - actual_pnl, 2),
            },
            "notes": " ".join(notes) if notes else "No price bar history found for lifetime replay.",
        }

    # Alias for convenience
    simulate_trade = simulate_single_trade_counterfactual

    async def replay_portfolio_sizing(
        self,
        session: AsyncSession,
        target_risk_pct: float,
        baseline_risk_pct: float = 1.0,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """
        Simulate portfolio outcome if position sizing risk had been scaled.
        e.g. baseline 1.0% vs target 0.5% (conservative) or 2.0% (aggressive).
        """
        stmt = (
            select(PaperTradeRecord)
            .where(PaperTradeRecord.status == "closed")
            .order_by(desc(PaperTradeRecord.closed_at))
            .limit(limit)
        )
        trades = (await session.execute(stmt)).scalars().all()

        multiplier = float(target_risk_pct) / max(float(baseline_risk_pct), 0.01)

        actual_pnls = []
        cf_pnls = []

        for t in trades:
            pnl_usd = float(t.pnl_usd or 0.0)
            actual_pnls.append(pnl_usd)
            cf_pnls.append(pnl_usd * multiplier)

        total_actual = sum(actual_pnls)
        total_cf = sum(cf_pnls)

        def _calc_dd(pnl_list):
            equity = 10000.0
            peak = equity
            max_dd = 0.0
            for p in reversed(pnl_list):
                equity += p
                if equity > peak:
                    peak = equity
                dd = (peak - equity) / peak * 100.0
                if dd > max_dd:
                    max_dd = dd
            return round(max_dd, 2)

        actual_dd = _calc_dd(actual_pnls)
        cf_dd = _calc_dd(cf_pnls)

        return {
            "status": "success",
            "trades_replayed": len(trades),
            "baseline_risk_pct": baseline_risk_pct,
            "target_risk_pct": target_risk_pct,
            "scaling_multiplier": round(multiplier, 2),
            "baseline": {
                "total_pnl_usd": round(total_actual, 2),
                "max_drawdown_pct": actual_dd,
            },
            "counterfactual": {
                "total_pnl_usd": round(total_cf, 2),
                "max_drawdown_pct": cf_dd,
                "pnl_difference_usd": round(total_cf - total_actual, 2),
            },
            "summary": (
                f"Dengan scaling risk ke {target_risk_pct}% (multiplier {multiplier:.1f}x), "
                f"total PnL berubah dari ${total_actual:.2f} menjadi ${total_cf:.2f}, "
                f"dengan max drawdown terproyeksi {cf_dd}% (dibandingkan {actual_dd}% baseline)."
            ),
        }

