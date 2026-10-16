"""
Order placement, trade modification, position synchronization, and emergency actions for MT5Client.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import time
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from monika.infrastructure.database.models import Position

from .base import MT5MixinBase
from .constants import PRIORITY_CRITICAL, PRIORITY_STANDARD, logger
from .order_ops import (
    _cancel_order,
    _close_position,
    _get_deal_history,
    _get_open_positions,
    _get_order_history,
    _get_orders,
    _modify_position,
    _place_order,
)
from .primitives import _capture_chart_screenshot


class MT5ExecutionMixin(MT5MixinBase):
    """Mixin providing trade dispatch, position lifecycle, emergency liquidation, and DB sync."""

    async def place_order(
        self,
        symbol: str,
        direction: str,
        volume: float,
        price: Optional[float] = None,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        comment: str = "AIAgent",
        order_type: str = "market",
        max_spread_multiplier: Optional[float] = None,
    ) -> dict[str, Any]:
        """Ajukan order baru (market, limit, atau stop) ke MT5."""
        if not await self.ensure_connected():
            return {"success": False, "error": "MT5 disconnected", "retcode": -1}

        direction = (direction or "").lower().strip()
        if max_spread_multiplier is None:
            exec_cfg = self.settings.get("execution", {})
            mult_map = exec_cfg.get("max_spread_multiplier", {})
            max_spread_multiplier = mult_map.get(symbol, 10.0)  # Default 10x if not found

        # Phase 1: Persistent pre-dispatch marker
        pending_act = None
        if hasattr(self, "pending_action_manager") and self.pending_action_manager:
            try:
                pending_act = self.pending_action_manager.begin_action(
                    symbol=symbol,
                    action=direction,
                    volume=volume,
                    price=price,
                    sl=sl,
                    tp=tp,
                    order_type=order_type,
                    comment=comment,
                )
            except Exception as e:
                logger.error(f"Failed writing Phase 1 pending action marker: {e}")

        try:
            result = await self._run(
                _place_order,
                symbol,
                direction,
                volume,
                price,
                sl,
                tp,
                comment,
                order_type,
                max_spread_multiplier,
                priority=PRIORITY_CRITICAL,
                timeout=3.0,
            )
        except (TimeoutError, asyncio.TimeoutError) as te:
            if pending_act and hasattr(self, "pending_action_manager") and self.pending_action_manager:
                self.pending_action_manager.mark_unconfirmed(pending_act.client_order_id, f"Timeout 3.0s: {te}")
            logger.warning(
                f"MT5 place_order timed out after 3.0s for {symbol}. Performing in-flight order reconciliation..."
            )
            # Reconcile: Periksa apakah posisi sebenarnya sudah terbentuk di MT5 dalam beberapa detik terakhir
            try:
                await asyncio.sleep(0.5)
                open_positions = await self.get_open_positions(symbol)
                now_ts = time.time()
                expected_type = "buy" if direction == "buy" else "sell"
                for op in open_positions:
                    pos_type = str(
                        op.get("direction")
                        or ("buy" if op.get("type") == 0 else "sell" if op.get("type") == 1 else op.get("type", ""))
                    ).lower()
                    raw_time = op.get("time", 0)
                    pos_ts = raw_time.timestamp() if isinstance(raw_time, datetime) else float(raw_time or 0.0)
                    # Cek kesesuaian tipe, volume mendekati, dan timestamp dalam 15 detik terakhir
                    if (
                        pos_type == expected_type
                        and abs(float(op.get("volume", 0.0)) - float(volume)) < 0.001
                        and (now_ts - pos_ts) < 15.0
                    ):
                        logger.critical(
                            f"MT5 in-flight reconciliation SUCCESS: Found open position ticket={op.get('ticket')} for {symbol}"
                        )
                        if pending_act and hasattr(self, "pending_action_manager") and self.pending_action_manager:
                            self.pending_action_manager.commit_action(
                                pending_act.client_order_id, broker_ticket=op.get("ticket")
                            )
                        return {
                            "success": True,
                            "ticket": op.get("ticket"),
                            "price": op.get("price_open") or op.get("open_price"),
                            "sl": op.get("sl"),
                            "tp": op.get("tp"),
                            "retcode": 10009,
                            "recovered_from_timeout": True,
                        }

                # Also inspect active pending orders (limit/stop) if position was not directly filled
                active_orders = await self.get_orders(symbol)
                for ord_item in active_orders:
                    ord_type = str(ord_item.get("direction", "")).lower()
                    raw_time = ord_item.get("time", 0)
                    ord_ts = raw_time.timestamp() if isinstance(raw_time, datetime) else float(raw_time or 0.0)
                    if (
                        ord_type == expected_type
                        and abs(float(ord_item.get("volume", 0.0)) - float(volume)) < 0.001
                        and (now_ts - ord_ts) < 15.0
                    ):
                        logger.critical(
                            f"MT5 in-flight reconciliation SUCCESS: Found active pending order ticket={ord_item.get('ticket')} for {symbol}"
                        )
                        if pending_act and hasattr(self, "pending_action_manager") and self.pending_action_manager:
                            self.pending_action_manager.commit_action(
                                pending_act.client_order_id, broker_ticket=ord_item.get("ticket")
                            )
                        return {
                            "success": True,
                            "ticket": ord_item.get("ticket"),
                            "price": ord_item.get("price_open"),
                            "sl": ord_item.get("sl"),
                            "tp": ord_item.get("tp"),
                            "retcode": 10009,
                            "recovered_from_timeout": True,
                        }
            except Exception as rec_err:
                logger.error(f"In-flight reconciliation error for {symbol}: {rec_err}")
            return {
                "success": False,
                "error": f"MT5 order placement timed out for {symbol} (in-flight not detected)",
                "retcode": -999,
            }
        except Exception as general_err:
            if pending_act and hasattr(self, "pending_action_manager") and self.pending_action_manager:
                self.pending_action_manager.mark_unconfirmed(
                    pending_act.client_order_id, f"Execution exception: {general_err}"
                )
            raise

        if result.get("success"):
            if pending_act and hasattr(self, "pending_action_manager") and self.pending_action_manager:
                self.pending_action_manager.commit_action(
                    pending_act.client_order_id, broker_ticket=result.get("ticket")
                )
            logger.info(
                f"Order placed: {direction.upper()} {volume} {symbol} "
                f"@ {result.get('price')} | ticket={result.get('ticket')}"
            )
        else:
            if pending_act and hasattr(self, "pending_action_manager") and self.pending_action_manager:
                self.pending_action_manager.fail_action(
                    pending_act.client_order_id, error_message=str(result.get("error"))
                )
            logger.error(
                f"Order failed: {direction.upper()} {volume} {symbol} | "
                f"error={result.get('error')} retcode={result.get('retcode')}"
            )
        return result

    async def modify_position(
        self,
        ticket: Any,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
    ) -> dict[str, Any]:
        """Ubah SL/TP dari posisi terbuka yang ada."""
        if not await self.ensure_connected():
            return {"success": False, "error": "MT5 disconnected", "retcode": -1}
        try:
            ticket_id = int(str(ticket).strip())
        except ValueError, TypeError:
            logger.warning(f"Failed to parse ticket: {ticket!r}")
            return {"success": False, "error": f"Invalid ticket: {ticket}", "retcode": -1}
        try:
            result = await self._run(_modify_position, ticket_id, sl, tp, priority=PRIORITY_CRITICAL, timeout=3.0)
        except TimeoutError, asyncio.TimeoutError:
            logger.error(f"Modify position {ticket_id} timed out")
            return {"success": False, "error": f"Modify position {ticket_id} timed out", "retcode": -999}

        if result.get("success"):
            logger.info(f"Position {ticket_id} modified: SL={sl}, TP={tp}")
        else:
            logger.error(f"Modify {ticket_id} failed: {result.get('error')}")
        return result

    async def close_position(
        self,
        ticket: Any,
        volume: Optional[float] = None,
        comment: str = "AIAgent-Close",
        lots: Optional[float] = None,
    ) -> dict[str, Any]:
        """Tutup posisi terbuka (sepenuhnya atau sebagian)."""
        if not await self.ensure_connected():
            return {"success": False, "error": "MT5 disconnected", "retcode": -1}
        try:
            ticket_id = int(str(ticket).strip())
        except ValueError, TypeError:
            logger.warning(f"Failed to parse ticket: {ticket!r}")
            return {"success": False, "error": f"Invalid ticket: {ticket}", "retcode": -1}
        eff_volume = lots if volume is None and lots is not None else volume
        try:
            result = await self._run(
                _close_position, ticket_id, eff_volume, comment, lots=lots, priority=PRIORITY_CRITICAL, timeout=3.0
            )
        except TimeoutError, asyncio.TimeoutError:
            logger.error(f"Close position {ticket_id} timed out")
            return {"success": False, "error": f"Close position {ticket_id} timed out", "retcode": -999}

        if result.get("success"):
            logger.info(f"Position {ticket_id} closed @ {result.get('price')} | profit={result.get('profit')}")
        else:
            logger.error(f"Close {ticket_id} failed: {result.get('error')}")
        return result

    async def get_open_positions(self, symbol: Optional[str] = None) -> list[dict[str, Any]]:
        """Ambil semua posisi terbuka dari MT5."""
        if not await self.ensure_connected():
            return []
        positions = await self._run(_get_open_positions, symbol, priority=PRIORITY_STANDARD)
        return positions or []

    async def get_orders(self, symbol: Optional[str] = None) -> list[dict[str, Any]]:
        """Ambil daftar semua order pending yang aktif di terminal MT5."""
        if not await self.ensure_connected():
            return []
        orders = await self._run(_get_orders, symbol, priority=PRIORITY_STANDARD)
        return orders or []

    async def cancel_order(self, ticket_or_id: Any) -> dict[str, Any]:
        """Batalkan pending order di MT5 berdasarkan ticket."""
        if not await self.ensure_connected():
            return {"success": False, "error": "MT5 disconnected", "retcode": -1}
        try:
            ticket = int(str(ticket_or_id).strip())
        except ValueError, TypeError:
            logger.warning(f"Failed to parse ticket: {ticket_or_id!r}")
            return {"success": False, "error": f"Invalid ticket: {ticket_or_id}", "retcode": -1}
        return await self._run(_cancel_order, ticket, priority=PRIORITY_CRITICAL, timeout=3.0)

    async def cancel_all_pending_orders(self, symbol: Optional[str] = None) -> dict[str, Any]:
        """Batalkan semua pending/resting order di MT5 untuk menenangkan buku order (Cancel-Before-Flatten)."""
        orders = await self.get_orders(symbol)
        canceled = 0
        failed = 0
        errors = []
        for o in orders:
            t = o.get("ticket")
            if t:
                res = await self.cancel_order(t)
                if res.get("success"):
                    canceled += 1
                else:
                    failed += 1
                    errors.append(res.get("error", "Unknown error"))
        logger.info(f"[MT5Client] Cancelled {canceled}/{len(orders)} pending orders (failed={failed})")
        return {"total": len(orders), "canceled": canceled, "failed": failed, "errors": errors}

    async def get_order_history(
        self,
        ticket: Optional[int] = None,
        symbol: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> list[dict[str, Any]]:
        """Ambil riwayat order dari MT5 berdasarkan ticket."""
        if not await self.ensure_connected():
            return []
        if ticket is None:
            return []
        try:
            ticket_id = int(str(ticket).strip())
        except ValueError, TypeError:
            logger.warning(f"Failed to parse ticket: {ticket!r}")
            ticket_id = 0
        if ticket_id == 0:
            return []
        return await self._run(_get_order_history, ticket_id, priority=PRIORITY_STANDARD) or []

    async def get_deal_history(
        self,
        ticket: Optional[int] = None,
        position: Optional[int] = None,
        symbol: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> list[dict[str, Any]]:
        """Ambil riwayat deal dari MT5 berdasarkan ticket posisi atau order."""
        if not await self.ensure_connected():
            return []
        target_ticket = position if position is not None else ticket
        if target_ticket is None:
            return []
        try:
            ticket_id = int(str(target_ticket).strip())
        except ValueError, TypeError:
            logger.warning(f"Failed to parse ticket: {target_ticket!r}")
            ticket_id = 0
        if ticket_id == 0:
            return []
        return await self._run(_get_deal_history, ticket_id, priority=PRIORITY_STANDARD) or []

    async def close_all_positions(
        self,
        symbol: Optional[str] = None,
        comment: str = "AIAgent-CloseAll",
    ) -> dict[str, Any]:
        """Tutup SEMUA posisi terbuka (dipakai oleh kill-switch) - Priority 0."""
        if not await self.ensure_connected():
            return {"closed": 0, "failed": 0, "total": 0, "error": "MT5 disconnected"}
        positions = await self._run(_get_open_positions, symbol, priority=PRIORITY_CRITICAL)
        closed = failed = 0
        for pos in positions or []:
            result = await self.close_position(pos["ticket"], comment=comment)
            if result.get("success"):
                closed += 1
            else:
                failed += 1
                logger.error(f"Failed to close position {pos['ticket']}: {result.get('error')}")
        logger.warning(f"close_all_positions: closed={closed}, failed={failed}, total={len(positions or [])}")
        return {"closed": closed, "failed": failed, "total": len(positions or [])}

    async def emergency_close_all(self, comment: str = "AIAgent-EmergencyCloseAll") -> dict[str, Any]:
        """Emergency liquidate all positions (Priority 0)."""
        return await self.close_all_positions(comment=comment)

    async def kill_switch(self, comment: str = "AIAgent-KillSwitch") -> dict[str, Any]:
        """Emergency kill-switch: liquidate all positions and disconnect (Priority 0)."""
        res = await self.close_all_positions(comment=comment)
        await self.disconnect()
        return res

    async def modify_order(
        self,
        ticket: int,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
    ) -> dict[str, Any]:
        """Alias for modify_position (Priority 0)."""
        return await self.modify_position(ticket=ticket, sl=sl, tp=tp)

    async def capture_chart_screenshot(
        self,
        symbol: str,
        timeframe: str = "H1",
        width: int = 1280,
        height: int = 720,
        filepath: Optional[str] = None,
    ) -> dict[str, Any]:
        """Takes an on-demand screenshot of the active MT5 chart window via mt5.chart_screenshot()."""
        if not await self.ensure_connected():
            return {"success": False, "error": "MT5 disconnected"}

        from pathlib import Path

        if not filepath:
            out_dir = Path("results/charts/mt5_screenshots")
            out_dir.mkdir(parents=True, exist_ok=True)
            ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = str(out_dir / f"{symbol}_{timeframe}_{ts_str}.png")

        tf_val = self._timeframe_to_mt5(timeframe)
        res = await self._run(_capture_chart_screenshot, symbol, tf_val, width, height, filepath)
        return res

    def get_chart_objects(self, symbol: str) -> dict[str, Any]:
        """Reads exported user chart objects from shared MT5 FILE_COMMON (Q151)."""
        import json
        from pathlib import Path

        from monika.infrastructure.brokers.ea_bridge.heartbeat_writer import HeartbeatManager

        common_path = HeartbeatManager().get_common_path()
        if not common_path:
            return {
                "symbol": symbol,
                "objects": [],
                "status": "unavailable",
                "message": "MT5 common directory not found",
            }

        obj_file = Path(common_path) / f"chart_objects_{symbol}.json"
        if not obj_file.exists():
            return {
                "symbol": symbol,
                "objects": [],
                "status": "not_found",
                "message": f"No chart_objects_{symbol}.json found in MT5 common folder. Ensure AIAgent_EA is attached to the chart.",
            }

        try:
            with open(obj_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {"status": "success", **data}
        except Exception as e:
            return {"symbol": symbol, "objects": [], "status": "error", "error": str(e)}

    async def sync_positions_from_mt5(
        self,
        session: AsyncSession,
    ) -> dict[str, Any]:
        """Sinkronkan posisi terbuka dari MT5 ke DB lokal (perbarui status DB yang sudah tertutup di MT5)."""
        mt5_positions = await self.get_open_positions()
        mt5_orders = await self.get_orders()
        mt5_tickets = {p["ticket"] for p in mt5_positions}
        pending_tickets = {o["ticket"] for o in mt5_orders}
        active_tickets = mt5_tickets.union(pending_tickets)

        synced = closed_in_db = 0
        closed_positions = []

        # Insert any new MT5 positions not yet in DB
        for pos in mt5_positions:
            existing = (
                await session.execute(select(Position).where(Position.mt5_ticket == pos["ticket"]))
            ).scalar_one_or_none()
            if existing is None:
                direction = "buy" if pos["type"] == 0 else "sell"
                session.add(
                    Position(
                        mt5_ticket=pos["ticket"],
                        symbol=pos["symbol"],
                        direction=direction,
                        volume=pos["volume"],
                        entry_price=pos["price_open"],
                        sl=pos.get("sl"),
                        tp=pos.get("tp"),
                        opened_at=pos["time"],
                        status="open",
                    )
                )
                synced += 1
            else:
                # Update volume/lots and status upon partial close
                mt5_vol = float(pos.get("volume", 0.0))
                if mt5_vol != existing.lots:
                    logger.info(f"Position {existing.mt5_ticket} volume changed: {existing.lots} -> {mt5_vol}")
                    existing.lots = mt5_vol
                    if mt5_vol == 0:
                        existing.status = "closed"
                        existing.closed_at = datetime.now(timezone.utc)

        # Mark DB-open positions that are no longer on MT5 as closed
        db_open = (await session.execute(select(Position).where(Position.status == "open"))).scalars().all()
        for db_pos in db_open:
            # Skip paper/dry-run positions — they don't exist in MT5
            if getattr(db_pos, "is_paper", False):
                continue
            if db_pos.mt5_ticket and db_pos.mt5_ticket not in active_tickets:
                db_pos.status = "closed"
                db_pos.closed_at = datetime.now(timezone.utc)

                # Fetch deal history to get PnL and close reason
                deals = await self._run(_get_deal_history, db_pos.mt5_ticket)
                if deals:
                    close_deal = deals[-1]
                    db_pos.pnl = sum(getattr(d, "profit", 0.0) for d in deals)
                    setattr(db_pos, "_mt5_close_reason", getattr(close_deal, "reason", None))
                    setattr(db_pos, "_mt5_exit_price", getattr(close_deal, "price", None))
                # Sync matching PaperTradeRecord to track demo performance statistics
                if db_pos.analysis_id:
                    try:
                        from monika.infrastructure.database.models import PaperTradeRecord

                        pt_record = (
                            await session.execute(
                                select(PaperTradeRecord).where(
                                    PaperTradeRecord.analysis_id == db_pos.analysis_id,
                                    PaperTradeRecord.status == "open",
                                )
                            )
                        ).scalar_one_or_none()
                        if pt_record:
                            pt_record.status = "closed"
                            pt_record.closed_at = db_pos.closed_at
                            exit_px = getattr(db_pos, "_mt5_exit_price", None)
                            if exit_px is not None:
                                pt_record.exit_price = float(exit_px)
                            reason_code = getattr(db_pos, "_mt5_close_reason", None)
                            reason_str = (
                                "tp_hit" if reason_code == 4 else ("sl_hit" if reason_code == 3 else "broker_close")
                            )
                            pt_record.exit_reason = reason_str
                            if pt_record.exit_price and pt_record.entry_price and pt_record.entry_price > 0:
                                if pt_record.direction == "buy":
                                    pnl_ratio = (pt_record.exit_price - pt_record.entry_price) / pt_record.entry_price
                                else:
                                    pnl_ratio = (pt_record.entry_price - pt_record.exit_price) / pt_record.entry_price
                                pt_record.pnl_pct = round(pnl_ratio * 100.0, 4)
                            op_at = pt_record.opened_at
                            cl_at = pt_record.closed_at
                            if op_at is not None and cl_at is not None:
                                pt_record.holding_hours = round((cl_at - op_at).total_seconds() / 3600.0, 2)
                    except Exception as pt_err:
                        logger.debug(f"Syncing PaperTradeRecord for position {db_pos.id} non-fatal: {pt_err}")

                closed_positions.append(db_pos)
                closed_in_db += 1

        await session.commit()
        logger.info(f"Position sync: {synced} new, {closed_in_db} closed")
        return {"synced": synced, "closed_in_db": closed_in_db, "closed_positions": closed_positions}
