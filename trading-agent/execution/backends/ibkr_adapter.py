# ==============================================================================
# File: execution/backends/ibkr_adapter.py
# ==============================================================================

"""
Interactive Brokers (IBKR) Execution Adapter (Async).
Integrates Monika with Interactive Brokers Trader Workstation (TWS) or IB Gateway
using `ib_insync`. Provides full parity with `BrokerAdapter`.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import utils.clock as clock
from execution.broker_adapter import BrokerAdapter, _get_contract_size, _get_pip_size
from execution.broker_plugin import OrderRequest, normalize_order_request

logger = logging.getLogger("TradingAgent.IBKRAdapter")

try:
    import ib_insync
    HAS_IB_INSYNC = True
except ImportError:
    ib_insync = None
    HAS_IB_INSYNC = False


class IBKRBrokerAdapter(BrokerAdapter):
    """
    Interactive Brokers execution adapter wrapping TWS / IB Gateway via ib_insync.
    Supports Forex pairs (EUR.USD), Indices, and Commodities/CFDs.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 7497,  # 7497: TWS paper, 7496: TWS live, 4002: Gateway paper, 4001: Gateway live
        client_id: int = 1,
        account: str = "",
        timeout_seconds: float = 15.0,
        **kwargs,
    ):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.account = account
        self.timeout_seconds = timeout_seconds
        self.ib: Optional[Any] = None
        self._connected = False
        self._contract_cache: Dict[str, Any] = {}

    def _ensure_ib(self):
        if not HAS_IB_INSYNC:
            raise RuntimeError(
                "ib_insync package is not installed. Please install it with 'pip install ib_insync'."
            )
        if self.ib is None:
            self.ib = ib_insync.IB()

    async def connect(self) -> bool:
        """Connect to TWS or IB Gateway."""
        if not HAS_IB_INSYNC:
            logger.warning("[IBKR] ib_insync library not available; running in stub/disconnected mode.")
            return False

        try:
            self._ensure_ib()
            if self.ib.isConnected():
                self._connected = True
                return True

            logger.info(f"[IBKR] Connecting to {self.host}:{self.port} (clientId={self.client_id})...")
            await self.ib.connectAsync(
                host=self.host,
                port=self.port,
                clientId=self.client_id,
                timeout=self.timeout_seconds,
            )
            self._connected = self.ib.isConnected()
            logger.info(f"[IBKR] Connected successfully to account {self.ib.managedAccounts()}")
            return self._connected
        except Exception as e:
            logger.error(f"[IBKR] Connection failed: {e}")
            self._connected = False
            return False

    async def disconnect(self) -> None:
        """Disconnect from TWS/IB Gateway."""
        if self.ib and self.ib.isConnected():
            self.ib.disconnect()
        self._connected = False
        logger.info("[IBKR] Disconnected.")

    def _resolve_contract(self, symbol: str) -> Any:
        """Map standard symbol (EURUSD, XAUUSD) to IB Contract object."""
        sym = symbol.upper().replace("/", "").replace(".", "")
        if sym in self._contract_cache:
            return self._contract_cache[sym]

        if not HAS_IB_INSYNC:
            return None

        # FX pairs (EURUSD, GBPUSD, etc.)
        if len(sym) == 6 and not sym.startswith("XAU") and not sym.startswith("BTC"):
            base = sym[:3]
            quote = sym[3:]
            contract = ib_insync.Forex(f"{base}{quote}")
        elif "XAU" in sym or "GOLD" in sym:
            contract = ib_insync.CFD("XAUUSD", "SMART", "USD")
        elif "BTC" in sym:
            contract = ib_insync.Crypto("BTC", "PAXOS", "USD")
        else:
            contract = ib_insync.Stock(sym, "SMART", "USD")

        self._contract_cache[sym] = contract
        return contract

    async def get_tick(self, symbol: str) -> dict:
        """Fetch latest tick quote."""
        now_iso = clock.now().isoformat()
        if not self._connected or not HAS_IB_INSYNC:
            return {
                "symbol": symbol,
                "bid": 0.0,
                "ask": 0.0,
                "last": 0.0,
                "spread": 0.0,
                "time": now_iso,
                "status": "ibkr_disconnected",
            }

        try:
            contract = self._resolve_contract(symbol)
            await self.ib.qualifyContractsAsync(contract)
            ticker = self.ib.reqMktData(contract, "", False, False)
            await asyncio.sleep(0.5)

            bid = ticker.bid if ticker.bid and ticker.bid > 0 else (ticker.last or 0.0)
            ask = ticker.ask if ticker.ask and ticker.ask > 0 else (ticker.last or 0.0)
            last = ticker.last if ticker.last and ticker.last > 0 else ((bid + ask) / 2.0)
            spread = max(0.0, round(ask - bid, 5))

            return {
                "symbol": symbol,
                "bid": bid,
                "ask": ask,
                "last": last,
                "spread": spread,
                "time": ticker.time.isoformat() if ticker.time else now_iso,
                "status": "success",
            }
        except Exception as e:
            logger.error(f"[IBKR] Error fetching tick for {symbol}: {e}")
            return {
                "symbol": symbol,
                "bid": 0.0,
                "ask": 0.0,
                "last": 0.0,
                "spread": 0.0,
                "time": now_iso,
                "error": str(e),
            }

    async def submit_order(self, order: Any, **kwargs) -> dict:
        """Submit order to IBKR."""
        req: OrderRequest = normalize_order_request(order)

        if not self._connected or not HAS_IB_INSYNC:
            logger.warning("[IBKR] Cannot submit order: IBKR adapter disconnected or ib_insync missing.")
            return {
                "success": False,
                "ticket": None,
                "price": None,
                "executed_volume": 0.0,
                "slippage_pips": 0.0,
                "error": "IBKR TWS/Gateway disconnected",
            }

        try:
            contract = self._resolve_contract(req.symbol)
            await self.ib.qualifyContractsAsync(contract)

            action = req.direction.upper()  # BUY or SELL
            # Convert MT5 standard lot to shares/units
            units = req.volume * _get_contract_size(req.symbol)

            order_type = req.order_type.upper()
            if order_type in ("MARKET", "BUY", "SELL"):
                ib_order = ib_insync.MarketOrder(action, units)
            elif order_type in ("LIMIT", "BUY_LIMIT", "SELL_LIMIT") and req.price:
                ib_order = ib_insync.LimitOrder(action, units, req.price)
            elif order_type in ("STOP", "BUY_STOP", "SELL_STOP") and req.price:
                ib_order = ib_insync.StopOrder(action, units, req.price)
            else:
                ib_order = ib_insync.MarketOrder(action, units)

            trade = self.ib.placeOrder(contract, ib_order)
            # Await order placement response
            await asyncio.sleep(0.5)

            ticket = trade.order.orderId
            fill_price = trade.orderStatus.avgFillPrice if trade.orderStatus else (req.price or 0.0)

            return {
                "success": True,
                "ticket": ticket,
                "price": fill_price,
                "executed_volume": req.volume,
                "slippage_pips": 0.0,
                "status": trade.orderStatus.status if trade.orderStatus else "Submitted",
                "error": None,
            }
        except Exception as e:
            logger.error(f"[IBKR] Order submission failed: {e}")
            return {
                "success": False,
                "ticket": None,
                "price": None,
                "executed_volume": 0.0,
                "slippage_pips": 0.0,
                "error": str(e),
            }

    async def cancel_order(self, client_order_id: str) -> bool:
        """Cancel an active order."""
        if not self._connected or not HAS_IB_INSYNC:
            return False
        try:
            order_id = int(client_order_id)
            for trade in self.ib.openTrades():
                if trade.order.orderId == order_id:
                    self.ib.cancelOrder(trade.order)
                    return True
            return False
        except Exception as e:
            logger.error(f"[IBKR] Cancel order failed for {client_order_id}: {e}")
            return False

    async def get_orders(self, symbol: Optional[str] = None) -> List[dict]:
        """Return list of pending orders."""
        if not self._connected or not HAS_IB_INSYNC:
            return []
        try:
            trades = self.ib.openTrades()
            orders = []
            for t in trades:
                sec = t.contract.symbol
                if symbol and sec.upper() != symbol.upper():
                    continue
                orders.append({
                    "ticket": t.order.orderId,
                    "symbol": sec,
                    "type": t.order.action,
                    "volume": t.order.totalQuantity,
                    "price": getattr(t.order, "lmtPrice", 0.0),
                    "status": t.orderStatus.status,
                })
            return orders
        except Exception as e:
            logger.error(f"[IBKR] Error fetching orders: {e}")
            return []

    async def get_positions(self) -> List[dict]:
        """Return open positions."""
        if not self._connected or not HAS_IB_INSYNC:
            return []
        try:
            pos_list = self.ib.positions()
            positions = []
            for p in pos_list:
                positions.append({
                    "ticket": hash(f"{p.account}_{p.contract.conId}"),
                    "symbol": p.contract.symbol,
                    "type": "BUY" if p.position > 0 else "SELL",
                    "volume": abs(p.position),
                    "price_open": p.avgCost,
                    "account": p.account,
                })
            return positions
        except Exception as e:
            logger.error(f"[IBKR] Error fetching positions: {e}")
            return []

    async def get_account_info(self) -> dict:
        """Return account financial status."""
        if not self._connected or not HAS_IB_INSYNC:
            return {
                "balance": 0.0,
                "equity": 0.0,
                "margin": 0.0,
                "free_margin": 0.0,
                "leverage": 1.0,
                "connected": False,
                "broker": "Interactive Brokers",
            }
        try:
            summary = self.ib.accountSummary()
            acc_dict = {item.tag: float(item.value) for item in summary if item.value.replace('.', '', 1).isdigit()}
            equity = acc_dict.get("NetLiquidation", 0.0)
            balance = acc_dict.get("TotalCashValue", equity)
            margin = acc_dict.get("InitMarginReq", 0.0)
            free_margin = acc_dict.get("AvailableFunds", equity - margin)

            return {
                "balance": balance,
                "equity": equity,
                "margin": margin,
                "free_margin": free_margin,
                "leverage": 30.0,
                "connected": True,
                "broker": "Interactive Brokers",
            }
        except Exception as e:
            logger.error(f"[IBKR] Error reading account info: {e}")
            return {
                "balance": 0.0,
                "equity": 0.0,
                "margin": 0.0,
                "free_margin": 0.0,
                "leverage": 1.0,
                "error": str(e),
                "broker": "Interactive Brokers",
            }

    async def close_position(self, ticket: int, lots: Optional[float] = None) -> dict:
        """Close an open position by submitting opposite order."""
        positions = await self.get_positions()
        target = next((p for p in positions if p.get("ticket") == ticket), None)
        if not target:
            return {"success": False, "ticket": ticket, "error": f"Position {ticket} not found"}

        opposite_dir = "SELL" if target["type"] == "BUY" else "BUY"
        close_vol = lots or target["volume"]
        order = OrderRequest(
            symbol=target["symbol"],
            direction=opposite_dir,
            volume=close_vol,
            order_type="MARKET",
            comment=f"Close {ticket}",
        )
        res = await self.submit_order(order)
        return {
            "success": res.get("success", False),
            "ticket": ticket,
            "price": res.get("price"),
            "pnl": 0.0,
            "error": res.get("error"),
        }
