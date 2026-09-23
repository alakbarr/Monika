# ==============================================================================
# File: execution/broker_adapter.py
# ==============================================================================

"""
Broker Adapter Abstraction & Parity Engine (Phase 3).
Provides standardized broker abstraction for 100% research-to-live execution parity.

Adapters:
1. BrokerAdapter (ABC): Formal abstract interface.
2. MT5LiveAdapter: Live and paper trading wrapper around MT5Client.
3. SimulatedBrokerAdapter: High-fidelity simulation engine with spread model,
   ATR slippage, fill latency, margin & balance simulation.
"""

from abc import ABC, abstractmethod
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

import utils.clock as clock
from database.models import Order, OrderStatus
from execution.broker_plugin import OrderRequest, normalize_order_request
from execution.broker_registry import BrokerAdapterRegistry

logger = logging.getLogger("TradingAgent.BrokerAdapter")


def _get_pip_size(symbol: str) -> float:
    """Determine pip size based on instrument type."""
    sym = (symbol or "").upper()
    if "JPY" in sym:
        return 0.01
    if "XAU" in sym or "GOLD" in sym:
        return 0.01
    if "BTC" in sym or "ETH" in sym or "CRYPTO" in sym:
        return 1.0
    if any(k in sym for k in ("USO", "OIL", "BRENT", "XTI", "XBR", "UKOIL", "WTI")):
        return 0.01
    return 0.0001


def _get_contract_size(symbol: str) -> float:
    """Determine standard contract lot size based on instrument type."""
    sym = (symbol or "").upper()
    if "XAU" in sym or "GOLD" in sym:
        return 100.0  # 100 troy oz per lot
    if "BTC" in sym or "ETH" in sym:
        return 1.0    # 1 coin per lot
    if any(k in sym for k in ("XTI", "WTI")):
        return 100.0  # 100 barrels per lot
    if any(k in sym for k in ("USO", "OIL", "BRENT", "XBR", "UKOIL")):
        return 1000.0 # 1,000 barrels per lot
    return 100000.0   # 100,000 units standard FX lot


# ==============================================================================
# 1. Abstract Broker Adapter Interface
# ==============================================================================

class BrokerAdapter(ABC):
    """
    Abstract base class defining the standardized broker execution interface.
    Guarantees that both live execution and backtest simulation adhere to the
    exact same contracts and state semantics.
    """

    @abstractmethod
    async def get_tick(self, symbol: str) -> dict:
        """
        Fetch latest tick quote.
        Returns:
            dict with keys: 'symbol', 'bid', 'ask', 'last', 'spread', 'time'
        """
        pass

    @abstractmethod
    async def submit_order(self, order: Any, **kwargs) -> dict:
        """
        Submit an order for execution.
        Returns:
            dict with keys:
                'success': bool
                'ticket': Optional[int]
                'price': Optional[float]
                'executed_volume': float
                'slippage_pips': float
                'error': Optional[str]
        """
        pass

    @abstractmethod
    async def cancel_order(self, client_order_id: str) -> bool:
        """Cancel a pending/in-flight order."""
        pass

    @abstractmethod
    async def get_orders(self, symbol: Optional[str] = None) -> List[dict]:
        """Return list of all active pending orders."""
        pass

    @abstractmethod
    async def get_positions(self) -> List[dict]:
        """Return list of all open positions."""
        pass

    @abstractmethod
    async def get_account_info(self) -> dict:
        """
        Return account financial status.
        Returns:
            dict with keys: 'balance', 'equity', 'margin', 'free_margin', 'leverage'
        """
        pass

    @abstractmethod
    async def close_position(self, ticket: int, lots: Optional[float] = None) -> dict:
        """
        Close an open position.
        Returns:
            dict with keys: 'success', 'ticket', 'price', 'pnl', 'error'
        """
        pass

    async def close_all_positions(self, comment: str = "KillSwitch") -> dict:
        """
        Close all open positions on the broker adapter.
        Default implementation iterates over get_positions and calls close_position.
        """
        positions = await self.get_positions()
        closed_count = 0
        failed_count = 0
        errors = []
        for pos in positions:
            ticket = pos.get("ticket")
            if ticket:
                res = await self.close_position(ticket)
                if res.get("success"):
                    closed_count += 1
                else:
                    failed_count += 1
                    errors.append(res.get("error", f"Ticket {ticket} failed"))
        return {
            "closed": closed_count,
            "failed": failed_count,
            "total": len(positions),
            "errors": errors,
        }

    async def get_open_positions(self, symbol: Optional[str] = None) -> List[dict]:
        """Universal compatibility alias for get_positions with optional symbol filter."""
        positions = await self.get_positions()
        if symbol:
            sym_upper = symbol.upper()
            return [p for p in positions if p.get("symbol", "").upper() == sym_upper]
        return positions

    async def get_current_price(self, symbol: str) -> dict:
        """Universal compatibility alias for get_tick."""
        return await self.get_tick(symbol)

    async def ensure_connected(self) -> bool:
        """Universal compatibility check for broker connection."""
        return True

    async def is_connected(self) -> bool:
        """Universal check whether broker connection is active."""
        return True


# ==============================================================================
# 2. MT5 Live Adapter
# ==============================================================================

class MT5LiveAdapter(BrokerAdapter):
    """
    Adapter wrapping the live MT5Client instance.
    Directs orders to actual MetaTrader 5 terminal or simulated mock ticket if dry_run.
    """

    def __init__(
        self,
        mt5_client: Optional[Any] = None,
        settings: Optional[dict] = None,
        dry_run: bool = False,
        service: Optional[Any] = None,
    ):
        self._mt5 = mt5_client
        self.settings = settings or {}
        self._dry_run = dry_run
        self._service = service

    @property
    def dry_run(self) -> bool:
        if self._service is not None and hasattr(self._service, 'dry_run'):
            return getattr(self._service, 'dry_run')
        return self._dry_run

    @dry_run.setter
    def dry_run(self, val: bool):
        self._dry_run = val

    @property
    def mt5(self) -> Any:
        if self._service is not None and hasattr(self._service, 'mt5') and self._service.mt5 is not None:
            return self._service.mt5
        if self._mt5 is None:
            from execution.mt5_client import MT5Client
            self._mt5 = MT5Client(settings=self.settings)
        return self._mt5

    @mt5.setter
    def mt5(self, val: Any):
        self._mt5 = val

    async def is_connected(self) -> bool:
        try:
            return await self.mt5.is_connected()
        except Exception:
            return False

    async def get_tick(self, symbol: str) -> dict:
        try:
            cur_price = await self.mt5.get_current_price(symbol)
            if cur_price:
                bid = float(cur_price.get("bid", 0.0))
                ask = float(cur_price.get("ask", 0.0))
                spread = round(ask - bid, 5)
                return {
                    "symbol": symbol,
                    "bid": bid,
                    "ask": ask,
                    "last": float(cur_price.get("last", ask)),
                    "spread": spread,
                    "time": cur_price.get("time", clock.now()),
                }
        except Exception as e:
            logger.debug(f"[MT5LiveAdapter] get_current_price failed for {symbol}: {e}")

        # Fallback to get_spread
        try:
            sp = await self.mt5.get_spread(symbol)
            bid = float(sp.get("bid", 0.0))
            ask = float(sp.get("ask", 0.0))
            spread = float(sp.get("spread", 0.0))
            return {
                "symbol": symbol,
                "bid": bid,
                "ask": ask,
                "last": ask,
                "spread": spread,
                "time": clock.now(),
            }
        except Exception as e:
            logger.error(f"[MT5LiveAdapter] get_tick failed completely for {symbol}: {e}")
            return {
                "symbol": symbol,
                "bid": 0.0,
                "ask": 0.0,
                "last": 0.0,
                "spread": 0.0,
                "time": clock.now(),
            }

    async def submit_order(self, order: Any, **kwargs) -> dict:
        order = normalize_order_request(order)
        pip_size = _get_pip_size(order.symbol)
        is_pending_type = (order.order_type or "market").upper() in ("LIMIT", "STOP", "BUY_LIMIT", "SELL_LIMIT", "BUY_STOP", "SELL_STOP")

        if self.dry_run:
            import hashlib
            seed = f"{order.symbol}_{clock.now().isoformat()}_{order.client_order_id}"
            mock_ticket = int(hashlib.md5(seed.encode()).hexdigest(), 16) % 9000000 + 1000000
            if is_pending_type:
                logger.info(
                    f"[MT5LiveAdapter] DRY RUN: Placed pending {order.order_type} {order.client_order_id} {order.direction} "
                    f"{order.requested_volume} lots for {order.symbol} (mock ticket: {mock_ticket})"
                )
                return {
                    "success": True,
                    "ticket": mock_ticket,
                    "price": order.requested_price,
                    "executed_volume": 0.0,
                    "slippage_pips": 0.0,
                    "status": "accepted",
                    "error": None,
                }
            logger.info(
                f"[MT5LiveAdapter] DRY RUN: Order {order.client_order_id} {order.direction} "
                f"{order.requested_volume} lots for {order.symbol} (mock ticket: {mock_ticket})"
            )
            return {
                "success": True,
                "ticket": mock_ticket,
                "price": order.requested_price,
                "executed_volume": order.requested_volume,
                "slippage_pips": 0.0,
                "status": "filled",
                "error": None,
            }

        max_spread_mult = kwargs.get("max_spread_multiplier")
        if max_spread_mult is None:
            max_spread_mult = self.settings.get("execution", {}).get("max_spread_multiplier", {}).get(order.symbol, 10.0)

        cid = (order.client_order_id or getattr(order, 'id', None) or 'UNKNOWN')[:8]
        comment = kwargs.get("comment", f"ORD#{cid}")
        res = await self.mt5.place_order(
            symbol=order.symbol,
            direction=order.direction.lower(),
            volume=order.requested_volume,
            price=order.requested_price,
            sl=kwargs.get("sl"),
            tp=kwargs.get("tp"),
            comment=comment,
            order_type=order.order_type.lower(),
            max_spread_multiplier=max_spread_mult,
        )

        success = bool(res.get("success", False))
        ticket = res.get("ticket")
        executed_price = res.get("price") or order.requested_price
        slippage_pips = 0.0
        if success and executed_price and order.requested_price:
            slippage_pips = round(abs(executed_price - order.requested_price) / pip_size, 2)

        if success and is_pending_type:
            status = "accepted"
            exec_vol = 0.0
        elif success:
            status = "filled"
            exec_vol = order.requested_volume
        else:
            status = "rejected"
            exec_vol = 0.0

        return {
            "success": success,
            "ticket": ticket,
            "price": executed_price if success else None,
            "executed_volume": exec_vol,
            "slippage_pips": slippage_pips,
            "status": status,
            "error": res.get("error"),
        }

    async def cancel_order(self, client_order_id: Any) -> bool:
        logger.info(f"[MT5LiveAdapter] Cancel order requested for {client_order_id}")
        if self.dry_run:
            return True
        if hasattr(self.mt5, "cancel_order"):
            try:
                ticket = None
                try:
                    ticket = int(client_order_id)
                except (ValueError, TypeError):
                    active_orders = await self.get_orders()
                    target_str = str(client_order_id)
                    for o in active_orders:
                        c_str = str(o.get("comment", ""))
                        cid_str = str(o.get("client_order_id", ""))
                        if target_str in c_str or target_str == cid_str:
                            ticket = o.get("ticket")
                            break
                if ticket is None:
                    logger.warning(f"[MT5LiveAdapter] Cannot resolve ticket for client_order_id {client_order_id}")
                    return False

                res = await self.mt5.cancel_order(ticket)
                if isinstance(res, dict):
                    return bool(res.get("success", False))
                return bool(res)
            except Exception as e:
                logger.error(f"[MT5LiveAdapter] cancel_order failed for {client_order_id}: {e}")
                return False
        return True

    async def get_orders(self, symbol: Optional[str] = None) -> List[dict]:
        if self.dry_run:
            return []
        try:
            if hasattr(self.mt5, "get_orders"):
                return await self.mt5.get_orders(symbol=symbol)
            return []
        except Exception as e:
            logger.error(f"[MT5LiveAdapter] get_orders failed: {e}")
            return []

    async def get_open_positions(self, symbol: Optional[str] = None) -> List[dict]:
        try:
            return await self.mt5.get_open_positions(symbol)
        except Exception as e:
            logger.error(f"[MT5LiveAdapter] get_open_positions failed: {e}")
            return []

    async def get_positions(self) -> List[dict]:
        try:
            return await self.mt5.get_open_positions()
        except Exception as e:
            logger.error(f"[MT5LiveAdapter] get_positions failed: {e}")
            return []

    async def ensure_connected(self) -> bool:
        if self.dry_run:
            return True
        try:
            if hasattr(self.mt5, "ensure_connected"):
                return await self.mt5.ensure_connected()
            return True
        except Exception as e:
            logger.error(f"[MT5LiveAdapter] ensure_connected failed: {e}")
            return False

    async def get_account_info(self) -> dict:
        try:
            acc = await self.mt5.get_account_info()
            return acc or {}
        except Exception as e:
            logger.error(f"[MT5LiveAdapter] get_account_info failed: {e}")
            return {}

    async def close_position(self, ticket: int, lots: Optional[float] = None) -> dict:
        if self.dry_run:
            logger.info(f"[MT5LiveAdapter] DRY RUN: close position #{ticket}")
            return {"success": True, "ticket": ticket, "price": 0.0, "pnl": 0.0, "error": None}
        try:
            res = await self.mt5.close_position(ticket=ticket, volume=lots, lots=lots)
            pnl = res.get("pnl") if "pnl" in res else res.get("profit", 0.0)
            return {
                "success": res.get("success", False),
                "ticket": ticket,
                "price": res.get("price", 0.0),
                "pnl": pnl,
                "error": res.get("error"),
                "retcode": res.get("retcode"),
            }
        except Exception as e:
            logger.error(f"[MT5LiveAdapter] close_position failed for #{ticket}: {e}")
            return {"success": False, "ticket": ticket, "price": 0.0, "pnl": 0.0, "error": str(e)}

    async def close_all_positions(self, comment: str = "KillSwitch") -> dict:
        if self.dry_run:
            logger.info(f"[MT5LiveAdapter] DRY RUN: close all positions with comment={comment}")
            return {"closed": 0, "failed": 0, "total": 0, "errors": []}
        if hasattr(self.mt5, "close_all_positions"):
            return await self.mt5.close_all_positions(comment=comment)
        return await super().close_all_positions(comment=comment)


# ==============================================================================
# 3. Simulated Broker Adapter (100% Research-to-Live Parity)
# ==============================================================================

class SimulatedBrokerAdapter(BrokerAdapter):
    """
    High-fidelity simulated broker adapter for backtesting and offline verification.
    Features:
    - Dynamic or configurable spread model.
    - ATR-based and pip-based execution slippage.
    - Fill latency simulation via non-blocking asyncio.
    - Margin requirement validation (contract size, leverage, free margin).
    - Position tracking and real-time mark-to-market PnL calculation.
    """

    def __init__(
        self,
        initial_balance: float = 10000.0,
        leverage: float = 100.0,
        default_spread_pips: float = 1.5,
        symbol_spread_pips: Optional[Dict[str, float]] = None,
        atr_slippage_pips: float = 0.5,
        fill_latency_ms: float = 0.0,
        settings: Optional[dict] = None,
    ):
        self.settings = settings or {}
        self.balance: float = float(initial_balance)
        self.leverage: float = float(leverage)
        self.default_spread_pips: float = default_spread_pips
        self.symbol_spread_pips: Dict[str, float] = symbol_spread_pips or {
            "EURUSD": 1.2,
            "GBPUSD": 1.6,
            "USDJPY": 1.4,
            "XAUUSD": 2.5,
            "BTCUSD": 15.0,
        }
        self.atr_slippage_pips: float = atr_slippage_pips
        self.fill_latency_ms: float = fill_latency_ms

        self.positions: Dict[int, dict] = {}
        self.pending_orders: Dict[str, Order] = {}
        self.pending_order_kwargs: Dict[str, dict] = {}
        self.current_prices: Dict[str, dict] = {}
        self._next_ticket: int = 100001

    def reset(self, balance: Optional[float] = None) -> None:
        """Reset adapter state to avoid memory growth and allow fresh backtests."""
        if balance is not None:
            self.balance = float(balance)
        self.positions.clear()
        self.pending_orders.clear()
        self.pending_order_kwargs.clear()
        self.current_prices.clear()
        self._next_ticket = 100001

    def set_tick(
        self,
        symbol: str,
        bid: float,
        ask: float,
        last: Optional[float] = None,
        timestamp: Optional[datetime] = None,
    ):
        """Manually inject price tick into simulation and check pending orders."""
        spread = round(ask - bid, 5)
        tick = {
            "symbol": symbol,
            "bid": float(bid),
            "ask": float(ask),
            "last": float(last or ask),
            "spread": spread,
            "time": timestamp or clock.now(),
        }
        self.current_prices[symbol] = tick
        self.check_pending_orders(symbol)

    async def get_tick(self, symbol: str) -> dict:
        if symbol in self.current_prices:
            return self.current_prices[symbol]

        pip_size = _get_pip_size(symbol)
        spread_pips = self.symbol_spread_pips.get(symbol, self.default_spread_pips)
        half_spread = (spread_pips * pip_size) / 2.0

        # Baseline realistic mid prices
        default_mids = {
            "EURUSD": 1.08500,
            "GBPUSD": 1.27000,
            "USDJPY": 155.000,
            "XAUUSD": 2350.00,
            "BTCUSD": 65000.0,
        }
        mid = default_mids.get(symbol, 1.0000)

        bid = mid - half_spread
        ask = mid + half_spread
        tick = {
            "symbol": symbol,
            "bid": round(bid, 5),
            "ask": round(ask, 5),
            "last": round(ask, 5),
            "spread": round(ask - bid, 5),
            "time": clock.now(),
        }
        self.current_prices[symbol] = tick
        return tick

    def _compute_account_info_sync(self) -> dict:
        """Internal synchronous account state calculation."""
        total_unrealized = 0.0
        used_margin = 0.0

        for ticket, pos in self.positions.items():
            used_margin += pos.get("margin", 0.0)
            sym = pos["symbol"]
            tick = self.current_prices.get(sym)
            if tick:
                contract_size = _get_contract_size(sym)
                vol = pos["volume"]
                if pos["type"] == "buy":
                    unrealized = (tick["bid"] - pos["open_price"]) * contract_size * vol
                else:
                    unrealized = (pos["open_price"] - tick["ask"]) * contract_size * vol
                total_unrealized += unrealized

        equity = self.balance + total_unrealized
        free_margin = max(0.0, equity - used_margin)
        margin_level = (equity / used_margin * 100.0) if used_margin > 0 else 0.0

        return {
            "balance": round(self.balance, 2),
            "equity": round(equity, 2),
            "margin": round(used_margin, 2),
            "free_margin": round(free_margin, 2),
            "margin_level": round(margin_level, 2),
            "leverage": self.leverage,
        }

    def _fill_order_internal(self, order: Order, tick: dict, **kwargs) -> dict:
        """Execute fill calculations for market orders or triggered pending orders."""
        symbol = order.symbol
        direction = (order.direction or "").lower().strip()
        pip_size = _get_pip_size(symbol)
        contract_size = _get_contract_size(symbol)

        slippage_price = self.atr_slippage_pips * pip_size
        if direction == "buy":
            base_price = tick["ask"]
            fill_price = base_price + slippage_price
        else:
            base_price = tick["bid"]
            fill_price = base_price - slippage_price

        # Robust reference price for slippage calculation
        req_price = order.requested_price
        ref_price = req_price if (req_price is not None and req_price > 0) else base_price
        actual_slippage_pips = round(abs(fill_price - ref_price) / pip_size, 2)

        # Margin requirement check
        required_margin = (order.requested_volume * contract_size * fill_price) / self.leverage
        acc = self._compute_account_info_sync()
        free_margin = acc.get("free_margin", 0.0)

        if required_margin > free_margin:
            err_msg = (
                f"Margin call: required margin ${required_margin:.2f} "
                f"exceeds free margin ${free_margin:.2f}"
            )
            logger.warning(f"[SimulatedBrokerAdapter] Order {order.client_order_id} rejected: {err_msg}")
            return {
                "success": False,
                "ticket": None,
                "price": None,
                "executed_volume": 0.0,
                "slippage_pips": 0.0,
                "error": err_msg,
            }

        # Partial fill check if requested
        partial_ratio = float(kwargs.get("partial_fill_ratio", 1.0))
        partial_ratio = max(0.01, min(1.0, partial_ratio))
        executed_volume = round(order.requested_volume * partial_ratio, 2)
        if executed_volume <= 0:
            executed_volume = order.requested_volume

        is_partial = executed_volume < order.requested_volume
        status = "partially_filled" if is_partial else "filled"

        ticket = getattr(order, "mt5_ticket", None)
        if not ticket:
            ticket = self._next_ticket
            self._next_ticket += 1
        order.mt5_ticket = ticket
        cid = (order.client_order_id or getattr(order, 'id', None) or 'UNKNOWN')[:8]
        comment = kwargs.get("comment", f"ORD#{cid}")
        actual_margin = (executed_volume * contract_size * fill_price) / self.leverage
        pos = {
            "ticket": ticket,
            "id": ticket,
            "order_id": getattr(order, "id", None) or getattr(order, "client_order_id", "UNKNOWN"),
            "client_order_id": order.client_order_id,
            "symbol": symbol,
            "type": direction,
            "volume": float(executed_volume),
            "open_price": round(fill_price, 5),
            "price_open": round(fill_price, 5),
            "price": round(fill_price, 5),
            "sl": kwargs.get("sl") if kwargs.get("sl") is not None else getattr(order, "stop_loss", None),
            "tp": kwargs.get("tp") if kwargs.get("tp") is not None else getattr(order, "take_profit", None),
            "comment": comment,
            "time": clock.now().timestamp(),
            "margin": actual_margin,
            "pnl": 0.0,
            "unrealized_pnl": 0.0,
        }
        self.positions[ticket] = pos

        logger.info(
            f"[SimulatedBrokerAdapter] {status.upper()} #{ticket}: {direction.upper()} {executed_volume} lots "
            f"{symbol} @ {fill_price:.5f} (slippage: {actual_slippage_pips} pips, req_margin: ${actual_margin:.2f})"
        )

        return {
            "success": True,
            "ticket": ticket,
            "price": round(fill_price, 5),
            "executed_volume": float(executed_volume),
            "slippage_pips": actual_slippage_pips,
            "status": status,
            "error": None,
        }

    def check_pending_orders(self, symbol: Optional[str] = None) -> List[dict]:
        """Check and fill any pending LIMIT or STOP orders whose price conditions are met."""
        filled_results = []
        to_remove = []
        for client_id, pending_order in list(self.pending_orders.items()):
            if symbol and pending_order.symbol.upper() != symbol.upper():
                continue
            tick = self.current_prices.get(pending_order.symbol)
            if not tick:
                continue

            order_type = (pending_order.order_type or "MARKET").upper()
            direction = (pending_order.direction or "").lower().strip()
            req_price = pending_order.requested_price

            can_fill = False
            if order_type == "LIMIT" and req_price is not None:
                if direction == "buy" and tick["ask"] <= req_price:
                    can_fill = True
                elif direction == "sell" and tick["bid"] >= req_price:
                    can_fill = True
            elif order_type == "STOP" and req_price is not None:
                if direction == "buy" and tick["ask"] >= req_price:
                    can_fill = True
                elif direction == "sell" and tick["bid"] <= req_price:
                    can_fill = True

            if can_fill:
                kw = self.pending_order_kwargs.get(client_id, {})
                fill_res = self._fill_order_internal(pending_order, tick, **kw)
                filled_results.append(fill_res)
                if fill_res.get("status") == "partially_filled":
                    pending_order.filled_volume = (pending_order.filled_volume or 0.0) + fill_res.get("executed_volume", 0.0)
                    if pending_order.filled_volume >= pending_order.requested_volume:
                        to_remove.append(client_id)
                else:
                    pending_order.filled_volume = pending_order.requested_volume
                    to_remove.append(client_id)

        for cid in to_remove:
            self.pending_orders.pop(cid, None)
            self.pending_order_kwargs.pop(cid, None)

        return filled_results

    async def submit_order(self, order: Any, **kwargs) -> dict:
        order = normalize_order_request(order)
        # 1. Fill latency simulation
        if self.fill_latency_ms > 0:
            await asyncio.sleep(self.fill_latency_ms / 1000.0)

        # 2. Input validation
        direction = (order.direction or "").lower().strip()
        if direction not in ("buy", "sell"):
            return {
                "success": False,
                "ticket": None,
                "price": None,
                "executed_volume": 0.0,
                "slippage_pips": 0.0,
                "error": f"Invalid order direction: '{order.direction}'. Must be 'buy' or 'sell'.",
            }

        if order.requested_volume is None or order.requested_volume <= 0:
            return {
                "success": False,
                "ticket": None,
                "price": None,
                "executed_volume": 0.0,
                "slippage_pips": 0.0,
                "error": f"Invalid requested volume: {order.requested_volume}. Must be strictly positive.",
            }

        symbol = order.symbol
        tick = await self.get_tick(symbol)

        order_type = (order.order_type or "MARKET").upper()
        req_price = order.requested_price

        # 3. Check for LIMIT / STOP pending orders
        is_pending = False
        if order_type == "LIMIT" and req_price is not None and req_price > 0:
            if direction == "buy" and tick["ask"] > req_price:
                is_pending = True
            elif direction == "sell" and tick["bid"] < req_price:
                is_pending = True
        elif order_type == "STOP" and req_price is not None and req_price > 0:
            if direction == "buy" and tick["ask"] < req_price:
                is_pending = True
            elif direction == "sell" and tick["bid"] > req_price:
                is_pending = True

        if is_pending:
            ticket = self._next_ticket
            self._next_ticket += 1
            order.mt5_ticket = ticket
            self.pending_orders[order.client_order_id] = order
            self.pending_order_kwargs[order.client_order_id] = dict(kwargs)
            logger.info(
                f"[SimulatedBrokerAdapter] Placed PENDING {order_type} #{order.client_order_id}: "
                f"{direction.upper()} {order.requested_volume} lots {symbol} @ {req_price:.5f} (ticket: {ticket})"
            )
            return {
                "success": True,
                "ticket": ticket,
                "price": req_price,
                "executed_volume": 0.0,
                "slippage_pips": 0.0,
                "status": "pending",
                "error": None,
            }

        return self._fill_order_internal(order, tick, **kwargs)

    async def cancel_order(self, client_order_id: Any) -> bool:
        cid_str = str(client_order_id)
        if cid_str in self.pending_orders:
            del self.pending_orders[cid_str]
            self.pending_order_kwargs.pop(cid_str, None)
            logger.info(f"[SimulatedBrokerAdapter] Cancelled pending order {cid_str}")
            return True
        for k, o in list(self.pending_orders.items()):
            if str(getattr(o, "mt5_ticket", "")) == cid_str or getattr(o, "client_order_id", "") == cid_str:
                del self.pending_orders[k]
                self.pending_order_kwargs.pop(k, None)
                logger.info(f"[SimulatedBrokerAdapter] Cancelled pending order {k} (ticket {cid_str})")
                return True
        logger.debug(f"[SimulatedBrokerAdapter] cancel_order: {client_order_id} not found in pending orders")
        return False

    async def get_orders(self, symbol: Optional[str] = None) -> List[dict]:
        """Return list of active pending orders."""
        res = []
        for cid, o in self.pending_orders.items():
            if symbol and o.symbol.upper() != symbol.upper():
                continue
            ticket = getattr(o, "mt5_ticket", None)
            res.append({
                "ticket": ticket,
                "client_order_id": o.client_order_id,
                "symbol": o.symbol,
                "type": (o.order_type or "LIMIT").upper(),
                "direction": (o.direction or "buy").lower(),
                "volume": float(o.requested_volume),
                "volume_initial": float(o.requested_volume),
                "volume_current": float(o.requested_volume - (getattr(o, "filled_volume", 0.0) or 0.0)),
                "price_open": float(o.requested_price) if o.requested_price else 0.0,
                "sl": getattr(o, "sl", None),
                "tp": getattr(o, "tp", None),
                "time": getattr(o, "created_at", None) or clock.now(),
                "status": "pending",
            })
        return res

    async def get_positions(self) -> List[dict]:
        # Update mark-to-market unrealized PnL on positions
        res = []
        for ticket, pos in self.positions.items():
            sym = pos["symbol"]
            tick = await self.get_tick(sym)
            contract_size = _get_contract_size(sym)
            vol = pos["volume"]
            if pos["type"] == "buy":
                unrealized = (tick["bid"] - pos["open_price"]) * contract_size * vol
            else:
                unrealized = (pos["open_price"] - tick["ask"]) * contract_size * vol
            
            p_copy = dict(pos)
            p_copy["pnl"] = round(unrealized, 2)
            p_copy["unrealized_pnl"] = round(unrealized, 2)
            res.append(p_copy)
        return res

    async def get_account_info(self) -> dict:
        total_unrealized = 0.0
        used_margin = 0.0

        for ticket, pos in self.positions.items():
            used_margin += pos.get("margin", 0.0)
            sym = pos["symbol"]
            tick = await self.get_tick(sym)
            contract_size = _get_contract_size(sym)
            vol = pos["volume"]
            if pos["type"] == "buy":
                unrealized = (tick["bid"] - pos["open_price"]) * contract_size * vol
            else:
                unrealized = (pos["open_price"] - tick["ask"]) * contract_size * vol
            total_unrealized += unrealized

        equity = self.balance + total_unrealized
        free_margin = max(0.0, equity - used_margin)
        margin_level = (equity / used_margin * 100.0) if used_margin > 0 else 0.0

        return {
            "balance": round(self.balance, 2),
            "equity": round(equity, 2),
            "margin": round(used_margin, 2),
            "free_margin": round(free_margin, 2),
            "margin_level": round(margin_level, 2),
            "leverage": self.leverage,
        }

    async def close_position(self, ticket: int, lots: Optional[float] = None) -> dict:
        if ticket not in self.positions:
            return {
                "success": False,
                "ticket": ticket,
                "price": 0.0,
                "pnl": 0.0,
                "error": f"Position #{ticket} not found",
            }

        pos = self.positions[ticket]
        if lots is not None:
            try:
                lots_f = float(lots)
                if lots_f <= 0:
                    return {
                        "success": False,
                        "ticket": ticket,
                        "price": 0.0,
                        "pnl": 0.0,
                        "error": f"Invalid close volume: {lots}. Must be > 0.",
                    }
            except (ValueError, TypeError):
                return {
                    "success": False,
                    "ticket": ticket,
                    "price": 0.0,
                    "pnl": 0.0,
                    "error": f"Invalid close volume type: {lots}",
                }

        symbol = pos["symbol"]
        contract_size = _get_contract_size(symbol)
        tick = await self.get_tick(symbol)

        vol_to_close = float(lots) if (lots is not None and 0 < float(lots) < pos["volume"]) else pos["volume"]

        pos_type = str(pos.get("type") or pos.get("direction") or "buy").lower()
        open_price = float(pos.get("open_price") or pos.get("entry_price") or tick.get("bid", 1.0))

        if pos_type == "buy":
            exit_price = tick.get("bid", open_price)
            diff = exit_price - open_price
        else:
            exit_price = tick.get("ask", open_price)
            diff = open_price - exit_price

        realized_pnl = round(diff * contract_size * vol_to_close, 2)
        self.balance = round(self.balance + realized_pnl, 2)

        if vol_to_close >= pos["volume"]:
            del self.positions[ticket]
        else:
            pos["volume"] = round(pos["volume"] - vol_to_close, 2)
            pos["margin"] = (pos["volume"] * contract_size * pos["open_price"]) / self.leverage

        logger.info(
            f"[SimulatedBrokerAdapter] CLOSED #{ticket}: {symbol} {vol_to_close} lots @ {exit_price} "
            f"(PnL: ${realized_pnl:+.2f}, New Balance: ${self.balance:.2f})"
        )

        return {
            "success": True,
            "ticket": ticket,
            "price": round(exit_price, 5),
            "pnl": realized_pnl,
            "closed_volume": vol_to_close,
            "error": None,
        }

    async def close_all_positions(self, comment: str = "KillSwitch") -> dict:
        tickets = list(self.positions.keys())
        closed = 0
        failed = 0
        errors = []
        for t in tickets:
            res = await self.close_position(t)
            if res.get("success"):
                closed += 1
            else:
                failed += 1
                errors.append(res.get("error", "Failed to close"))
        return {"closed": closed, "failed": failed, "total": len(tickets), "errors": errors}


# ==============================================================================
# 4. Remote Gateway Broker Adapter (Cross-Platform Linux / VPS)
# ==============================================================================

class MT5RemoteGatewayAdapter(BrokerAdapter):
    """
    Remote Gateway Broker Adapter for decoupled headless Linux / Ubuntu VPS deployment.
    Communicates with a remote MT5 bridge service via HTTP/REST / WebSocket RPC.
    Enables running the AI Trading Agent without requiring local Windows MetaTrader5 C-extension.
    """

    def __init__(
        self,
        gateway_url: str = "http://127.0.0.1:8080",
        api_token: Optional[str] = None,
        timeout: float = 10.0,
    ):
        self.gateway_url = gateway_url.rstrip("/")
        self.api_token = api_token
        self.timeout = timeout
        self._connected = False

    async def ensure_connected(self) -> bool:
        """Verify connectivity to remote gateway."""
        try:
            import aiohttp
            headers = {"Authorization": f"Bearer {self.api_token}"} if self.api_token else {}
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.gateway_url}/health",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as resp:
                    self._connected = (resp.status == 200)
                    return self._connected
        except Exception as e:
            logger.debug(f"[MT5RemoteGatewayAdapter] Connection check note: {e}")
            self._connected = False
            return False

    async def get_tick(self, symbol: str) -> dict:
        try:
            import aiohttp
            headers = {"Authorization": f"Bearer {self.api_token}"} if self.api_token else {}
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.gateway_url}/tick/{symbol}",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception as e:
            logger.warning(f"[MT5RemoteGatewayAdapter] get_tick failed for {symbol}: {e}")
        return {
            "symbol": symbol,
            "bid": 0.0,
            "ask": 0.0,
            "last": 0.0,
            "spread": 0.0,
            "time": clock.now().isoformat(),
        }

    async def get_current_price(self, symbol: str) -> dict:
        return await self.get_tick(symbol)

    async def submit_order(self, order: Any, **kwargs) -> dict:
        order = normalize_order_request(order)
        try:
            import aiohttp
            headers = {"Authorization": f"Bearer {self.api_token}"} if self.api_token else {}
            order_type_val = getattr(order.order_type, "value", str(order.order_type))
            volume = getattr(order, "volume", None) or getattr(order, "requested_volume", 0.0)
            entry_price = getattr(order, "entry_price", None) or getattr(order, "requested_price", 0.0) or getattr(order, "price", 0.0)
            direction = getattr(order, "direction", "buy")
            sl = kwargs.get("sl") or getattr(order, "stop_loss", None) or getattr(order, "sl", None)
            tp = kwargs.get("tp") or getattr(order, "take_profit", None) or getattr(order, "tp", None)
            comment = kwargs.get("comment", getattr(order, "comment", ""))
            payload = {
                "symbol": order.symbol,
                "direction": str(direction).lower(),
                "order_type": order_type_val,
                "volume": float(volume),
                "entry_price": float(entry_price),
                "stop_loss": float(sl) if sl is not None else None,
                "take_profit": float(tp) if tp is not None else None,
                "client_order_id": order.client_order_id,
                "comment": str(comment),
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.gateway_url}/orders",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    err_text = await resp.text()
                    return {"success": False, "error": f"Gateway error {resp.status}: {err_text}"}
        except Exception as e:
            logger.error(f"[MT5RemoteGatewayAdapter] submit_order failed: {e}")
            return {"success": False, "error": str(e)}

    async def cancel_order(self, client_order_id: str) -> bool:
        try:
            import aiohttp
            headers = {"Authorization": f"Bearer {self.api_token}"} if self.api_token else {}
            async with aiohttp.ClientSession() as session:
                async with session.delete(
                    f"{self.gateway_url}/orders/{client_order_id}",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as resp:
                    return resp.status == 200
        except Exception as e:
            logger.warning(f"[MT5RemoteGatewayAdapter] cancel_order failed for {client_order_id}: {e}")
            return False

    async def close_position(self, ticket: int, lots: Optional[float] = None) -> dict:
        try:
            import aiohttp
            headers = {"Authorization": f"Bearer {self.api_token}"} if self.api_token else {}
            payload = {"lots": lots} if lots else {}
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.gateway_url}/positions/{ticket}/close",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    err_text = await resp.text()
                    return {"success": False, "ticket": ticket, "price": 0.0, "pnl": 0.0, "error": f"Gateway error {resp.status}: {err_text}"}
        except Exception as e:
            logger.error(f"[MT5RemoteGatewayAdapter] close_position failed for {ticket}: {e}")
            return {"success": False, "ticket": ticket, "price": 0.0, "pnl": 0.0, "error": str(e)}

    async def get_orders(self, symbol: Optional[str] = None) -> List[dict]:
        try:
            import aiohttp
            headers = {"Authorization": f"Bearer {self.api_token}"} if self.api_token else {}
            params = {"symbol": symbol} if symbol else {}
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.gateway_url}/orders",
                    headers=headers,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception as e:
            logger.warning(f"[MT5RemoteGatewayAdapter] get_orders failed: {e}")
        return []

    async def get_positions(self) -> List[dict]:
        try:
            import aiohttp
            headers = {"Authorization": f"Bearer {self.api_token}"} if self.api_token else {}
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.gateway_url}/positions",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception as e:
            logger.warning(f"[MT5RemoteGatewayAdapter] get_positions failed: {e}")
        return []

    async def get_open_positions(self, symbol: Optional[str] = None) -> List[dict]:
        positions = await self.get_positions()
        if symbol:
            return [p for p in positions if p.get("symbol", "").upper() == symbol.upper()]
        return positions

    async def get_account_info(self) -> dict:
        try:
            import aiohttp
            headers = {"Authorization": f"Bearer {self.api_token}"} if self.api_token else {}
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.gateway_url}/account",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception as e:
            logger.warning(f"[MT5RemoteGatewayAdapter] get_account_info failed: {e}")
        return {"balance": 0.0, "equity": 0.0, "margin": 0.0, "free_margin": 0.0, "leverage": 100.0}

