# ==============================================================================
# File: execution/service/multi_account_adapter.py
# ==============================================================================

"""
Multi-Account Composite Broker Adapter & Trade Copier (Async).
Enables 1-to-N trade copying across multiple broker accounts (e.g. Master MT5 + Slave MT5/IBKR)
with proportional equity lot-sizing and parallel order dispatch.
"""

import asyncio
import copy
import logging
from typing import Any, Dict, List, Optional

import utils.clock as clock
from execution.broker_adapter import BrokerAdapter
from execution.broker_plugin import OrderRequest, normalize_order_request

logger = logging.getLogger("TradingAgent.MultiAccountAdapter")


class MultiAccountBrokerAdapter(BrokerAdapter):
    """
    Composite broker adapter implementing 1-to-N multi-account trade replication.
    Orders sent to the master account are automatically mirrored proportionally
    to all registered slave accounts based on equity ratios.
    """

    def __init__(
        self,
        master_adapter: Optional[BrokerAdapter] = None,
        slaves: Optional[Dict[str, BrokerAdapter]] = None,
        min_lot: float = 0.01,
        max_lot: float = 50.0,
        **kwargs,
    ):
        self.master_adapter = master_adapter
        self.slaves: Dict[str, BrokerAdapter] = slaves or {}
        self.min_lot = min_lot
        self.max_lot = max_lot

    def add_slave(self, account_id: str, adapter: BrokerAdapter) -> None:
        """Register a new slave copier account adapter."""
        self.slaves[account_id] = adapter
        logger.info(f"[MultiAccount] Registered slave account: {account_id}")

    def remove_slave(self, account_id: str) -> None:
        """Remove a slave copier account adapter."""
        if account_id in self.slaves:
            del self.slaves[account_id]
            logger.info(f"[MultiAccount] Removed slave account: {account_id}")

    def _ensure_master(self) -> BrokerAdapter:
        if self.master_adapter is None:
            from execution.broker_registry import BrokerAdapterRegistry
            self.master_adapter = BrokerAdapterRegistry.get("mt5_live") or BrokerAdapterRegistry.get("simulated")
        return self.master_adapter

    async def get_tick(self, symbol: str) -> dict:
        """Fetch tick quote from the master account adapter."""
        master = self._ensure_master()
        return await master.get_tick(symbol)

    async def submit_order(self, order: Any, **kwargs) -> dict:
        """
        Execute order on master account, then replicate proportionally across all slaves.
        """
        master = self._ensure_master()
        req: OrderRequest = normalize_order_request(order)

        # 1. Execute on Master Account
        master_res = await master.submit_order(req, **kwargs)
        if not master_res.get("success"):
            logger.warning(f"[MultiAccount] Master order failed: {master_res.get('error')}. Skipping slave replication.")
            return master_res

        # If no slaves configured, return master response directly
        if not self.slaves:
            return master_res

        # 2. Compute proportional sizing and replicate to Slaves concurrently
        master_info = await master.get_account_info()
        master_equity = float(master_info.get("equity") or master_info.get("balance") or 10000.0)

        replication_results: Dict[str, Any] = {}

        async def _replicate_to_slave(acc_id: str, slave_adapter: BrokerAdapter):
            try:
                slave_info = await slave_adapter.get_account_info()
                slave_equity = float(slave_info.get("equity") or slave_info.get("balance") or master_equity)

                # Proportional sizing formula: L_slave = round(L_master * (E_slave / E_master), 2)
                ratio = max(0.01, slave_equity / max(master_equity, 100.0))
                slave_lot = round(req.volume * ratio, 2)
                slave_lot = max(self.min_lot, min(self.max_lot, slave_lot))

                slave_req = copy.deepcopy(req)
                slave_req.volume = slave_lot
                slave_req.comment = f"Copy:{req.comment or 'Monika'}"

                res = await slave_adapter.submit_order(slave_req, **kwargs)
                return acc_id, {
                    "success": res.get("success", False),
                    "ticket": res.get("ticket"),
                    "allocated_lot": slave_lot,
                    "price": res.get("price"),
                    "error": res.get("error"),
                }
            except Exception as e:
                logger.error(f"[MultiAccount] Error copying to slave {acc_id}: {e}")
                return acc_id, {"success": False, "error": str(e)}

        tasks = [_replicate_to_slave(acc_id, adapter) for acc_id, adapter in self.slaves.items()]
        results = await asyncio.gather(*tasks, return_exceptions=False)
        for acc_id, res in results:
            replication_results[acc_id] = res

        master_res["slaves_replicated"] = replication_results
        return master_res

    async def cancel_order(self, client_order_id: str) -> bool:
        """Cancel order across master and all slave accounts."""
        master = self._ensure_master()
        results = [await master.cancel_order(client_order_id)]
        for slave in self.slaves.values():
            results.append(await slave.cancel_order(client_order_id))
        return any(results)

    async def get_orders(self, symbol: Optional[str] = None) -> List[dict]:
        """Return aggregated active orders across all accounts."""
        master = self._ensure_master()
        all_orders = []
        master_orders = await master.get_orders(symbol)
        for o in master_orders:
            o_tagged = dict(o)
            o_tagged["account_role"] = "master"
            all_orders.append(o_tagged)

        for acc_id, slave in self.slaves.items():
            try:
                slave_orders = await slave.get_orders(symbol)
                for so in slave_orders:
                    so_tagged = dict(so)
                    so_tagged["account_role"] = f"slave_{acc_id}"
                    all_orders.append(so_tagged)
            except Exception as e:
                logger.debug(f"[MultiAccount] Could not fetch orders from slave {acc_id}: {e}")

        return all_orders

    async def get_positions(self) -> List[dict]:
        """Return aggregated open positions across master and slaves."""
        master = self._ensure_master()
        all_positions = []
        master_pos = await master.get_positions()
        for p in master_pos:
            p_tagged = dict(p)
            p_tagged["account_role"] = "master"
            all_positions.append(p_tagged)

        for acc_id, slave in self.slaves.items():
            try:
                slave_pos = await slave.get_positions()
                for sp in slave_pos:
                    sp_tagged = dict(sp)
                    sp_tagged["account_role"] = f"slave_{acc_id}"
                    all_positions.append(sp_tagged)
            except Exception as e:
                logger.debug(f"[MultiAccount] Could not fetch positions from slave {acc_id}: {e}")

        return all_positions

    async def get_account_info(self) -> dict:
        """
        Return consolidated multi-account financial summary and per-account breakdown.
        """
        master = self._ensure_master()
        master_info = await master.get_account_info()

        total_balance = float(master_info.get("balance", 0.0))
        total_equity = float(master_info.get("equity", 0.0))
        total_margin = float(master_info.get("margin", 0.0))
        total_free_margin = float(master_info.get("free_margin", 0.0))

        accounts_detail = {
            "master": master_info,
        }

        for acc_id, slave in self.slaves.items():
            try:
                s_info = await slave.get_account_info()
                accounts_detail[f"slave_{acc_id}"] = s_info
                total_balance += float(s_info.get("balance", 0.0))
                total_equity += float(s_info.get("equity", 0.0))
                total_margin += float(s_info.get("margin", 0.0))
                total_free_margin += float(s_info.get("free_margin", 0.0))
            except Exception as e:
                accounts_detail[f"slave_{acc_id}"] = {"error": str(e)}

        return {
            "is_multi_account": True,
            "total_accounts": 1 + len(self.slaves),
            "balance": round(total_balance, 2),
            "equity": round(total_equity, 2),
            "margin": round(total_margin, 2),
            "free_margin": round(total_free_margin, 2),
            "leverage": master_info.get("leverage", 100.0),
            "accounts": accounts_detail,
        }

    async def close_position(self, ticket: int, lots: Optional[float] = None) -> dict:
        """Close position on master account."""
        master = self._ensure_master()
        return await master.close_position(ticket, lots)

    async def close_all_positions(self, comment: str = "KillSwitch") -> dict:
        """
        Emergency kill-switch: Concurrently closes all positions on master and ALL slaves.
        """
        master = self._ensure_master()
        tasks = [master.close_all_positions(comment)]
        for slave in self.slaves.values():
            tasks.append(slave.close_all_positions(comment))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        total_closed = 0
        total_failed = 0
        all_errors = []

        for r in results:
            if isinstance(r, dict):
                total_closed += r.get("closed", 0)
                total_failed += r.get("failed", 0)
                all_errors.extend(r.get("errors", []))
            elif isinstance(r, Exception):
                total_failed += 1
                all_errors.append(str(r))

        return {
            "closed": total_closed,
            "failed": total_failed,
            "errors": all_errors,
            "status": "multi_account_kill_switch_completed",
        }
