# ==============================================================================
# File: utils/paper_tracker.py
# ==============================================================================

"""
Paper Tracker — Melacak estimasi PnL (profit and loss) untuk mode dry_run.
Secara otomatis mencatat posisi setelah analisis disetujui (buy/sell),
dan mensimulasikan hasil jika harga mengenai SL atau TP.
"""

import asyncio
import logging
import math
from datetime import datetime, timedelta, timezone, UTC
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import monika.core.primitives.clock as clock
from monika.core.primitives.constants import MARKET_OUTCOME_EXIT_REASONS
from monika.domain.risk.position_math import validated_stop_distance
from monika.infrastructure.database.models import AssetAnalysis, PaperTradeRecord, Position, PriceOHLCV

logger = logging.getLogger("TradingAgent.PaperTracker")

_PAPER_TRACKER_LOCK = asyncio.Lock()


class PaperTracker:
    """
    Memantau posisi paper trade terbuka & melikuidasi saat menyentuh SL/TP.
    Dipanggil setiap siklus oleh CycleScheduler.
    """

    def __init__(self, settings: dict | None = None):
        if settings is None:
            try:
                import os

                import yaml

                base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                with open(os.path.join(base_dir, "config", "settings.yaml")) as f:
                    self.settings = yaml.safe_load(f)
            except Exception:
                self.settings = {}
        else:
            self.settings = settings

    async def update_paper_trade_sl(self, session: AsyncSession, analysis_id: int, new_sl: float) -> None:
        """Update the *current* stop loss for an open paper trade (used by TrailingStopManager).

        The entry-time anchor (``initial_stop_loss``) is never touched here: it is
        the denominator of realized R and must stay immutable.
        """
        if new_sl is None or not math.isfinite(float(new_sl)) or float(new_sl) <= 0:
            logger.error(f"[PAPER] Refusing invalid trailing SL {new_sl!r} for analysis_id {analysis_id}")
            return
        trade = (
            await session.execute(
                select(PaperTradeRecord)
                .where(PaperTradeRecord.analysis_id == analysis_id)
                .where(PaperTradeRecord.status == "open")
            )
        ).scalar_one_or_none()

        if trade:
            trade.stop_loss = float(new_sl)
            logger.debug(f"[PAPER] Updated SL for analysis_id {analysis_id} to {new_sl}")

    async def _resolve_initial_stop_loss(self, session: AsyncSession, trade: PaperTradeRecord) -> float | None:
        """Return the immutable entry stop, resolving it deterministically when legacy rows lack it.

        Never reads the mutable ``stop_loss`` column and never relies on an ORM
        relationship: the previous lazy-relationship fallback silently returned
        the trailing stop, which is exactly the accounting bug being fixed.
        """
        if trade.initial_stop_loss is not None:
            return float(trade.initial_stop_loss)
        if not trade.analysis_id:
            return None
        resolved = (
            await session.execute(select(AssetAnalysis.stop_loss).where(AssetAnalysis.id == trade.analysis_id))
        ).scalar_one_or_none()
        if resolved is None:
            return None
        trade.initial_stop_loss = float(resolved)
        if trade.initial_risk_pct is None and trade.risk_pct is not None:
            trade.initial_risk_pct = float(trade.risk_pct)
        return trade.initial_stop_loss

    async def _close_linked_position(self, session: AsyncSession, trade: PaperTradeRecord) -> None:
        """Mirror PaperTradeRecord closure into the Position table.
        Without this, paper Position rows stay status='open' forever and
        permanently deadlock RiskGate._check_max_positions / _check_no_duplicate.
        """
        if not trade.analysis_id:
            return
        pos = (
            await session.execute(
                select(Position)
                .where(Position.analysis_id == trade.analysis_id)
                .where(Position.status == "open")
                .where(Position.is_paper == True)
            )
        ).scalar_one_or_none()
        if pos:
            pos.status = "closed"
            closed_at = trade.closed_at or datetime.now(UTC)
            if closed_at.tzinfo is None:
                closed_at = closed_at.replace(tzinfo=UTC)
            if pos.opened_at is not None:
                if pos.opened_at.tzinfo is None:
                    pos.opened_at = pos.opened_at.replace(tzinfo=UTC)
                if closed_at < pos.opened_at:
                    closed_at = pos.opened_at
            pos.closed_at = closed_at
            # Mirror the verified paper result into Position.pnl; never fabricate a
            # number when accounting is unverifiable (fail closed, leave NULL).
            if trade.pnl_pct is not None:
                init_bal = float(self.settings.get("paper_trading", {}).get("initial_balance", 10000.0) or 10000.0)
                pos.pnl = round(init_bal * (trade.pnl_pct / 100.0), 2)
            else:
                pos.pnl = None
            pos.sl = trade.stop_loss
            logger.debug(f"[PAPER] Linked Position id={pos.id} closed with PaperTradeRecord {trade.id}")

    # -------------------------------------------------------------------------
    # Core Operations
    # -------------------------------------------------------------------------

    def _get_realistic_spread(self, symbol: str) -> float:
        """Calculate realistic spread utilizing multipliers based on settings.yaml and base spreads."""
        base_spreads = {
            "XAUUSD": 0.15,
            "EURUSD": 0.00008,
            "GBPUSD": 0.00012,
            "USDJPY": 0.012,
            "AUDUSD": 0.00008,
            "XTIUSD": 0.03,
            "XBRUSD": 0.04,
            "BTCUSD": 15.0,
        }
        spread = base_spreads.get(symbol, 0.0003)

        multipliers = self.settings.get("paper_trading", {}).get("spread_multipliers", {})
        multiplier = multipliers.get(symbol, multipliers.get("default", 1.5))
        spread *= multiplier
        return spread

    async def open_paper_trade(
        self, session: AsyncSession, analysis: AssetAnalysis, risk_pct: float = 0.75, **kwargs: Any
    ) -> None:
        """Open a paper trade respecting the entry condition type."""
        import json

        if not analysis.stop_loss or not analysis.take_profit:
            logger.debug(f"[PAPER] Skipping {analysis.symbol}: missing SL or TP")
            return

        # Parse entry condition from analysis
        entry_cond = {}
        if analysis.entry_zone:
            try:
                entry_cond = json.loads(analysis.entry_zone)
            except Exception:
                pass

        entry_type = entry_cond.get("type", "market")
        stated_price = entry_cond.get("price")

        # Get current market price from kwargs, last H4 bar, or other bars
        current_price = None
        if "entry_price" in kwargs and kwargs["entry_price"] is not None and float(kwargs["entry_price"]) > 0:
            current_price = float(kwargs["entry_price"])
        else:
            last_bar = (
                await session.execute(
                    select(PriceOHLCV)
                    .where(PriceOHLCV.symbol == analysis.symbol)
                    .where(PriceOHLCV.timeframe == "H4")
                    .order_by(PriceOHLCV.timestamp.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if last_bar and last_bar.close:
                current_price = float(last_bar.close)
            elif stated_price:
                current_price = float(stated_price)
            else:
                other_bar = (
                    await session.execute(
                        select(PriceOHLCV)
                        .where(PriceOHLCV.symbol == analysis.symbol)
                        .order_by(PriceOHLCV.timestamp.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if other_bar and other_bar.close:
                    current_price = float(other_bar.close)

        if not current_price or current_price <= 0:
            logger.warning(f"[PAPER] No valid price for {analysis.symbol}, cannot open paper trade")
            return

        # Dynamic spread
        spread = self._get_realistic_spread(analysis.symbol)

        if entry_type == "market" or stated_price is None:
            # Market order: execute at current price + half spread (for buy) or - half spread (for sell)
            if analysis.decision == "buy":
                actual_entry = current_price + spread / 2  # Pay the ask
            else:
                actual_entry = current_price - spread / 2  # Hit the bid
            is_pending = False

        elif entry_type == "limit":
            # Limit order: do NOT open immediately
            # Will be filled when price reaches stated_price in check_and_close_trades
            actual_entry = stated_price if stated_price else current_price
            is_pending = True
            logger.info(
                f"[PAPER] PENDING limit order for {analysis.symbol} {analysis.decision} @ {stated_price} (current: {current_price})"
            )

        elif entry_type == "trigger":
            # Treat trigger as limit at stated price
            actual_entry = stated_price if stated_price else current_price
            is_pending = True

        else:
            actual_entry = current_price
            is_pending = False

        req_lot = kwargs.get("requested_lot") or kwargs.get("lot_size")
        req_lot_float = float(req_lot) if req_lot is not None else None

        entry_anchor_ok = validated_stop_distance(analysis.decision, actual_entry, analysis.stop_loss) is not None
        if not entry_anchor_ok:
            logger.error(
                f"[PAPER] Invalid entry risk anchor for {analysis.symbol} {analysis.decision}: "
                f"entry={actual_entry} stop_loss={analysis.stop_loss}. "
                "Trade is recorded but its realized PnL will not be trusted (fail closed)."
            )

        trade = PaperTradeRecord(
            analysis_id=analysis.id,
            symbol=analysis.symbol,
            direction=analysis.decision,
            entry_price=actual_entry,  # Stated/actual fill price
            stop_loss=analysis.stop_loss,
            take_profit=analysis.take_profit,
            # Immutable entry-time anchor: trailing must never rewrite realized R.
            initial_stop_loss=analysis.stop_loss,
            initial_risk_pct=risk_pct,
            accounting_status="ok" if entry_anchor_ok else "invalid_initial_stop",
            opened_at=clock.now(),
            status="open",
            risk_pct=risk_pct,
            entry_condition_type=entry_type,
            stated_entry_price=stated_price,
            is_pending_fill=is_pending,
            requested_lot=req_lot_float,
            decision_source=getattr(analysis, "decision_source", None),
            was_debate_modified=bool(getattr(analysis, "was_debate_modified", False)),
        )
        session.add(trade)
        await session.commit()

        if is_pending:
            logger.info(
                f"[PAPER] PENDING {analysis.symbol} {analysis.decision} @ {actual_entry} (awaiting fill, current={current_price})"
            )
        else:
            logger.info(f"[PAPER] Opened {analysis.symbol} {analysis.decision} @ {actual_entry:.5f} (risk={risk_pct}%)")

    async def _get_bars_since_open(self, session: AsyncSession, trade: PaperTradeRecord, timeframe: str):
        """Ambil bars sejak posisi dibuka, termasuk bar yang sedang aktif."""
        start_time = trade.filled_at or trade.opened_at
        age_hours = (clock.now() - start_time).total_seconds() / 3600

        # Dynamic limit based on timeframe and age
        if timeframe == "M15":
            limit = int(age_hours * 4) + 10
        elif timeframe == "H1":
            limit = int(age_hours) + 10
        else:
            limit = int(age_hours / 4) + 10

        limit = min(5000, max(50, limit))

        return list(
            (
                await session.execute(
                    select(PriceOHLCV)
                    .where(PriceOHLCV.symbol == trade.symbol)
                    .where(PriceOHLCV.timeframe == timeframe)
                    .where(PriceOHLCV.timestamp >= start_time)
                    .where(PriceOHLCV.timestamp <= clock.now())
                    .order_by(PriceOHLCV.timestamp.asc())
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )

    async def _is_news_environment(self, session: AsyncSession, trade: PaperTradeRecord, bar_timestamp) -> bool:
        """Gunakan database EconomicCalendar untuk deteksi rilis berita High impact."""
        if bar_timestamp is None:
            return False
        try:
            from datetime import timedelta

            from sqlalchemy import select

            from monika.infrastructure.database.models import EconomicCalendar

            # Extract base currency from symbol (e.g. EURUSD -> EUR, XAUUSD -> XAU)
            base_ccy = trade.symbol[:3] if len(trade.symbol) >= 6 else None
            quote_ccy = trade.symbol[3:6] if len(trade.symbol) >= 6 else None
            currencies = [c for c in (base_ccy, quote_ccy, "USD") if c]
            events = (
                await session.execute(
                    select(EconomicCalendar)
                    .where(EconomicCalendar.currency.in_(currencies))
                    .where(EconomicCalendar.impact == "high")
                    .where(EconomicCalendar.event_time >= bar_timestamp - timedelta(minutes=30))
                    .where(EconomicCalendar.event_time <= bar_timestamp + timedelta(minutes=30))
                    .limit(1)
                )
            ).scalar_one_or_none()
            return events is not None
        except Exception as e:
            logger.debug(f"_is_news_environment check failed (non-fatal, assuming normal): {e}")
            return False

    async def _check_sl_tp(
        self, session: AsyncSession, trade: PaperTradeRecord, bars, timeframe: str = "H4"
    ) -> dict | None:
        SLIPPAGE_MODEL = {
            "XAUUSD": {"normal": 0.3, "news": 4.0, "weekend_open": 8.0, "off_peak": 1.0},
            "EURUSD": {"normal": 0.00012, "news": 0.0010, "weekend_open": 0.0020, "off_peak": 0.0003},
            "GBPUSD": {"normal": 0.00018, "news": 0.0015, "weekend_open": 0.0025, "off_peak": 0.0005},
            "USDJPY": {"normal": 0.06, "news": 0.30, "weekend_open": 0.50, "off_peak": 0.12},
            "AUDUSD": {"normal": 0.00012, "news": 0.0008, "weekend_open": 0.0015, "off_peak": 0.0003},
            "XTIUSD": {"normal": 0.15, "news": 1.20, "weekend_open": 2.50, "off_peak": 0.40},
            "BTCUSD": {"normal": 5.0, "news": 25.0, "weekend_open": 40.0, "off_peak": 15.0},
        }
        # FIX (P0): pakai model spread realistis per-simbol yang SAMA dengan
        # yang dipakai saat entry (self._get_realistic_spread). Implementasi
        # lama membaca settings.assets.symbols.<SYMBOL>.spread_tolerance --
        # path config yang tidak pernah ada di settings.yaml -- sehingga
        # selalu jatuh ke default generik 0.0003 untuk SEMUA simbol,
        # termasuk XAUUSD/BTCUSD di mana 0.0003 nyaris nol relatif terhadap
        # harga. Ini membuat biaya exit tidak konsisten dengan biaya entry.
        spread = self._get_realistic_spread(trade.symbol)
        try:
            tp_method = self.settings.get("paper_trading", {}).get("tp_detection_method", "close_price")
            sl_conflict = self.settings.get("paper_trading", {}).get("realistic_sl_tp_conflict", "sl_wins")
        except Exception:
            tp_method = "close_price"
            sl_conflict = "sl_wins"

        # Realized R must be measured against the risk taken at entry, not the
        # stop that trailing may have moved since. Resolve it once per call.
        risk_pct = trade.initial_risk_pct if trade.initial_risk_pct is not None else trade.risk_pct
        if risk_pct is None or float(risk_pct) <= 0.0:
            risk_pct = None
        initial_stop = await self._resolve_initial_stop_loss(session, trade)
        sl_distance = validated_stop_distance(trade.direction, trade.entry_price, initial_stop)
        if sl_distance is None:
            logger.error(
                f"[PAPER] Unverifiable risk anchor for trade {trade.id} "
                f"({trade.symbol} {trade.direction}): entry={trade.entry_price} "
                f"initial_stop={initial_stop}. Realized PnL will be recorded as unverified."
            )

        def _get_slip_key(bar_timestamp, is_news):
            if is_news:
                return "news"
            if bar_timestamp:
                hour = bar_timestamp.hour
                if 21 <= hour <= 23 or 0 <= hour < 2:
                    return "off_peak"
            return "normal"

        for bar in bars:
            is_news = await self._is_news_environment(session, trade, bar.timestamp)
            slip_key = _get_slip_key(bar.timestamp, is_news)

            is_weekend_open = (
                bar.timestamp
                and bar.timestamp.weekday() == 6  # Sunday
                and 20 <= bar.timestamp.hour <= 22
            )
            if is_weekend_open:
                slip_key = "weekend_open"

            slippage = SLIPPAGE_MODEL.get(trade.symbol, {}).get(slip_key, spread)
            sl_hit = False
            tp_hit = False

            # ============================================================
            # Symmetrical touch detection for long and short directions
            # Standard MT5 FX OHLCV bars represent BID prices.
            # BUY: closed with SELL -> receives BID price
            # SELL: closed with BUY -> pays ASK = BID + spread
            # ============================================================
            if trade.direction == "buy":
                # SL hit: BID drops to or below stop loss
                sl_hit = bar.low <= trade.stop_loss
                # TP hit: BID rises to or above take profit
                if tp_method == "close_price":
                    tp_hit = bar.close >= trade.take_profit
                else:
                    tp_hit = bar.high >= trade.take_profit
            else:  # sell
                # SL hit: BID rises to or above stop loss (close BUY, pays ASK = SL + spread)
                sl_hit = bar.high >= trade.stop_loss
                # TP hit: BID drops to or below take profit (close BUY, pays ASK = TP + spread)
                if tp_method == "close_price":
                    tp_hit = bar.close <= trade.take_profit
                else:
                    tp_hit = bar.low <= trade.take_profit

            # If the same bar touches both boundaries, prioritize SL (conservative risk accounting)
            if sl_hit and tp_hit:
                if sl_conflict == "sl_wins":
                    tp_hit = False

            if not sl_hit and not tp_hit:
                continue

            # ============================================================
            # Symmetrical exit price calculation (accounting for half-spread & slippage)
            # ============================================================
            gap_multiplier = 2.0 if is_news else 1.5
            actual_slippage = slippage * gap_multiplier
            # Apply half-spread symmetrically on exit legs for both long and short positions.
            if sl_hit:
                # A stop at/beyond entry is a breakeven or profit-locked trailing
                # stop. Its PnL must come from the exit price, not be forced to 0.
                is_be_or_profit_sl = False
                if trade.entry_price and trade.stop_loss:
                    if trade.direction == "buy" and trade.stop_loss >= trade.entry_price:
                        is_be_or_profit_sl = True
                    elif trade.direction == "sell" and trade.stop_loss <= trade.entry_price:
                        is_be_or_profit_sl = True

                if is_be_or_profit_sl:
                    if trade.direction == "buy":
                        exit_price = max(trade.entry_price, trade.stop_loss - spread / 2)
                    else:
                        exit_price = min(trade.entry_price, trade.stop_loss + spread / 2)
                    exit_reason = "breakeven" if abs(exit_price - trade.entry_price) < 1e-9 else "trailing_sl"
                else:
                    exit_reason = "sl_hit"
                    if trade.direction == "buy":
                        exit_price = trade.stop_loss - spread / 2 - actual_slippage
                    else:
                        exit_price = trade.stop_loss + spread / 2 + actual_slippage
            else:
                exit_reason = "tp_hit"
                if trade.direction == "buy":
                    exit_price = trade.take_profit - spread / 2 - slippage * 0.5
                else:
                    exit_price = trade.take_profit + spread / 2 + slippage * 0.5

            # Realized R against the immutable entry anchor. Never fall back to
            # the mutable trailing stop and never invent a default R.
            rr_achieved: float | None = None
            pnl_pct: float | None = None
            if trade.entry_price is not None and exit_price is not None:
                if sl_distance is not None and risk_pct is not None:
                    actual_move = (
                        float(exit_price) - float(trade.entry_price)
                        if trade.direction == "buy"
                        else float(trade.entry_price) - float(exit_price)
                    )
                    rr_achieved = actual_move / sl_distance
                    pnl_pct = risk_pct * rr_achieved
                    trade.accounting_status = "ok"
                else:
                    trade.accounting_status = "invalid_initial_stop"
            else:
                trade.accounting_status = "invalid_exit_price"

            raw_opened = trade.opened_at
            raw_bar_ts = bar.timestamp
            if raw_opened is not None and raw_bar_ts is not None:
                bar_ts = raw_bar_ts if raw_bar_ts.tzinfo is not None else raw_bar_ts.replace(tzinfo=timezone.utc)
                open_ts = raw_opened if raw_opened.tzinfo is not None else raw_opened.replace(tzinfo=timezone.utc)
                holding_hours = max(0.01, (bar_ts - open_ts).total_seconds() / 3600.0)
            else:
                holding_hours = 0.0
            trade.holding_hours = holding_hours

            if holding_hours > 24 and pnl_pct is not None:
                swap_enabled = (
                    self.settings.get("trading", {}).get("edge_strategy", {}).get("swap_modeling_enabled", True)
                )
                if swap_enabled:
                    from monika.domain.market.swap_estimator import estimate_swap_cost

                    lots = (
                        getattr(trade, "requested_lot", None)
                        or getattr(trade, "volume", None)
                        or getattr(trade, "lots", None)
                        or 0.01
                    )
                    mt5_client = getattr(self, "_mt5", None)
                    swap_abs = await estimate_swap_cost(
                        symbol=trade.symbol,
                        direction=trade.direction,
                        lots=float(lots),
                        holding_hours=holding_hours,
                        start_time=trade.opened_at,
                        mt5_client=mt5_client,
                    )
                    init_bal = float(self.settings.get("paper_trading", {}).get("initial_balance", 10000.0) or 10000.0)
                    pnl_pct += swap_abs / max(1.0, init_bal) * 100

            trade.status = "closed"
            trade.closed_at = bar.timestamp if bar.timestamp.tzinfo is not None else bar.timestamp.replace(tzinfo=UTC)
            raw_closed = trade.closed_at
            if raw_opened is not None and raw_closed is not None:
                c_ts = raw_closed if raw_closed.tzinfo is not None else raw_closed.replace(tzinfo=timezone.utc)
                o_ts = raw_opened if raw_opened.tzinfo is not None else raw_opened.replace(tzinfo=timezone.utc)
                if c_ts < o_ts:
                    trade.closed_at = raw_opened
            trade.slippage_applied = slippage if exit_reason == "sl_hit" else 0.0
            trade.exit_price = exit_price
            trade.exit_reason = exit_reason[:100]
            trade.detection_method = f"{tp_method}_tp_{sl_conflict}_sl"[:100]
            trade.pnl_pct = round(pnl_pct, 4) if pnl_pct is not None else None

            return {
                "symbol": trade.symbol,
                "direction": trade.direction,
                "entry": trade.entry_price,
                "exit": trade.exit_price,
                "pnl_pct": trade.pnl_pct,
                "exit_reason": trade.exit_reason,
                "holding_hours": trade.holding_hours,
                "rr_achieved": rr_achieved,
                "accounting_status": trade.accounting_status,
                "detection_tf": timeframe,
            }
        return None

    async def check_and_close_trades(self, session: AsyncSession) -> list[dict]:
        """Check and close paper trades using M15 data for accuracy."""
        async with _PAPER_TRACKER_LOCK:
            closed = []
            open_trades = (
                (await session.execute(select(PaperTradeRecord).where(PaperTradeRecord.status == "open")))
                .scalars()
                .all()
            )

            now = clock.now()
            MAX_TRADE_AGE_HOURS = float(self.settings.get("paper_trading", {}).get("max_paper_trade_holding_hours", 48))

            for trade in open_trades:
                result = None
                current_closed_item = None
                try:
                    # NEW: Force close sangat tua trades yang mungkin stuck karena data issue
                    if trade.opened_at:
                        age_hours = (now - trade.opened_at).total_seconds() / 3600
                        if age_hours > MAX_TRADE_AGE_HOURS:
                            # Coba dapatkan current price untuk estimate P&L
                            last_bar = (
                                await session.execute(
                                    select(PriceOHLCV)
                                    .where(PriceOHLCV.symbol == trade.symbol)
                                    .where(PriceOHLCV.timeframe == "H4")
                                    .order_by(PriceOHLCV.timestamp.desc())
                                    .limit(1)
                                )
                            ).scalar_one_or_none()

                            exit_price = float(last_bar.close) if last_bar and last_bar.close else None
                            initial_stop = await self._resolve_initial_stop_loss(session, trade)
                            sl_dist = validated_stop_distance(trade.direction, trade.entry_price, initial_stop)
                            risk_pct = trade.initial_risk_pct if trade.initial_risk_pct is not None else trade.risk_pct
                            if risk_pct is not None and float(risk_pct) <= 0.0:
                                risk_pct = None

                            pnl_pct: float | None = None
                            if exit_price is None:
                                trade.accounting_status = "invalid_exit_price"
                                logger.error(
                                    f"[PAPER] Force-close {trade.symbol} trade {trade.id}: no price bar available; "
                                    "PnL left unverified"
                                )
                            elif sl_dist is None or risk_pct is None:
                                trade.accounting_status = "invalid_initial_stop"
                                logger.error(
                                    f"[PAPER] Force-close {trade.symbol} trade {trade.id}: invalid risk anchor "
                                    f"(entry={trade.entry_price}, initial_sl={initial_stop}, risk_pct={risk_pct}); "
                                    "PnL left unverified"
                                )
                            else:
                                move = (
                                    exit_price - trade.entry_price
                                    if trade.direction == "buy"
                                    else trade.entry_price - exit_price
                                )
                                pnl_pct = (move / sl_dist) * float(risk_pct)
                                trade.accounting_status = "ok"

                            if age_hours > 24 and pnl_pct is not None:
                                swap_enabled = (
                                    self.settings.get("trading", {})
                                    .get("edge_strategy", {})
                                    .get("swap_modeling_enabled", True)
                                )
                                if swap_enabled:
                                    from monika.domain.market.swap_estimator import estimate_swap_cost

                                    lots = (
                                        getattr(trade, "requested_lot", None)
                                        or getattr(trade, "volume", None)
                                        or getattr(trade, "lots", None)
                                        or 0.01
                                    )
                                    swap_abs = await estimate_swap_cost(
                                        symbol=trade.symbol,
                                        direction=trade.direction,
                                        lots=float(lots),
                                        holding_hours=age_hours,
                                        start_time=trade.opened_at,
                                        mt5_client=getattr(self, "_mt5", None),
                                    )
                                    init_bal = float(
                                        self.settings.get("paper_trading", {}).get("initial_balance", 10000.0)
                                        or 10000.0
                                    )
                                    pnl_pct += swap_abs / max(1.0, init_bal) * 100

                            trade.status = "closed"
                            trade.closed_at = now
                            trade.exit_price = exit_price
                            trade.exit_reason = "max_holding_time"
                            trade.pnl_pct = round(pnl_pct, 4) if pnl_pct is not None else None
                            trade.holding_hours = age_hours
                            await self._close_linked_position(session, trade)
                            logger.warning(
                                f"[PAPER] Force-closed {trade.symbol} after {age_hours:.0f}h (max holding time), "
                                f"accounting={trade.accounting_status}"
                            )
                            current_closed_item = {
                                "symbol": trade.symbol,
                                "exit_reason": "max_holding_time",
                                "pnl_pct": trade.pnl_pct,
                                "accounting_status": trade.accounting_status,
                            }
                            closed.append(current_closed_item)
                            try:
                                await self._record_factor_outcomes(session, trade)
                            except Exception as e:
                                logger.debug(f"Factor outcome recording failed (non-fatal): {e}")
                            try:
                                await self._record_decay_outcome(session, trade)
                            except Exception as e:
                                logger.debug(f"Decay outcome recording failed (non-fatal): {e}")
                            continue

                    # Step 1: Handle pending limit orders - check if price reached entry level
                    if getattr(trade, "is_pending_fill", False) and trade.stated_entry_price:
                        was_filled = await self._try_fill_pending_order(session, trade)
                        if not was_filled:
                            # Check if order has expired (pending for more than 48h)
                            age_hours = (clock.now() - trade.opened_at).total_seconds() / 3600
                            if age_hours > 48:
                                trade.status = "closed"
                                trade.closed_at = clock.now()
                                trade.exit_reason = "expired_limit"
                                trade.pnl_pct = 0.0
                                trade.exit_price = trade.entry_price
                                # No capital was ever at risk: zero PnL is a fact,
                                # not an unverified estimate.
                                trade.accounting_status = "not_filled"
                                await self._close_linked_position(session, trade)
                                logger.info(
                                    f"[PAPER] EXPIRED limit order {trade.symbol} {trade.direction} (never filled after 48h)"
                                )
                                try:
                                    await self._record_factor_outcomes(session, trade)
                                except Exception as e:
                                    logger.debug(f"Factor outcome recording failed (non-fatal): {e}")
                            continue  # Skip SL/TP check if still pending

                    # Step 2: Try to detect SL/TP - adaptive TF based on trade age
                    result = None
                    trade_age_h = (clock.now() - trade.opened_at).total_seconds() / 3600
                    tfs_to_check = ["M15", "H1"] if trade_age_h < 24 else ["H1", "H4"]

                    for timeframe in tfs_to_check:
                        bars = await self._get_bars_since_open(session, trade, timeframe)
                        if bars:
                            result = await self._check_sl_tp(session, trade, bars, timeframe)
                            if result:
                                break

                    if result:
                        current_closed_item = result
                        closed.append(result)
                        await self._close_linked_position(session, trade)
                        pnl_text = f"{result['pnl_pct']:.2f}%" if result["pnl_pct"] is not None else "UNVERIFIED"
                        logger.info(
                            f"[PAPER] Closed {trade.symbol} {trade.direction}: "
                            f"{result['exit_reason']}, P&L={pnl_text}, "
                            f"accounting={result.get('accounting_status', 'unknown')}, "
                            f"detected_on={result.get('detection_tf', 'unknown')}"
                        )

                        # IMP-11: Record individual factor outcomes for attribution analysis
                        try:
                            await self._record_factor_outcomes(session, trade)
                        except Exception as e:
                            logger.debug(f"Factor outcome recording failed (non-fatal): {e}")

                        try:
                            from monika.core.analytics.trade_autopsy import run_trade_autopsy

                            await run_trade_autopsy(session, trade)
                        except Exception as e:
                            logger.debug(f"Trade autopsy failed (non-fatal): {e}")

                        try:
                            await self._record_decay_outcome(session, trade)
                        except Exception as e:
                            logger.debug(f"Decay outcome recording failed (non-fatal): {e}")

                        if trade.analysis_id and trade.pnl_pct is not None:
                            try:
                                from monika.application.analysis.memory.outcome_linker import OutcomeLinker

                                await OutcomeLinker(self.settings).process_closed_position(
                                    session,
                                    analysis_id=trade.analysis_id,
                                    pnl=trade.pnl_pct,
                                    holding_hours=trade.holding_hours or 0.0,
                                    exit_reason=trade.exit_reason or "unknown",
                                )
                            except Exception as e:
                                logger.debug(f"OutcomeLinker failed (non-fatal): {e}")
                except Exception as e:
                    logger.error(f"[PAPER] Trade {trade.id} ({trade.symbol}) check failed, skipping this cycle: {e}")
                    try:
                        await session.rollback()
                    except Exception:
                        pass
                    # If this trade had partially appended a result before failing, remove it
                    if current_closed_item and current_closed_item in closed:
                        closed.remove(current_closed_item)
                    continue

            if closed or any(t.status == "closed" and t.exit_reason == "expired_limit" for t in open_trades):
                await session.commit()
                await self.check_recent_streak(session)

            return closed

    async def _record_factor_outcomes(self, session: AsyncSession, trade: PaperTradeRecord) -> None:
        """IMP-11: Record individual confluence factor outcomes after a trade closes."""
        import json as _json

        from monika.infrastructure.database.models import AssetAnalysis, ConfluenceFactorOutcome

        if not trade.analysis_id:
            return

        try:
            analysis = (
                await session.execute(select(AssetAnalysis).where(AssetAnalysis.id == trade.analysis_id))
            ).scalar_one_or_none()

            if not analysis or not analysis.confluence_factors_json:
                return

            factors_raw = _json.loads(analysis.confluence_factors_json)
            # Normalize: factors may be list or dict
            if isinstance(factors_raw, list):
                active_factors = set(factors_raw)
            elif isinstance(factors_raw, dict):
                active_factors = {k for k, v in factors_raw.items() if v}
            else:
                active_factors = set()

            ALL_POSSIBLE_FACTORS = [
                "fundamental_bias",
                "dxy_confirms",
                "d1_trend",
                "rsi_neutral",
                "near_fvg",
                "near_order_block",
                "in_ote_zone",
                "near_sr_zone",
                "cot_aligned",
                "vix_ok",
                "post_event_entry",
                "session_prime",
            ]

            for factor in ALL_POSSIBLE_FACTORS:
                outcome_row = ConfluenceFactorOutcome(
                    paper_trade_id=trade.id,
                    analysis_id=trade.analysis_id,
                    symbol=trade.symbol,
                    factor_name=factor,
                    was_present=factor in active_factors,
                    trade_outcome=trade.exit_reason,
                    pnl_pct=trade.pnl_pct,
                )
                session.add(outcome_row)
            # Commit handled by caller
        except Exception as e:
            logger.debug(f"_record_factor_outcomes inner error: {e}")

    async def _record_decay_outcome(self, session: AsyncSession, trade: PaperTradeRecord) -> None:
        """Record paper trade outcome into StrategyDecayMonitor for edge alpha degradation tracking."""
        if not trade.analysis_id:
            return
        if trade.pnl_pct is None:
            logger.warning(f"[PAPER] Skipping decay outcome for trade {trade.id}: PnL is unverified")
            return
        try:
            from monika.infrastructure.database.models import AssetAnalysis

            analysis = await session.get(AssetAnalysis, trade.analysis_id)
            if analysis is None:
                res = await session.execute(select(AssetAnalysis).where(AssetAnalysis.id == trade.analysis_id))
                analysis = res.scalar_one_or_none()

            strat_id = getattr(analysis, "source_strategy_id", None) if analysis else None
            if analysis and strat_id is not None:
                from monika.application.analysis.strategies.decay_monitor import get_strategy_decay_monitor

                mon = get_strategy_decay_monitor()
                mon.record_trade_outcome(
                    strategy_id=str(strat_id),
                    win=(trade.pnl_pct or 0.0) > 0,
                    is_paper=True,
                )
                await mon.save_to_db(session)
                logger.debug(
                    f"[PAPER] Recorded decay outcome for strategy '{strat_id}', win={(trade.pnl_pct or 0.0) > 0}"
                )
        except Exception as d_err:
            logger.debug(f"[PAPER] StrategyDecayMonitor record error: {d_err}")

    async def _try_fill_pending_order(self, session: AsyncSession, trade: PaperTradeRecord) -> bool:
        """Check if a pending limit order has been filled. Returns True if filled."""
        bars = await self._get_bars_since_open(session, trade, "M15")
        if not bars:
            bars = await self._get_bars_since_open(session, trade, "H1")
        if not bars:
            bars = await self._get_bars_since_open(session, trade, "H4")
        if not bars:
            return False

        stated_entry = trade.stated_entry_price
        if stated_entry is None:
            return False

        for bar in bars:
            # For BUY limit: price must drop to or below the limit price
            if trade.direction == "buy" and bar.low <= stated_entry:
                # Filled at stated entry price (limit order)
                trade.entry_price = stated_entry
                trade.is_pending_fill = False
                trade.filled_at = bar.timestamp
                logger.info(f"[PAPER] BUY LIMIT FILLED {trade.symbol} @ {stated_entry:.5f}")
                await session.commit()
                return True

            # For SELL limit: price must rise to or above the limit price
            elif trade.direction == "sell" and bar.high >= stated_entry:
                trade.entry_price = stated_entry
                trade.is_pending_fill = False
                trade.filled_at = bar.timestamp
                logger.info(f"[PAPER] SELL LIMIT FILLED {trade.symbol} @ {stated_entry:.5f}")
                await session.commit()
                return True

        return False

    async def get_suspended_symbols(self, session: AsyncSession) -> list[str]:
        """Return list of symbols currently suspended due to poor performance"""
        from sqlalchemy import select

        from monika.infrastructure.database.models import SystemConfig

        cfg = (
            await session.execute(select(SystemConfig).where(SystemConfig.key == "suspended_symbols"))
        ).scalar_one_or_none()

        if not cfg or not cfg.value:
            return []

        try:
            import json

            data = json.loads(cfg.value)
            now = clock.now()
            # Filter out suspensions that have expired
            active = [s for s in data if datetime.fromisoformat(s["until"]) > now]
            return [s["symbol"] for s in active]
        except Exception:
            return []

    async def check_and_suspend_poor_performers(self, session: AsyncSession, settings: dict) -> list[str]:
        """
        Auto-suspend symbols with consecutive losses.
        Returns list of newly suspended symbols.
        Respects trading.paper_trading.streak_loss_policy and prevents infinite re-suspension loop.
        """
        import json

        from sqlalchemy import select

        from monika.infrastructure.database.models import PaperTradeRecord, SystemConfig

        paper_cfg = settings.get("trading", {}).get("paper_trading", {})
        streak_policy = paper_cfg.get("streak_loss_policy", "warn_and_scale")
        is_auto_execute = settings.get("trading", {}).get("auto_execute", False)

        # Jika paper exploration mode (disabled / warn_and_scale) dan bukan live trading:
        if not is_auto_execute and streak_policy in ("disabled", "warn_and_scale"):
            logger.debug(f"[PaperTracker] Skipping auto-suspension (streak_loss_policy: '{streak_policy}')")
            return []

        newly_suspended = []
        max_consecutive_losses = settings.get("trading", {}).get("risk", {}).get("max_consecutive_losses_per_symbol", 3)
        suspension_hours = paper_cfg.get(
            "suspension_hours",
            settings.get("trading", {}).get("risk", {}).get("suspension_hours_after_consecutive_losses", 12),
        )

        asset_universe = settings.get("trading", {}).get("asset_universe", [])

        cfg = (
            await session.execute(select(SystemConfig).where(SystemConfig.key == "suspended_symbols"))
        ).scalar_one_or_none()

        current = []
        if cfg and cfg.value:
            try:
                current = json.loads(cfg.value)
            except Exception:
                current = []

        now = clock.now()

        for symbol in asset_universe:
            # FIX INFINITE LOOP: Cek apakah simbol ini sebelumnya pernah di-suspend
            prev_entry = next((s for s in current if s.get("symbol") == symbol), None)
            last_suspended_until = None
            if prev_entry and "until" in prev_entry:
                try:
                    last_suspended_until = datetime.fromisoformat(prev_entry["until"])
                except Exception:
                    last_suspended_until = None

            query = (
                select(PaperTradeRecord)
                .where(PaperTradeRecord.symbol == symbol)
                .where(PaperTradeRecord.status == "closed")
                .where(PaperTradeRecord.exit_reason.in_(["sl_hit", "tp_hit"]))
            )
            # Jika suspensi sebelumnya telah expired, HANYA hitung trade yang ditutup SETELAH masa suspensi berakhir
            if last_suspended_until and last_suspended_until <= now:
                query = query.where(PaperTradeRecord.closed_at > last_suspended_until)

            recent = (
                (
                    await session.execute(
                        query.order_by(PaperTradeRecord.closed_at.desc()).limit(max_consecutive_losses + 1)
                    )
                )
                .scalars()
                .all()
            )

            consecutive_losses = 0
            for trade in recent:
                if trade.exit_reason == "sl_hit":
                    consecutive_losses += 1
                else:
                    break

            if consecutive_losses >= max_consecutive_losses:
                # Suspend this symbol
                until = (now + timedelta(hours=suspension_hours)).isoformat()

                # Remove old entry for this symbol if exists
                current = [s for s in current if s.get("symbol") != symbol]
                current.append(
                    {
                        "symbol": symbol,
                        "suspended_at": now.isoformat(),
                        "until": until,
                        "reason": f"{consecutive_losses} consecutive losses",
                    }
                )

                newly_suspended.append(symbol)
                logger.warning(
                    f"AUTO-SUSPENDED {symbol}: {consecutive_losses} consecutive SL hits. Suspended for {suspension_hours}h."
                )

                try:
                    from monika.infrastructure.notifications.telegram_notifier import AgentNotifier

                    await AgentNotifier().send_warning(
                        f"[DIJEDA] <b>{symbol} Auto-Suspended</b>\n"
                        f"{consecutive_losses} consecutive losses detected.\n"
                        f"Suspended for {suspension_hours}h until {until[:16]} UTC.\n"
                        f"Review recent analyses to identify systematic issue."
                    )
                except Exception:
                    pass

        if newly_suspended:
            if cfg:
                cfg.value = json.dumps(current)
            else:
                session.add(SystemConfig(key="suspended_symbols", value=json.dumps(current)))
            await session.commit()

        return newly_suspended

    async def suspend_symbol(
        self, session: AsyncSession, symbol: str, duration_hours: float = 24.0, reason: str = "manual_command"
    ) -> dict:
        """Suspend trading untuk simbol tertentu secara manual dengan durasi waktu."""
        import json
        from datetime import timedelta

        from sqlalchemy import select

        from monika.infrastructure.database.models import SystemConfig

        sym_norm = symbol.strip().upper().replace("/", "")
        cfg = (
            await session.execute(select(SystemConfig).where(SystemConfig.key == "suspended_symbols"))
        ).scalar_one_or_none()

        current = []
        if cfg and cfg.value:
            try:
                current = json.loads(cfg.value)
            except Exception:
                current = []

        now = clock.now()
        until = now + timedelta(hours=duration_hours)
        until_iso = until.isoformat()

        entry = {"symbol": sym_norm, "until": until_iso, "reason": reason}
        updated = False
        for s in current:
            if s.get("symbol", "").upper() == sym_norm:
                s["until"] = until_iso
                s["reason"] = reason
                updated = True
                break
        if not updated:
            current.append(entry)

        if cfg:
            cfg.value = json.dumps(current)
        else:
            session.add(SystemConfig(key="suspended_symbols", value=json.dumps(current)))
        await session.commit()
        logger.warning(f"[PaperTracker] Symbol {sym_norm} suspended manually until {until_iso} (reason={reason})")
        return {"symbol": sym_norm, "until": until_iso, "duration_hours": duration_hours, "reason": reason}

    async def unsuspend_symbol(self, session: AsyncSession, symbol: str) -> bool:
        """Buka suspensi untuk simbol tertentu."""
        import json

        from sqlalchemy import select

        from monika.infrastructure.database.models import SystemConfig

        cfg = (
            await session.execute(select(SystemConfig).where(SystemConfig.key == "suspended_symbols"))
        ).scalar_one_or_none()
        if not cfg or not cfg.value:
            return False
        try:
            current = json.loads(cfg.value)
            new_list = [s for s in current if s.get("symbol", "").upper() != symbol.upper()]
            if len(new_list) != len(current):
                cfg.value = json.dumps(new_list)
                await session.commit()
                logger.info(f"[PaperTracker] Symbol {symbol} unsuspended successfully.")
                return True
        except Exception as e:
            logger.error(f"Failed to unsuspend {symbol}: {e}")
        return False

    async def unsuspend_all(self, session: AsyncSession) -> list[str]:
        """Buka suspensi untuk semua simbol."""
        import json

        from sqlalchemy import select

        from monika.infrastructure.database.models import SystemConfig

        cfg = (
            await session.execute(select(SystemConfig).where(SystemConfig.key == "suspended_symbols"))
        ).scalar_one_or_none()
        if not cfg or not cfg.value:
            return []
        try:
            current = json.loads(cfg.value)
            cleared_symbols = [s.get("symbol") for s in current if s.get("symbol")]
            cfg.value = json.dumps([])
            await session.commit()
            logger.info(f"[PaperTracker] All symbols unsuspended: {cleared_symbols}")
            return cleared_symbols
        except Exception as e:
            logger.error(f"Failed to unsuspend all: {e}")
            return []

    async def get_streak_status(self, session: AsyncSession, symbol: str) -> dict:
        """Mengambil status streak loss dan suspensi untuk simbol tertentu."""
        from sqlalchemy import select

        from monika.infrastructure.database.models import PaperTradeRecord

        recent = (
            (
                await session.execute(
                    select(PaperTradeRecord)
                    .where(PaperTradeRecord.symbol == symbol)
                    .where(PaperTradeRecord.status == "closed")
                    .where(PaperTradeRecord.exit_reason.in_(["sl_hit", "tp_hit"]))
                    .order_by(PaperTradeRecord.closed_at.desc())
                    .limit(5)
                )
            )
            .scalars()
            .all()
        )

        consecutive_losses = 0
        for trade in recent:
            if trade.exit_reason == "sl_hit":
                consecutive_losses += 1
            else:
                break

        suspended_list = await self.get_suspended_symbols(session)
        is_suspended = symbol in suspended_list

        paper_cfg = (
            self.settings.get("trading", {}).get("paper_trading", {})
            if hasattr(self, "settings") and self.settings
            else {}
        )
        streak_policy = paper_cfg.get("streak_loss_policy", "warn_and_scale")

        return {
            "symbol": symbol,
            "consecutive_losses": consecutive_losses,
            "is_suspended": is_suspended,
            "streak_policy": streak_policy,
        }

    async def get_statistics(
        self, session: AsyncSession, days_back: int | None = None, symbol: str | None = None
    ) -> dict:
        """Hitung win rate dan statistik performa komprehensif."""
        from datetime import datetime, timedelta, timezone

        from sqlalchemy import select

        query = (
            select(PaperTradeRecord, AssetAnalysis)
            .outerjoin(AssetAnalysis, PaperTradeRecord.analysis_id == AssetAnalysis.id)
            .where(PaperTradeRecord.status == "closed")
            # Phase 0: only rows with a verified entry-time risk anchor may
            # contribute to expectancy/win-rate/PF. Unverified rows are excluded
            # instead of being silently counted as breakeven.
            .where(PaperTradeRecord.accounting_status == "ok")
        )
        if days_back is not None:
            since = clock.now() - timedelta(days=days_back)
            query = query.where(PaperTradeRecord.closed_at >= since)
        if symbol is not None:
            query = query.where(PaperTradeRecord.symbol == symbol)

        results = (await session.execute(query)).all()

        if not results:
            return {
                "total_trades": 0,
                "market_trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate_market_pct": 0.0,
                "win_rate_operational_pct": 0.0,
                "win_rate_pct": 0.0,
                "avg_pnl_pct": 0.0,
                "total_pnl_pct": 0.0,
                "avg_win_pct": 0.0,
                "avg_loss_pct": 0.0,
                "avg_rr_achieved": 0.0,
                "expectancy_per_trade_pct": 0.0,
                "expectancy_per_trade_R": 0.0,
                "has_positive_edge": False,
                "edge_alert": False,
                "by_confluence": {},
                "by_priced_in": {},
                "session_buckets": {
                    "tokyo_00_08": {"label": "Tokyo (00:00-08:00 UTC)", "wins": 0, "total": 0},
                    "london_08_13": {"label": "London Pre-Overlap (08:00-13:00 UTC)", "wins": 0, "total": 0},
                    "overlap_13_16": {"label": "NY-London Overlap (13:00-16:00 UTC)", "wins": 0, "total": 0},
                    "ny_16_21": {"label": "NY Post-London (16:00-21:00 UTC)", "wins": 0, "total": 0},
                    "offpeak_21_00": {"label": "Off-Peak (21:00-00:00 UTC)", "wins": 0, "total": 0},
                },
                "avg_win_hold_hours": 0.0,
                "avg_loss_hold_hours": 0.0,
                "by_symbol": {},
                "by_symbol_direction": {},
                "recent_20": [],
            }

        # Pisahkan list paper trades (r) dan list tuples untuk iterasi
        records = [r for r, a in results]

        tp_hits = [r for r in records if r.exit_reason == "tp_hit"]
        sl_hits = [r for r in records if r.exit_reason == "sl_hit"]
        pnl_values = [r.pnl_pct or 0 for r in records]

        market_records = [r for r in records if r.exit_reason in MARKET_OUTCOME_EXIT_REASONS]

        avg_win_pct = sum(r.pnl_pct or 0 for r in tp_hits) / len(tp_hits) if tp_hits else 0
        avg_loss_pct = abs(sum(r.pnl_pct or 0 for r in sl_hits) / len(sl_hits)) if sl_hits else 0

        market_total = len(market_records)
        win_rate_market = len(tp_hits) / market_total if market_total > 0 else 0
        loss_rate_market = 1 - win_rate_market if market_total > 0 else 0

        win_rate_operational = len(tp_hits) / len(records) if records else 0

        # Expectancy per trade
        expectancy = (win_rate_market * avg_win_pct) - (loss_rate_market * avg_loss_pct)
        avg_rr = avg_win_pct / avg_loss_pct if avg_loss_pct > 0 else 0
        expectancy_r = (win_rate_market * avg_rr) - loss_rate_market

        # Compute extended metrics (Confluence, Priced In, Sessions, Durations)
        by_confluence = {}
        by_priced_in = {}
        session_buckets = {
            "tokyo_00_08": {"label": "Tokyo (00:00-08:00 UTC)", "wins": 0, "total": 0},
            "london_08_13": {"label": "London Pre-Overlap (08:00-13:00 UTC)", "wins": 0, "total": 0},
            "overlap_13_16": {"label": "NY-London Overlap (13:00-16:00 UTC)", "wins": 0, "total": 0},
            "ny_16_21": {"label": "NY Post-London (16:00-21:00 UTC)", "wins": 0, "total": 0},
            "offpeak_21_00": {"label": "Off-Peak (21:00-00:00 UTC)", "wins": 0, "total": 0},
        }

        win_durations = []
        loss_durations = []

        for r, a in results:
            is_win = (r.pnl_pct or 0) > 0

            # Confluence
            if a and a.confluence_score is not None:
                cs = a.confluence_score
                cb = f"{cs}"
                if cb not in by_confluence:
                    by_confluence[cb] = {"wins": 0, "total": 0}
                by_confluence[cb]["total"] += 1
                if is_win:
                    by_confluence[cb]["wins"] += 1

            # Priced In
            if a and a.priced_in_score is not None:
                ps = a.priced_in_score
                pb = f"pi_{ps}"
                if pb not in by_priced_in:
                    by_priced_in[pb] = {"score": ps, "wins": 0, "total": 0}
                by_priced_in[pb]["total"] += 1
                if is_win:
                    by_priced_in[pb]["wins"] += 1

            # Sessions
            if r.opened_at:
                h = r.opened_at.hour
                if 0 <= h < 8:
                    key = "tokyo_00_08"
                elif 8 <= h < 13:
                    key = "london_08_13"
                elif 13 <= h < 16:
                    key = "overlap_13_16"
                elif 16 <= h < 21:
                    key = "ny_16_21"
                else:
                    key = "offpeak_21_00"
                session_buckets[key]["total"] += 1
                if is_win:
                    session_buckets[key]["wins"] += 1

            # Durations
            if r.holding_hours:
                if is_win:
                    win_durations.append(r.holding_hours)
                else:
                    loss_durations.append(r.holding_hours)

        history = []
        for record in records:
            history.append(
                {
                    "symbol": record.symbol,
                    "direction": record.direction,
                    "exit_reason": record.exit_reason,
                    "pnl_pct": record.pnl_pct or 0,
                    "opened_at": record.opened_at.isoformat() if record.opened_at else None,
                    "closed_at": record.closed_at.isoformat() if record.closed_at else None,
                }
            )

        # Comprehensive quantitative ratios (Sharpe, Sortino, Calmar, Profit Factor, Max Drawdown)
        import math

        gross_profit = sum(p for p in pnl_values if p > 0)
        gross_loss = abs(sum(p for p in pnl_values if p < 0))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0.0)

        # Drawdown calculation
        curr_eq = 100.0
        peak = 100.0
        max_dd = 0.0
        for p in pnl_values:
            curr_eq *= 1.0 + (p / 100.0)
            if curr_eq > peak:
                peak = curr_eq
            dd = ((peak - curr_eq) / peak) * 100.0 if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd

        # Sharpe & Sortino ratios (annualized scaling based on 252 trading days)
        if len(pnl_values) >= 2:
            mean_ret = sum(pnl_values) / len(pnl_values)
            variance = sum((p - mean_ret) ** 2 for p in pnl_values) / (len(pnl_values) - 1)
            std_dev = math.sqrt(variance) if variance > 0 else 0.0
            sharpe_ratio = (mean_ret / std_dev) * math.sqrt(252) if std_dev > 0 else 0.0

            downside_pnl = [p for p in pnl_values if p < 0]
            if downside_pnl:
                downside_var = sum(p**2 for p in downside_pnl) / len(downside_pnl)
                downside_std = math.sqrt(downside_var) if downside_var > 0 else 0.0
                sortino_ratio = (mean_ret / downside_std) * math.sqrt(252) if downside_std > 0 else 0.0
            else:
                sortino_ratio = sharpe_ratio if sharpe_ratio > 0 else 0.0
        else:
            sharpe_ratio = 0.0
            sortino_ratio = 0.0

        total_pnl_val = sum(pnl_values)
        calmar_ratio = (total_pnl_val / max_dd) if max_dd > 0 else (total_pnl_val if total_pnl_val > 0 else 0.0)

        return {
            "total_trades": len(records),
            "market_trades": market_total,
            "wins": len(tp_hits),
            "losses": len(sl_hits),
            "win_rate_market_pct": round(win_rate_market * 100, 1),
            "win_rate_operational_pct": round(win_rate_operational * 100, 1),
            "win_rate_pct": round(win_rate_market * 100, 1),
            "avg_pnl_pct": round(sum(pnl_values) / len(pnl_values), 4) if len(pnl_values) > 0 else 0,
            "total_pnl_pct": round(sum(pnl_values), 4),
            "avg_win_pct": round(avg_win_pct, 3),
            "avg_loss_pct": round(avg_loss_pct, 3),
            "avg_rr_achieved": round(avg_rr, 2),
            "expectancy_per_trade_pct": round(expectancy, 4),
            "expectancy_per_trade_R": round(expectancy_r, 3),
            "sharpe_ratio": round(sharpe_ratio, 2),
            "sortino_ratio": round(sortino_ratio, 2),
            "calmar_ratio": round(calmar_ratio, 2),
            "profit_factor": round(profit_factor, 2),
            "max_drawdown_pct": round(max_dd, 2),
            "has_positive_edge": expectancy > 0,
            "edge_alert": expectancy < -0.1,
            "by_confluence": by_confluence,
            "by_priced_in": by_priced_in,
            "session_buckets": session_buckets,
            "avg_win_hold_hours": sum(win_durations) / len(win_durations) if win_durations else 0,
            "avg_loss_hold_hours": sum(loss_durations) / len(loss_durations) if loss_durations else 0,
            "by_symbol": _group_by_symbol(history),
            "by_symbol_direction": _group_by_symbol_direction(history),
            "recent_20": [
                {"symbol": h["symbol"], "exit_reason": h["exit_reason"], "pnl_pct": h["pnl_pct"]} for h in history[-20:]
            ],
        }

    async def check_and_alert_winrate(self, session: AsyncSession, settings: dict, min_trades: int = 10) -> None:
        """
        Kirim alert jika win rate jatuh di bawah batas minimum (breakeven).
        Berjalan setiap kali paper trade selesai (closed).
        """
        stats = await self.get_statistics(session)
        total = stats.get("total_trades", 0)

        if total < min_trades:  # Butuh minimal trades untuk statistik yang valid
            return

        win_rate = stats.get("win_rate_pct", 0)

        # Ambang batas lebih dinamis berdasarkan R:R minimal
        risk_cfg = settings.get("trading", {}).get("risk", {})
        min_rr = risk_cfg.get("min_rr_ratio", 1.3)

        # Breakeven WR% = 100 / (1 + RR)
        breakeven_wr = 100 / (1 + min_rr)
        # Alert threshold = breakeven_wr + 5% (buffer)
        alert_threshold = breakeven_wr + 5

        if win_rate < alert_threshold:
            # Generate insight
            by_symbol = stats.get("by_symbol", {})
            worst_symbol = ""
            worst_pnl = 0
            for sym, s_stats in by_symbol.items():
                sym_pnl = s_stats.get("total_pnl_pct", s_stats.get("pnl_pct", 0))
                if sym_pnl < worst_pnl:
                    worst_pnl = sym_pnl
                    worst_symbol = sym

            msg = (
                f"[DARURAT] <b>Win Rate Alert</b>\n"
                f"Paper trading win rate: {win_rate:.1f}% ({total} trades)\n"
                f"Below minimum threshold: {alert_threshold:.1f}% (Breakeven: {breakeven_wr:.1f}%)\n\n"
                f"System may NOT have statistical edge.\n"
            )
            if worst_symbol:
                msg += f"[PERINGATAN] Worst performing asset: {worst_symbol} ({worst_pnl:.2f}% PnL)\n"

            msg += (
                f"\nAction needed:\n"
                f"• Wait for next Performance Notes generation\n"
                f"• Increase confluence threshold\n"
                f"• Disable {worst_symbol} if bleeding continues"
            )

            logger.warning(f"Win rate alert: {win_rate:.1f}% < {alert_threshold:.1f}%")
            try:
                from monika.infrastructure.notifications.telegram_notifier import AgentNotifier

                await AgentNotifier().send_critical(msg)
            except Exception:
                pass

    async def should_regenerate_performance_notes(self, session: AsyncSession) -> tuple[bool, str]:
        """
        Returns (should_regenerate: bool, reason: str).
        Triggers on: win rate < 40% after 10+ trades, or 10+ new trades since last generation.
        """
        from sqlalchemy import select

        from monika.infrastructure.database.models import SystemConfig

        stats = await self.get_statistics(session)
        total = stats.get("total_trades", 0)
        win_rate = stats.get("win_rate_pct", 50)

        MIN_TRADES_FOR_INITIAL = 15
        if total < MIN_TRADES_FOR_INITIAL:
            return False, f"insufficient_data ({total}/{MIN_TRADES_FOR_INITIAL} trades)"

        # Check autopsy patterns yang mengindikasikan systematic issue
        autopsy_keys = (
            (
                await session.execute(
                    select(SystemConfig.key)
                    .where(SystemConfig.key.like("autopsy_%"))
                    .where(SystemConfig.value.like('%"severity": "high"%'))
                )
            )
            .scalars()
            .all()
        )

        if len(autopsy_keys) >= 3:
            # Ada 3+ high-severity patterns dari autopsy → regenerate
            return (True, f"high_severity_autopsy_patterns_detected ({len(autopsy_keys)} patterns)")

        # Check last generation time
        last_gen_key = "performance_notes_last_gen"
        last_gen_cfg = (
            await session.execute(select(SystemConfig).where(SystemConfig.key == last_gen_key))
        ).scalar_one_or_none()

        if not last_gen_cfg or not last_gen_cfg.value:
            return True, "first_generation"

        import json

        last_gen_data = {}
        try:
            last_gen_data = json.loads(last_gen_cfg.value)
        except Exception:
            return True, "corrupted_state"

        last_gen_total = last_gen_data.get("total_trades", 0)
        last_gen_time_str = last_gen_data.get("timestamp", "2020-01-01")
        # Handle cases where timestamp might not have timezone info or is invalid
        try:
            last_gen_time = datetime.fromisoformat(last_gen_time_str)
            if last_gen_time.tzinfo is None:
                last_gen_time = last_gen_time.replace(tzinfo=UTC)
        except ValueError:
            last_gen_time = clock.now() - timedelta(days=8)

        hours_since = (clock.now() - last_gen_time).total_seconds() / 3600

        # Trigger conditions:
        # Require minimum 20 trades before triggering critical status.
        # Win rate of 35% over 10-12 trades is within normal statistical variance
        # for a profitable system and should not trigger system-wide throttling.
        MIN_TRADES_FOR_CRITICAL = 20
        MIN_TRADES_FOR_POOR = 15

        if win_rate < 35 and hours_since >= 6 and total >= MIN_TRADES_FOR_CRITICAL:
            return True, f"critical_win_rate_{win_rate:.0f}pct_over_{total}_trades"

        if win_rate < 40 and hours_since >= 12 and total >= MIN_TRADES_FOR_POOR:
            return True, f"poor_win_rate_{win_rate:.0f}pct_over_{total}_trades"

        if total - last_gen_total >= 5:  # 5 new trades since last gen
            return True, f"5_new_trades_since_last_gen"

        # TAMBAHKAN: Trigger on consecutive losses (losing streak detection)
        recent = (
            (
                await session.execute(
                    select(PaperTradeRecord)
                    .where(PaperTradeRecord.status == "closed")
                    .where(PaperTradeRecord.exit_reason.in_(["sl_hit", "tp_hit"]))
                    .order_by(PaperTradeRecord.closed_at.desc())
                    .limit(4)
                )
            )
            .scalars()
            .all()
        )
        if len(recent) >= 4 and all(r.exit_reason == "sl_hit" for r in recent):
            return True, "4_consecutive_losses_detected"

        if hours_since >= 24 * 7:  # Weekly regardless (existing Monday behavior)
            return True, "weekly_scheduled"

        return False, "no_trigger"

    async def check_recent_streak(self, session: AsyncSession, lookback: int = 5) -> dict:
        """
        Deteksi losing streak mendadak (misal: 5 kerugian beruntun memicu alarm).
        Lebih sensitif mendeteksi kelemahan dibanding metrik all-time win rate.
        """
        recent = (
            (
                await session.execute(
                    select(PaperTradeRecord)
                    .where(PaperTradeRecord.status == "closed")
                    .where(PaperTradeRecord.exit_reason.in_(["sl_hit", "tp_hit"]))
                    .order_by(PaperTradeRecord.closed_at.desc())
                    .limit(lookback)
                )
            )
            .scalars()
            .all()
        )

        if len(recent) < lookback:
            return {"streak_data": "insufficient", "count": len(recent)}

        losses = [r for r in recent if r.exit_reason == "sl_hit"]
        wins = [r for r in recent if r.exit_reason == "tp_hit"]
        recent_wr = len(wins) / len(recent) * 100

        result = {
            "lookback": lookback,
            "recent_win_rate": recent_wr,
            "recent_wins": len(wins),
            "recent_losses": len(losses),
            "alert_triggered": len(losses) >= lookback - 1,  # 4 dari 5 terakhir loss
        }

        if result["alert_triggered"]:
            msg = (
                f"[KRITIS] <b>LOSING STREAK DETECTED</b>\n"
                f"Last {lookback} trades: {len(losses)} losses, {len(wins)} wins\n"
                f"Recent win rate: {recent_wr:.0f}%\n"
                f"Consider pausing and reviewing recent analyses."
            )
            try:
                from monika.infrastructure.notifications.telegram_notifier import AgentNotifier

                await AgentNotifier().send_critical(msg)
            except Exception:
                pass

        return result

    async def simulate_equity_curve(self, session: AsyncSession, starting_equity: float = 10000.0) -> dict:
        """
        Simulasikan kurva ekuitas (equity curve) untuk hitung max drawdown & growth.
        Menggunakan % risiko per trade dari konfigurasi.
        """
        records = (
            (
                await session.execute(
                    select(PaperTradeRecord)
                    .where(PaperTradeRecord.status == "closed")
                    .order_by(PaperTradeRecord.opened_at.asc())
                )
            )
            .scalars()
            .all()
        )

        if not records:
            return {}

        equity = starting_equity
        peak_equity = starting_equity
        max_drawdown = 0.0
        equity_history = [
            {"date": records[0].opened_at.isoformat() if records[0].opened_at else None, "equity": equity}
        ]

        RISK_PCT = 1.5 / 100  # Default 1.5% risk per trade

        for record in records:
            if record.pnl_pct is not None:
                trade_pnl = equity * (record.pnl_pct / 100.0)
            else:
                trade_pnl = 0.0

            equity += trade_pnl
            peak_equity = max(peak_equity, equity)
            drawdown = (peak_equity - equity) / peak_equity * 100
            max_drawdown = max(max_drawdown, drawdown)

            equity_history.append(
                {
                    "date": record.closed_at.isoformat() if record.closed_at else None,
                    "equity": round(equity, 2),
                    "trade_pnl": round(trade_pnl, 2),
                    "symbol": record.symbol,
                    "direction": record.direction,
                }
            )

        return {
            "starting_equity": starting_equity,
            "final_equity": round(equity, 2),
            "total_return_pct": round((equity - starting_equity) / starting_equity * 100, 2),
            "max_drawdown_pct": round(max_drawdown, 2),
            "equity_history": equity_history[-50:],
        }


def _group_by_symbol(history):
    by_sym = {}
    from monika.core.primitives.constants import MARKET_OUTCOME_EXIT_REASONS

    for t in history:
        sym = t.get("symbol")
        if not sym:
            continue
        if sym not in by_sym:
            by_sym[sym] = {
                "trades": 0,
                "total": 0,
                "wins": 0,
                "losses": 0,
                "pnl_pct": 0.0,
                "total_pnl_pct": 0.0,
                "win_rate": 0.0,
                "_win_pnls": [],
                "_loss_pnls": [],
            }

        # Only count trades for win_rate if they are market exits
        if t.get("exit_reason") in MARKET_OUTCOME_EXIT_REASONS:
            by_sym[sym]["trades"] += 1
            by_sym[sym]["total"] += 1
            if t.get("exit_reason") == "tp_hit" or (t.get("pnl_pct") or 0) > 0:
                by_sym[sym]["wins"] += 1
            else:
                by_sym[sym]["losses"] += 1

        pnl = t.get("pnl_pct", 0) or 0.0
        if pnl > 0:
            by_sym[sym]["_win_pnls"].append(float(pnl))
        elif pnl < 0:
            by_sym[sym]["_loss_pnls"].append(abs(float(pnl)))

        by_sym[sym]["pnl_pct"] = round(by_sym[sym]["pnl_pct"] + pnl, 4)
        by_sym[sym]["total_pnl_pct"] = by_sym[sym]["pnl_pct"]
        by_sym[sym]["win_rate"] = (
            round(by_sym[sym]["wins"] / by_sym[sym]["trades"] * 100, 1) if by_sym[sym]["trades"] > 0 else 0.0
        )

    for s_data in by_sym.values():
        win_list = s_data.pop("_win_pnls", [])
        loss_list = s_data.pop("_loss_pnls", [])
        avg_w = sum(win_list) / len(win_list) if win_list else 0.0
        avg_l = sum(loss_list) / len(loss_list) if loss_list else 0.0
        payoff = round(avg_w / avg_l, 2) if avg_l > 0 else (round(avg_w, 2) if avg_w > 0 else 1.0)
        s_data["avg_win_pct"] = round(avg_w, 4)
        s_data["avg_loss_pct"] = round(avg_l, 4)
        s_data["payoff_ratio"] = payoff

    return by_sym


def _group_by_symbol_direction(history):
    by_sym_dir = {}
    from monika.core.primitives.constants import MARKET_OUTCOME_EXIT_REASONS

    for t in history:
        sym = t.get("symbol")
        direction = t.get("direction")
        if not sym or not direction:
            continue
        key = f"{sym}_{str(direction).lower()}"
        if key not in by_sym_dir:
            by_sym_dir[key] = {
                "trades": 0,
                "total": 0,
                "wins": 0,
                "losses": 0,
                "pnl_pct": 0.0,
                "total_pnl_pct": 0.0,
                "win_rate": 0.0,
            }

        if t.get("exit_reason") in MARKET_OUTCOME_EXIT_REASONS:
            by_sym_dir[key]["trades"] += 1
            by_sym_dir[key]["total"] += 1
            if t.get("exit_reason") == "tp_hit" or (t.get("pnl_pct") or 0) > 0:
                by_sym_dir[key]["wins"] += 1
            else:
                by_sym_dir[key]["losses"] += 1

        pnl = t.get("pnl_pct", 0) or 0.0
        by_sym_dir[key]["pnl_pct"] = round(by_sym_dir[key]["pnl_pct"] + pnl, 4)
        by_sym_dir[key]["total_pnl_pct"] = by_sym_dir[key]["pnl_pct"]
        by_sym_dir[key]["win_rate"] = (
            round(by_sym_dir[key]["wins"] / by_sym_dir[key]["trades"] * 100, 1)
            if by_sym_dir[key]["trades"] > 0
            else 0.0
        )
    return by_sym_dir
