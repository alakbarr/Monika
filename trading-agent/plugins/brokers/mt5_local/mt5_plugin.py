# ==============================================================================
# File: plugins/brokers/mt5_local/mt5_plugin.py
# ==============================================================================

"""
MetaTrader 5 Windows Local Broker Plugin.
Standardized BrokerPlugin wrapper for local MT5 terminal IPC connection.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from execution.broker_plugin import (
    BrokerPlugin,
    TickData,
    InstrumentSpec,
    PositionData,
    DealData,
    AccountInfo,
    ExitReason,
)
from harness.contract import PluginMetadata, PluginCategory, PluginOrigin
from execution.mt5_client import MT5Client

logger = logging.getLogger("TradingAgent.Plugins.MT5Local")


class MT5LocalBrokerPlugin(BrokerPlugin):
    metadata = PluginMetadata(
        id="mt5_local",
        name="MetaTrader 5 Windows Local Broker",
        version="1.0.0",
        category=PluginCategory.BROKER,
        description="Live execution broker connecting to local MT5 Windows terminal via IPC",
        author="Monika Core Team",
        origin=PluginOrigin.BUILTIN,
        is_core=True,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mt5_client: Optional[MT5Client] = None
        self._dry_run: bool = False

    async def on_register(self, container, event_bus) -> None:
        self.mt5_client = MT5Client(settings=self.config)
        container.register("broker", self)
        container.register("mt5_client", self.mt5_client)
        logger.info("[MT5LocalBrokerPlugin] Registered in DI container")

    async def connect(self) -> bool:
        if self.mt5_client:
            return await self.mt5_client.connect()
        return False

    async def disconnect(self) -> None:
        if self.mt5_client:
            await self.mt5_client.disconnect()

    async def is_connected(self) -> bool:
        if self.mt5_client:
            return await self.mt5_client.is_connected()
        return False

    async def ensure_connected(self) -> bool:
        if self.mt5_client and hasattr(self.mt5_client, "ensure_connected"):
            return await self.mt5_client.ensure_connected()
        return await self.is_connected()

    async def get_tick(self, symbol: str) -> Optional[TickData]:
        if not self.mt5_client:
            return None
        try:
            cur = await self.mt5_client.get_current_price(symbol)
            if cur:
                bid = float(cur.get("bid", 0.0))
                ask = float(cur.get("ask", 0.0))
                return TickData(
                    symbol=symbol.upper(),
                    bid=bid,
                    ask=ask,
                    last=float(cur.get("last", ask)),
                    spread=round(ask - bid, 5),
                    time=cur.get("time", datetime.now(timezone.utc)),
                )
        except Exception as e:
            logger.debug(f"[MT5LocalBrokerPlugin] get_tick error: {e}")
        return None

    async def get_symbol_spec(self, symbol: str) -> InstrumentSpec:
        sym = symbol.upper()
        if self.mt5_client:
            try:
                info = await self.mt5_client.get_symbol_info(sym)
                if info:
                    return InstrumentSpec(
                        symbol=sym,
                        contract_size=float(info.get("trade_contract_size", 100000.0)),
                        pip_size=float(info.get("point", 0.0001)),
                        min_lot=float(info.get("volume_min", 0.01)),
                        max_lot=float(info.get("volume_max", 50.0)),
                        lot_step=float(info.get("volume_step", 0.01)),
                        stops_level_pips=float(info.get("trade_stops_level", 0.0)),
                    )
            except Exception as e:
                logger.debug(f"[MT5LocalBrokerPlugin] get_symbol_spec error: {e}")
        return InstrumentSpec(symbol=sym)

    async def get_open_positions(self, symbol: Optional[str] = None) -> List[PositionData]:
        if not self.mt5_client:
            return []
        try:
            raw_pos = await self.mt5_client.get_open_positions(symbol)
            result = []
            for p in raw_pos:
                result.append(
                    PositionData(
                        ticket=int(p.get("ticket", 0)),
                        symbol=str(p.get("symbol", "")).upper(),
                        direction="buy" if p.get("type", 0) == 0 else "sell",
                        volume=float(p.get("volume", 0.0)),
                        open_price=float(p.get("open_price", p.get("price_open", 0.0))),
                        sl=float(p["sl"]) if p.get("sl") else None,
                        tp=float(p["tp"]) if p.get("tp") else None,
                        pnl=float(p.get("profit", 0.0)),
                        magic=int(p.get("magic", 0)),
                        comment=str(p.get("comment", "")),
                        is_paper=False,
                    )
                )
            return result
        except Exception as e:
            logger.error(f"[MT5LocalBrokerPlugin] get_open_positions error: {e}")
            return []

    async def get_account_info(self) -> AccountInfo:
        if self.mt5_client:
            try:
                acc = await self.mt5_client.get_account_info()
                if acc:
                    return AccountInfo(
                        balance=float(acc.get("balance", 0.0)),
                        equity=float(acc.get("equity", 0.0)),
                        margin=float(acc.get("margin", 0.0)),
                        free_margin=float(acc.get("margin_free", acc.get("free_margin", 0.0))),
                        leverage=float(acc.get("leverage", 100.0)),
                        currency=str(acc.get("currency", "USD")),
                    )
            except Exception as e:
                logger.error(f"[MT5LocalBrokerPlugin] get_account_info error: {e}")
        return AccountInfo(balance=0.0, equity=0.0, margin=0.0, free_margin=0.0, leverage=100.0)

    async def submit_order(self, order: Any, **kwargs) -> Dict[str, Any]:
        if not self.mt5_client:
            return {"success": False, "error": "MT5 client not initialized"}
        return await self.mt5_client.place_order(order, **kwargs)

    async def cancel_order(self, client_order_id: str, ticket: Optional[int] = None) -> bool:
        if not self.mt5_client:
            return False
        if ticket is not None:
            res = await self.mt5_client.cancel_order(ticket)
            return bool(res.get("success", False)) if isinstance(res, dict) else bool(res)
        return False

    async def modify_position(self, ticket: int, sl: Optional[float] = None, tp: Optional[float] = None) -> bool:
        if not self.mt5_client:
            return False
        res = await self.mt5_client.modify_position(ticket=ticket, sl=sl, tp=tp)
        return bool(res.get("success", False)) if isinstance(res, dict) else bool(res)

    async def close_position(self, ticket: int, lots: Optional[float] = None) -> Dict[str, Any]:
        if not self.mt5_client:
            return {"success": False, "error": "MT5 client not initialized"}
        return await self.mt5_client.close_position(ticket=ticket, volume=lots)

    async def close_all_positions(self, comment: str = "KillSwitch") -> Dict[str, Any]:
        if not self.mt5_client:
            return {"success": False, "error": "MT5 client not initialized"}
        return await self.mt5_client.close_all_positions(comment=comment)
