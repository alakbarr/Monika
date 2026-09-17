# ==============================================================================
# File: execution/order_emulator.py
# ==============================================================================

"""
Event-Driven Client Order Emulator (ClientOrderEmulator).

Menggantikan evaluasi Breakeven dan Trailing Stop dari polling terjadwal 10 menit
menjadi emulator lokal berbasis event tick (TickPriceEvent) latensi rendah.

Spesifikasi:
1. Berlangganan ke EventBus pada event TickPriceEvent dengan priority=1 (eksekusi cepat).
2. Menyimpan watermark per posisi (high_watermark, low_watermark, status BE, status Trailing).
3. Evaluasi langsung kondisi Breakeven (BE) saat profit >= 1.0 * ATR.
4. Evaluasi langsung kondisi Trailing Stop saat profit >= 2.0 * ATR.
5. Menghubungi ExecutionService untuk update SL real-time tanpa database polling thrashing.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Callable, Awaitable, Sequence

from utils.protocol.event_bus import EventBus, TickPriceEvent

logger = logging.getLogger("TradingAgent.Execution.OrderEmulator")


@dataclass
class TrackedPosition:
    """Representasi in-memory posisi aktif yang diawasi oleh emulator."""
    ticket: int
    symbol: str
    direction: str                     # 'buy' or 'sell'
    entry_price: float
    current_sl: float
    current_tp: Optional[float] = None
    atr: float = 0.0
    high_watermark: float = 0.0
    low_watermark: float = 0.0
    breakeven_activated: bool = False
    trailing_activated: bool = False
    is_modifying: bool = False
    last_sl_update: float = 0.0
    analysis_id: Optional[int] = None
    pair_group_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class ClientOrderEmulator:
    """
    Sub-second event-driven client-side order emulator for Trailing Stop & Breakeven.
    """

    def __init__(
        self,
        execution_service: Optional[Any] = None,
        event_bus: Optional[EventBus] = None,
        settings: Optional[Dict[str, Any]] = None,
        on_sl_adjustment: Optional[Callable[[int, float, str, Optional[int]], Awaitable[dict]]] = None,
    ):
        self.execution_service = execution_service
        self.event_bus = event_bus
        self.settings = settings or {}
        self.on_sl_adjustment = on_sl_adjustment

        trail_cfg = self.settings.get("trading", {}).get("trailing_stop") or self.settings.get("trailing_stop", {})
        self.enabled = trail_cfg.get("enabled", True)
        self.breakeven_atr_multiple = float(trail_cfg.get("breakeven_atr_multiple", 1.0))
        self.trail_atr_multiple = float(trail_cfg.get("trail_atr_multiple", 1.5))
        self.spread_buffer_atr = float(trail_cfg.get("spread_buffer_atr", 0.1))
        self.min_trail_step_atr = float(trail_cfg.get("min_trail_step_atr", 0.1))

        self._positions: Dict[int, TrackedPosition] = {}
        self._lock = asyncio.Lock()
        self._subscribed = False

        if self.event_bus is not None:
            self.subscribe(self.event_bus)

    def subscribe(self, event_bus: EventBus) -> None:
        """Berlangganan ke TickPriceEvent dengan priority 1."""
        if not self._subscribed:
            event_bus.subscribe(TickPriceEvent, self.on_tick, priority=1)
            self._subscribed = True
            logger.info("[ClientOrderEmulator] Subscribed to TickPriceEvent (priority=1)")

    def unsubscribe(self, event_bus: EventBus) -> None:
        """Berhenti berlangganan dari TickPriceEvent."""
        if self._subscribed:
            event_bus.unsubscribe(TickPriceEvent, self.on_tick)
            self._subscribed = False
            logger.info("[ClientOrderEmulator] Unsubscribed from TickPriceEvent")

    async def register_position(
        self,
        ticket: int,
        symbol: str,
        direction: str,
        entry_price: float,
        current_sl: float,
        atr: float,
        current_tp: Optional[float] = None,
        analysis_id: Optional[int] = None,
        pair_group_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TrackedPosition:
        """Daftarkan posisi aktif ke emulator in-memory."""
        sym_clean = symbol.strip().upper().replace("/", "")
        dir_clean = direction.strip().lower()

        async with self._lock:
            existing = self._positions.get(ticket)
            h_wm = max(entry_price, existing.high_watermark if existing else entry_price)
            l_wm = min(entry_price, existing.low_watermark if existing else entry_price)
            be_active = existing.breakeven_activated if existing else False
            trail_active = existing.trailing_activated if existing else False

            # Check if BE already reached based on current SL vs entry
            if dir_clean == "buy" and current_sl > entry_price:
                be_active = True
            elif dir_clean == "sell" and 0.0 < current_sl < entry_price:
                be_active = True

            eff_atr = atr if atr > 0 else (existing.atr if existing and existing.atr > 0 else 0.0)
            pos = TrackedPosition(
                ticket=ticket,
                symbol=sym_clean,
                direction=dir_clean,
                entry_price=entry_price,
                current_sl=current_sl,
                current_tp=current_tp,
                atr=eff_atr,
                high_watermark=h_wm,
                low_watermark=l_wm,
                breakeven_activated=be_active,
                trailing_activated=trail_active,
                analysis_id=analysis_id,
                pair_group_id=pair_group_id,
                metadata=metadata or {},
            )
            self._positions[ticket] = pos
            logger.info(
                f"[ClientOrderEmulator] Registered position #{ticket} ({sym_clean} {dir_clean.upper()} "
                f"@ {entry_price}, SL={current_sl}, ATR={eff_atr:.5f})"
            )
            return pos

    async def unregister_position(self, ticket: int) -> Optional[TrackedPosition]:
        """Hapus posisi dari pemantauan (posisi ditutup/likuidasi)."""
        async with self._lock:
            pos = self._positions.pop(ticket, None)
            if pos:
                logger.info(f"[ClientOrderEmulator] Unregistered position #{ticket} ({pos.symbol})")
            return pos

    def get_tracked_position(self, ticket: int) -> Optional[TrackedPosition]:
        """Ambil posisi yang dilacak."""
        return self._positions.get(ticket)

    def get_all_tracked(self) -> Dict[int, TrackedPosition]:
        """Ambil seluruh posisi yang dilacak."""
        return dict(self._positions)

    async def sync_positions(
        self,
        active_positions: Sequence[Any],
        atr_lookup: Optional[Dict[str, float]] = None,
    ) -> None:
        """
        Sinkronkan daftar posisi dari DB/MT5 dengan posisi in-memory.
        Menghapus posisi yang sudah tutup dan memperbarui parameter posisi aktif.
        """
        atr_map = atr_lookup or {}
        active_tickets = set()

        for p in active_positions:
            t = getattr(p, "mt5_ticket", None) or getattr(p, "ticket", None)
            if t is None:
                continue
            active_tickets.add(int(t))
            sym = getattr(p, "symbol", "")
            direction = getattr(p, "direction", "buy")
            entry = float(getattr(p, "entry_price", 0.0) or 0.0)
            sl = float(getattr(p, "sl", 0.0) or 0.0)
            tp = float(getattr(p, "tp", 0.0) or 0.0) if getattr(p, "tp", None) else None
            analysis_id = getattr(p, "analysis_id", None)
            pair_group_id = getattr(p, "pair_group_id", None)
            atr = atr_map.get(sym.strip().upper().replace("/", ""), 0.0)

            curr = self.get_tracked_position(int(t))
            pos_atr = atr if atr > 0 else (curr.atr if curr else 0.0)

            await self.register_position(
                ticket=int(t),
                symbol=sym,
                direction=direction,
                entry_price=entry,
                current_sl=sl,
                atr=pos_atr,
                current_tp=tp,
                analysis_id=analysis_id,
                pair_group_id=pair_group_id,
            )

        # Unregister orphaned tickets
        async with self._lock:
            existing_tickets = list(self._positions.keys())
            for et in existing_tickets:
                if et not in active_tickets:
                    self._positions.pop(et, None)
                    logger.info(f"[ClientOrderEmulator] Pruned closed position #{et}")

    async def on_tick(self, event: Any) -> List[Dict[str, Any]]:
        """
        Handler event tick berkecepatan tinggi.
        Mengevaluasi kondisi trailing/breakeven dalam memori murni.
        """
        if not self.enabled:
            return []

        symbol = getattr(event, "symbol", "")
        if not symbol:
            return []

        sym_clean = symbol.strip().upper().replace("/", "")
        bid = float(getattr(event, "bid", 0.0) or 0.0)
        ask = float(getattr(event, "ask", 0.0) or 0.0)
        last_price = float(getattr(event, "last", 0.0) or 0.0)

        # Matching positions for this symbol
        async with self._lock:
            matching = [p for p in self._positions.values() if p.symbol == sym_clean]

        if not matching:
            return []

        adjustments = []
        for pos in matching:
            adj = await self._evaluate_tick_for_position(pos, bid=bid, ask=ask, last=last_price)
            if adj:
                adjustments.append(adj)

        return adjustments

    async def _evaluate_tick_for_position(
        self,
        pos: TrackedPosition,
        bid: float,
        ask: float,
        last: float,
    ) -> Optional[Dict[str, Any]]:
        """Evaluasi mutasi harga tick terhadap watermark, BE, dan trailing stop."""
        if getattr(pos, "is_modifying", False):
            return None

        current_price = bid if pos.direction == "buy" else (ask if ask > 0 else bid)
        if current_price <= 0:
            current_price = last
        if current_price <= 0:
            return None

        # Update high/low watermark
        pos.high_watermark = max(pos.high_watermark, current_price)
        pos.low_watermark = min(pos.low_watermark, current_price)

        atr = pos.atr
        if atr <= 0:
            return None

        entry = pos.entry_price
        current_sl = pos.current_sl
        new_sl: Optional[float] = None
        reason = ""
        min_step = self.min_trail_step_atr * atr

        if pos.direction == "buy":
            profit_distance = current_price - entry

            # 1. Breakeven condition
            if profit_distance >= (self.breakeven_atr_multiple * atr):
                be_sl = entry + (self.spread_buffer_atr * atr)
                if be_sl > current_sl:
                    new_sl = be_sl
                    reason = f"be_triggered (profit={profit_distance:.5f} >= {self.breakeven_atr_multiple}x ATR {atr:.5f})"

            # 2. Trailing stop condition
            if profit_distance >= (2.0 * self.breakeven_atr_multiple * atr):
                trail_sl = pos.high_watermark - (self.trail_atr_multiple * atr)
                if (trail_sl - current_sl) >= min_step and (new_sl is None or trail_sl > new_sl):
                    new_sl = trail_sl
                    reason = f"trailing_stop (profit={profit_distance:.5f}, trail={trail_sl:.5f})"

        elif pos.direction == "sell":
            profit_distance = entry - current_price

            # 1. Breakeven condition
            if profit_distance >= (self.breakeven_atr_multiple * atr):
                be_sl = entry - (self.spread_buffer_atr * atr)
                if be_sl < current_sl:
                    new_sl = be_sl
                    reason = f"be_triggered (profit={profit_distance:.5f} >= {self.breakeven_atr_multiple}x ATR {atr:.5f})"

            # 2. Trailing stop condition
            if profit_distance >= (2.0 * self.breakeven_atr_multiple * atr):
                trail_sl = pos.low_watermark + (self.trail_atr_multiple * atr)
                if (current_sl - trail_sl) >= min_step and (new_sl is None or trail_sl < new_sl):
                    new_sl = trail_sl
                    reason = f"trailing_stop (profit={profit_distance:.5f}, trail={trail_sl:.5f})"

        if new_sl is not None:
            # Round new_sl to reasonable precision
            new_sl = round(new_sl, 5)
            old_sl = pos.current_sl

            logger.info(
                f"[ClientOrderEmulator] Adjusting #{pos.ticket} ({pos.symbol} {pos.direction.upper()}) "
                f"SL {old_sl:.5f} -> {new_sl:.5f} ({reason})"
            )

            pos.is_modifying = True
            try:
                # Dispatch modification first before committing state
                success = await self._dispatch_sl_modification(pos.ticket, new_sl, reason, pos.analysis_id)
                if success:
                    pos.current_sl = new_sl
                    pos.last_sl_update = datetime.now(timezone.utc).timestamp()
                    if "be_triggered" in reason:
                        pos.breakeven_activated = True
                    if "trailing_stop" in reason:
                        pos.trailing_activated = True
                        pos.breakeven_activated = True
                else:
                    logger.warning(
                        f"[ClientOrderEmulator] Modification dispatch failed for #{pos.ticket}. "
                        f"Retaining previous SL {old_sl:.5f}."
                    )
            finally:
                pos.is_modifying = False

            return {
                "ticket": pos.ticket,
                "symbol": pos.symbol,
                "direction": pos.direction,
                "old_sl": old_sl,
                "new_sl": new_sl,
                "reason": reason,
                "success": success,
            }

        return None

    async def _dispatch_sl_modification(
        self,
        ticket: int,
        new_sl: float,
        reason: str,
        analysis_id: Optional[int],
    ) -> bool:
        """Mengirim permintaan perubahan SL ke callback atau ExecutionService."""
        if self.on_sl_adjustment:
            try:
                res = await self.on_sl_adjustment(ticket, new_sl, reason, analysis_id)
                return bool(res.get("success", False)) if isinstance(res, dict) else bool(res)
            except Exception as e:
                logger.error(f"[ClientOrderEmulator] Callback adjustment failed for #{ticket}: {e}")
                return False

        if self.execution_service and hasattr(self.execution_service, "modify_position_sl_tp"):
            try:
                res = await self.execution_service.modify_position_sl_tp(
                    ticket=ticket,
                    sl=new_sl,
                    tp=None,
                    requested_by="client_order_emulator",
                )
                return bool(res.get("success", False))
            except Exception as e:
                logger.error(f"[ClientOrderEmulator] ExecutionService adjustment failed for #{ticket}: {e}")
                return False

        return True
