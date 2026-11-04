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
from monika.core.analytics import paper_suspension
from monika.core.analytics.paper_analytics import (
    _group_by_symbol,
    _group_by_symbol_direction,
    aggregate_trade_statistics,
    calculate_equity_curve,
)

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
                import yaml
                from monika.core.paths import CONFIG_DIR

                cfg_file = CONFIG_DIR / "settings.yaml"
                if cfg_file.exists():
                    with open(cfg_file, encoding="utf-8") as f:
                        self.settings = yaml.safe_load(f) or {}
                else:
                    self.settings = {}
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
            MAX_TRADE_AGE_HOURS = float(self.settings.get("paper_trading", {}).get("max_paper_trade_holding_hours", 24))

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
                    # The realised result of this paper trade is the evidence; the
                    # synthetic 1.5/1.0 fallback would misstate the profit factor.
                    profit=(float(trade.pnl_pct) if trade.pnl_pct is not None else None),
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
        return await paper_suspension.get_suspended_symbols(session)

    async def check_and_suspend_poor_performers(self, session: AsyncSession, settings: dict) -> list[str]:
        """Auto-suspend symbols with consecutive losses."""
        return await paper_suspension.check_and_suspend_poor_performers(session, settings)

    async def suspend_symbol(
        self, session: AsyncSession, symbol: str, duration_hours: float = 24.0, reason: str = "manual_command"
    ) -> dict:
        """Suspend trading untuk simbol tertentu secara manual dengan durasi waktu."""
        return await paper_suspension.suspend_symbol(session, symbol, duration_hours, reason)

    async def unsuspend_symbol(self, session: AsyncSession, symbol: str) -> bool:
        """Unsuspend trading for a symbol"""
        return await paper_suspension.unsuspend_symbol(session, symbol)

    async def unsuspend_all(self, session: AsyncSession) -> list[str]:
        """Unsuspend all symbols"""
        return await paper_suspension.unsuspend_all(session)

    async def get_streak_status(self, session: AsyncSession, symbol: str, settings: Optional[dict] = None) -> dict:
        """Mengambil status streak loss dan suspensi untuk simbol tertentu."""
        eff_settings = settings if settings is not None else getattr(self, "settings", None)
        return await paper_suspension.get_streak_status(session, symbol, eff_settings)

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
            .where(PaperTradeRecord.accounting_status == "ok")
        )
        if days_back is not None:
            since = clock.now() - timedelta(days=days_back)
            query = query.where(PaperTradeRecord.closed_at >= since)
        if symbol is not None:
            query = query.where(PaperTradeRecord.symbol == symbol)

        results = (await session.execute(query)).all()
        return aggregate_trade_statistics(results)

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
        min_rr = risk_cfg.get("min_rr_ratio", 1.5)

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
        """Deteksi losing streak mendadak."""
        return await paper_suspension.check_recent_streak(session, lookback)

    async def simulate_equity_curve(self, session: AsyncSession, starting_equity: float = 10000.0) -> dict:
        """Simulasikan kurva ekuitas (equity curve) untuk hitung max drawdown & growth."""
        from sqlalchemy import select

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
        return calculate_equity_curve(records, starting_equity)


__all__ = [
    "PaperTracker",
    "_group_by_symbol",
    "_group_by_symbol_direction",
    "aggregate_trade_statistics",
    "calculate_equity_curve",
]
