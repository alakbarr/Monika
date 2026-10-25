"""Comprehensive unit tests achieving 100% coverage across src/monika/application/execution/."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
import json
import sys
import time
import types
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class _FakeExecResult:
    def __init__(self, val: object = None, rows: list[object] | None = None) -> None:
        self._val = val
        self._rows = rows or []

    def scalar_one_or_none(self) -> object:
        return self._val

    def scalar(self) -> object:
        return self._val

    def scalars(self) -> _FakeExecResult:
        return self

    def all(self) -> list[object]:
        return self._rows


class _FakeSession:
    def __init__(
        self,
        *,
        scalar_vals: list[object] | None = None,
        rows_list: list[list[object]] | None = None,
        fail_execute: bool = False,
        fail_flush: bool = False,
    ) -> None:
        self.scalar_vals = list(scalar_vals or [])
        self.rows_list = list(rows_list or [])
        self.fail_execute = fail_execute
        self.fail_flush = fail_flush
        self.added: list[object] = []

    async def execute(self, *_a: object, **_k: object) -> _FakeExecResult:
        if self.fail_execute:
            raise RuntimeError("fake session execute error")
        val = self.scalar_vals.pop(0) if self.scalar_vals else None
        if isinstance(val, Exception):
            raise val
        rows = self.rows_list.pop(0) if self.rows_list else []
        return _FakeExecResult(val=val, rows=rows)

    async def get(self, _model: object, _ident: object) -> object:
        return self.scalar_vals.pop(0) if self.scalar_vals else None

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def add_all(self, objs: list[object]) -> None:
        self.added.extend(objs)

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None

    async def flush(self) -> None:
        if self.fail_flush:
            raise RuntimeError("fake session flush error")
        return None

    def get_bind(self) -> MagicMock:
        bind = MagicMock()
        bind.dialect.name = "sqlite"
        return bind

    @asynccontextmanager
    async def begin_nested(self) -> AsyncIterator[_FakeSession]:
        yield self


def _make_cm_session(sess: _FakeSession) -> object:
    @asynccontextmanager
    async def _cm() -> AsyncIterator[_FakeSession]:
        yield sess

    return _cm()


@pytest.mark.asyncio
async def test_broker_registry_effect_gate_exec_service_health_check_full_coverage() -> None:
    from monika.application.execution.broker_registry import (
        BrokerAdapterRegistry,
        _register_builtins,
        get_active_broker,
        get_broker,
    )
    from monika.application.execution.effect_gate import EffectGate, EffectGateResult
    from monika.application.execution.execution_service import ExecutionService
    from monika.application.execution.health_check import FlakeTolerantHealthChecker

    # 1. BrokerAdapterRegistry & builtins
    saved_adapters = dict(BrokerAdapterRegistry._adapters)
    saved_factories = dict(BrokerAdapterRegistry._adapter_factories)
    saved_active = BrokerAdapterRegistry._active_name
    try:
        BrokerAdapterRegistry.reset()
        assert BrokerAdapterRegistry._active_name == "simulated"
        _register_builtins()

        assert BrokerAdapterRegistry.get("nonexistent_broker") is None
        BrokerAdapterRegistry._active_name = "nonexistent_broker"
        fallback = get_active_broker()
        assert fallback is not None

        with (
            patch("monika.infrastructure.brokers.broker_adapter.MT5LiveAdapter", return_value="mt5_live_inst"),
            patch("monika.infrastructure.brokers.broker_adapter.MT5RemoteGatewayAdapter", return_value="remote_inst"),
            patch("monika.infrastructure.brokers.ibkr_adapter.IBKRBrokerAdapter", return_value="ibkr_inst"),
        ):
            BrokerAdapterRegistry._adapters.clear()
            assert get_broker("mt5_live") == "mt5_live_inst"
            assert get_broker("remote_gateway") == "remote_inst"
            assert get_broker("ibkr") == "ibkr_inst"

        BrokerAdapterRegistry._adapters.clear()
        BrokerAdapterRegistry.register("mt5_live", lambda **_kw: None)
        multi = get_broker("multi_account")
        assert multi is not None
    finally:
        BrokerAdapterRegistry._adapters = saved_adapters
        BrokerAdapterRegistry._adapter_factories = saved_factories
        BrokerAdapterRegistry._active_name = saved_active

    # 2. EffectGateResult & EffectGate
    eg_res = EffectGateResult(success=True, result="ok", error=None, aborted=False)
    assert "EffectGateResult" in repr(eg_res)
    eg = EffectGate()
    assert eg.abort_reason == ""

    # 3. ExecutionService paper_trading config variants
    for s_cfg in (
        {"trading": {"paper_trading": {"enabled": True}}},
        {"trading": {"paper_trading": False}},
        {"trading": {"paper_trading": "invalid"}},
        {"paper_trading": True},
        {"paper_trading": "invalid"},
    ):
        svc = ExecutionService(settings=s_cfg, mt5_client=MagicMock())
        assert isinstance(svc.dry_run, bool)

    # 4. FlakeTolerantHealthChecker ping() and connected attribute branches
    class _PingMt5:
        async def ping(self) -> bool:
            return True

    class _ConnAttrMt5:
        connected = True

    hc_ping = FlakeTolerantHealthChecker(mt5_client=_PingMt5())
    assert await hc_ping.is_healthy(force_check=True) is True
    hc_attr = FlakeTolerantHealthChecker(mt5_client=_ConnAttrMt5())
    assert await hc_attr.is_healthy(force_check=True) is True


@pytest.mark.asyncio
async def test_multi_account_adapter_full_coverage() -> None:
    from monika.application.execution.service.multi_account_adapter import MultiAccountBrokerAdapter
    from monika.infrastructure.brokers.broker_adapter import BrokerAdapter

    adapter_no_master = MultiAccountBrokerAdapter(master_adapter=None)
    with pytest.raises(RuntimeError, match="No master broker adapter"):
        adapter_no_master._ensure_master()

    class _MockAdapter(BrokerAdapter):
        def __init__(
            self,
            *,
            submit_ok: bool = True,
            raise_err: bool = False,
            equity: float = 10000.0,
        ) -> None:
            self.submit_ok = submit_ok
            self.raise_err = raise_err
            self.equity = equity

        async def get_tick(self, symbol: str) -> dict[str, object]:
            return {"symbol": symbol, "bid": 1.1000, "ask": 1.1002}

        async def submit_order(self, order: object, **_kwargs: object) -> dict[str, object]:
            if self.raise_err:
                raise RuntimeError("slave submit boom")
            if not self.submit_ok:
                return {"success": False, "error": "rejected"}
            return {"success": True, "ticket": 101, "price": 1.1000}

        async def cancel_order(self, client_order_id: str) -> bool:
            return True

        async def get_orders(self, symbol: str | None = None) -> list[dict[str, object]]:
            if self.raise_err:
                raise RuntimeError("orders err")
            return [{"ticket": 1, "symbol": symbol or "EURUSD"}]

        async def get_positions(self) -> list[dict[str, object]]:
            if self.raise_err:
                raise RuntimeError("pos err")
            return [{"ticket": 55, "symbol": "EURUSD"}]

        async def get_account_info(self) -> dict[str, object]:
            if self.raise_err:
                raise RuntimeError("info err")
            return {"balance": self.equity, "equity": self.equity, "margin": 100.0, "free_margin": self.equity - 100.0}

        async def close_position(self, ticket: int, lots: float | None = None) -> dict[str, object]:
            if self.raise_err:
                raise RuntimeError("close err")
            return {"success": True, "ticket": ticket, "lots": lots}

        async def close_all_positions(self, comment: str = "KillSwitch") -> dict[str, object]:
            if self.raise_err:
                raise RuntimeError("close all err")
            return {"closed": 1, "failed": 0, "errors": []}

    master_fail = _MockAdapter(submit_ok=False)
    ma_fail = MultiAccountBrokerAdapter(master_adapter=master_fail)
    assert (await ma_fail.submit_order({"symbol": "EURUSD", "side": "buy", "volume": 0.1}))["success"] is False

    master_ok = _MockAdapter(submit_ok=True, equity=10000.0)
    ma = MultiAccountBrokerAdapter(master_adapter=master_ok)
    assert (await ma.get_tick("EURUSD"))["symbol"] == "EURUSD"

    # No slaves
    res_no_slaves = await ma.submit_order({"symbol": "EURUSD", "side": "buy", "volume": 0.1})
    assert res_no_slaves["success"] is True and "slaves_replicated" not in res_no_slaves

    # Add slaves (one good, one failing) & remove slave
    slave_ok = _MockAdapter(submit_ok=True, equity=20000.0)
    slave_err = _MockAdapter(raise_err=True)
    ma.add_slave("s_temp", slave_ok)
    ma.remove_slave("s_temp")
    ma.remove_slave("s_nonexistent")
    ma.add_slave("s_ok", slave_ok)
    ma.add_slave("s_err", slave_err)

    res_rep = await ma.submit_order({"symbol": "EURUSD", "side": "buy", "volume": 0.1})
    assert res_rep["slaves_replicated"]["s_ok"]["success"] is True
    assert res_rep["slaves_replicated"]["s_err"]["success"] is False

    assert await ma.cancel_order("cid_1") is True
    orders = await ma.get_orders("EURUSD")
    assert len(orders) == 2
    positions = await ma.get_positions()
    assert len(positions) == 2
    acc_info = await ma.get_account_info()
    assert acc_info["is_multi_account"] is True and "error" in acc_info["accounts"]["slave_s_err"]

    close_res = await ma.close_position(101, lots=0.1)
    assert close_res["success"] is True

    close_all_res = await ma.close_all_positions()
    assert close_all_res["closed"] == 2 and close_all_res["failed"] == 1


@pytest.mark.asyncio
async def test_order_executor_lifecycle_reconciliation_risk_eval_trade_confirm_full_coverage() -> None:
    import monika.application.execution.execution_service as es_mod
    from monika.application.execution.execution_service import ExecutionService
    import monika.application.execution.service.emergency_manager as em_mod
    import monika.application.execution.service.order_executor as oe_mod
    from monika.application.execution.service.order_executor import AnalysisPrunerState
    from monika.application.execution.service.order_lifecycle_service import OrderLifecycleService
    import monika.application.execution.service.position_synchronizer as ps_mod
    from monika.application.execution.service.reconciliation import ReconciliationHelper
    import monika.application.execution.service.risk_evaluator as re_mod
    from monika.application.execution.service.trade_confirm import TradeConfirmManager
    from monika.domain.ports import UnitOfWorkPort
    from monika.domain.risk.approval_hub import ApprovalHub

    # 1. get_session & transactional_advisory_lock in order_executor, emergency_manager, position_synchronizer, risk_evaluator
    for mod in (oe_mod, em_mod, ps_mod, re_mod):
        with (
            patch.object(es_mod, "get_session", lambda: "es_sess", create=True),
            patch.object(es_mod, "transactional_advisory_lock", lambda *_a, **_k: "es_lock", create=True),
        ):
            assert mod.get_session() == "es_sess"
            assert mod.transactional_advisory_lock("k") == "es_lock"

        with (
            patch.dict(sys.modules, {"monika.application.execution.execution_service": None}),
            patch("monika.infrastructure.database.db.get_session", return_value="real_sess"),
            patch("monika.infrastructure.database.db.transactional_advisory_lock", return_value="real_lock"),
        ):
            assert mod.get_session() == "real_sess"
            assert mod.transactional_advisory_lock("k") == "real_lock"

    # AnalysisPrunerState
    saved_lct = getattr(oe_mod, "_LAST_CLEANUP_TIME", None)
    try:
        if hasattr(oe_mod, "_LAST_CLEANUP_TIME"):
            delattr(oe_mod, "_LAST_CLEANUP_TIME")
        assert isinstance(AnalysisPrunerState.get_last_cleanup_time(), float)
        AnalysisPrunerState.reset()
        assert hasattr(oe_mod, "_LAST_CLEANUP_TIME")
    finally:
        if saved_lct is not None:
            setattr(oe_mod, "_LAST_CLEANUP_TIME", saved_lct)

    # 2. OrderLifecycleService
    mock_order = MagicMock(
        id=1,
        client_order_id="cid_1",
        symbol="EURUSD",
        status="CREATED",
        broker_order_id="100",
        filled_qty=0.1,
        avg_fill_price=1.1000,
    )
    sess_flush_fail = MagicMock(add=MagicMock(), flush=AsyncMock(side_effect=RuntimeError("flush err")))
    with pytest.raises(RuntimeError, match="flush err"):
        await OrderLifecycleService.transition_order_state(sess_flush_fail, mock_order, "SUBMITTED")

    sess_ok = MagicMock(add=MagicMock(), flush=AsyncMock())
    with (
        patch(
            "monika.infrastructure.database.event_store.TradingEventStore.emit",
            AsyncMock(side_effect=RuntimeError("es err")),
        ),
        patch(
            "monika.application.execution.service.order_lifecycle_service.get_event_bus",
            side_effect=RuntimeError("eb err"),
        ),
    ):
        evt = await OrderLifecycleService.transition_order_state(
            sess_ok, mock_order, "FILLED", reason="ok", ticket=100, executed_price=1.1000
        )
        assert evt is not None

    # 3. ReconciliationHelper
    class _FakeUoW(UnitOfWorkPort):
        def __init__(self) -> None:
            self._positions = MagicMock(
                get_recent_executed_analysis_ids=AsyncMock(return_value=[10]),
                get_recent_order_executed_analysis_ids=AsyncMock(return_value=[12]),
            )
            self._trade_proposals = MagicMock(
                get_recent_executed_analysis_ids=AsyncMock(return_value=[11]),
            )

        @property
        def positions(self) -> MagicMock:
            return self._positions

        @property
        def trade_proposals(self) -> MagicMock:
            return self._trade_proposals

        async def __aenter__(self) -> _FakeUoW:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def commit(self) -> None:
            return None

        async def rollback(self) -> None:
            return None

        async def flush(self) -> None:
            return None

    cache_dict: dict[int, float] = {}
    restored = await ReconciliationHelper.restore_executed_ids_from_db(_FakeUoW(), cache_dict)
    assert restored == 3 and {10, 11, 12}.issubset(cache_dict.keys())

    uow_err = _FakeUoW()
    uow_err.positions.get_recent_executed_analysis_ids = AsyncMock(side_effect=RuntimeError("repo err"))
    assert await ReconciliationHelper.restore_executed_ids_from_db(uow_err, {}) == 0

    # 4. RiskEvaluatorMixin (via ExecutionService)
    exec_obj = ExecutionService(
        settings={"paper_trading": {"enabled": True, "initial_balance": 10000.0}},
        mt5_client=MagicMock(),
    )
    exec_obj.broker_adapter = None

    async def _coro_five() -> int:
        return 5

    sess_coro_cnt = MagicMock(execute=AsyncMock(return_value=types.SimpleNamespace(scalar=lambda: _coro_five())))
    assert await exec_obj._count_open_positions(sess_coro_cnt, symbol="EURUSD") == 5

    sess_cnt_err = MagicMock(execute=AsyncMock(side_effect=RuntimeError("cnt err")))
    with pytest.raises(RuntimeError, match="cnt err"):
        await exec_obj._count_open_positions(sess_cnt_err)

    exec_obj.settings["trading"] = {"risk": {"dynamic_risk_scaling": True}}
    with patch(
        "monika.core.analytics.paper_tracker.PaperTracker.get_statistics",
        AsyncMock(return_value={"by_symbol": {"EURUSD": {"trades": 1}}}),
    ):
        assert await exec_obj._get_dynamic_risk_percent(MagicMock(), "EURUSD", 1.0) == 1.0

    with patch(
        "monika.core.analytics.paper_tracker.PaperTracker.get_statistics",
        AsyncMock(side_effect=RuntimeError("perf err")),
    ):
        assert await exec_obj._get_dynamic_risk_percent(MagicMock(), "EURUSD", 1.0) == 1.0

    # _get_current_price branches
    exec_obj.mt5 = MagicMock(
        get_current_price=AsyncMock(return_value={"bid": 1.1000, "ask": 1.1002, "fetched_at": time.time() - 300.0})
    )
    _, is_stale_f, _ = await exec_obj._get_current_price("EURUSD", "buy")
    assert is_stale_f is True

    exec_obj.mt5 = MagicMock(
        get_current_price=AsyncMock(return_value={"bid": 1.1000, "ask": 1.1002, "time": datetime(2020, 1, 1, 12, 0, 0)})
    )
    _, is_stale_t, _ = await exec_obj._get_current_price("EURUSD", "buy")
    assert is_stale_t is True

    exec_obj.mt5 = MagicMock(get_current_price=AsyncMock(side_effect=RuntimeError("mt5 down")))
    exec_obj.dry_run = False
    assert (await exec_obj._get_current_price("EURUSD", "buy"))[0] == 0.0

    exec_obj.dry_run = True

    @asynccontextmanager
    async def _bar_sess_ctx(bar_obj: object) -> AsyncIterator[object]:
        yield MagicMock(execute=AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: bar_obj)))

    with patch.object(
        re_mod, "get_session", lambda: _bar_sess_ctx(MagicMock(close=1.1234, timestamp=datetime(2026, 1, 1, 0, 0, 0)))
    ):
        assert (await exec_obj._get_current_price("EURUSD", "buy"))[0] == 1.1234

    with patch.object(re_mod, "get_session", lambda: _bar_sess_ctx(None)):
        assert (await exec_obj._get_current_price("EURUSD", "buy"))[0] == 0.0

    # _get_equity branches
    async def _coro_bad_eq() -> str:
        return "not_a_float"

    async def _coro_info() -> dict[str, object]:
        return {"equity": _coro_bad_eq()}

    exec_obj.mt5 = MagicMock(get_account_info=AsyncMock(return_value=_coro_info()))
    assert await exec_obj._get_equity() is None

    exec_obj.mt5 = MagicMock(get_account_info=AsyncMock(side_effect=RuntimeError("eq err")))
    assert await exec_obj._get_equity() is None

    # 5. TradeConfirmManager
    orig_tcm = TradeConfirmManager._instance
    try:
        TradeConfirmManager._instance = None
        tcm = TradeConfirmManager.get_instance()
        assert isinstance(tcm, TradeConfirmManager)
    finally:
        TradeConfirmManager._instance = orig_tcm

    tcm = TradeConfirmManager()
    with patch.object(ApprovalHub, "get_instance", side_effect=RuntimeError("hub err")):
        act1 = tcm.create_pending_action("open", "desc", {"k": 1}, ttl_seconds=60)
        assert tcm.get_action(act1.confirm_id) is act1

    assert tcm.get_action("nonexistent_id") is None

    # Resolved via ApprovalHub
    act_res = tcm.create_pending_action("open", "desc2", {}, ttl_seconds=60)
    ApprovalHub.get_instance()._requests[act_res.confirm_id].status = "approved"
    assert tcm.get_action(act_res.confirm_id) is None

    # Expired in get_action
    act_exp = tcm.create_pending_action("open", "desc_exp", {}, ttl_seconds=10)
    act_exp.created_at = time.time() - 100.0
    assert tcm.get_action(act_exp.confirm_id) is None

    act_exp2 = tcm.create_pending_action("open", "desc_exp2", {}, ttl_seconds=10)
    act_exp2.created_at = time.time() - 100.0
    with patch.object(ApprovalHub, "get_instance", side_effect=RuntimeError("hub err")):
        assert tcm.get_action(act_exp2.confirm_id) is None

    # execute_confirmed_action: expired (normal & hub error), pre_check false & error, handler ok (hub error), handler error (normal & hub error)
    act_e1 = tcm.create_pending_action("open", "e1", {}, ttl_seconds=10)
    act_e1.created_at = time.time() - 100.0
    assert (await tcm.execute_confirmed_action(act_e1.confirm_id, AsyncMock()))[0] is False

    act_e2 = tcm.create_pending_action("open", "e2", {}, ttl_seconds=10)
    act_e2.created_at = time.time() - 100.0
    with patch.object(ApprovalHub, "get_instance", side_effect=RuntimeError("hub err")):
        assert (await tcm.execute_confirmed_action(act_e2.confirm_id, AsyncMock()))[0] is False

    act_pc1 = tcm.create_pending_action("open", "pc1", {}, ttl_seconds=60)
    assert (await tcm.execute_confirmed_action(act_pc1.confirm_id, AsyncMock(), pre_check=lambda _p: False))[0] is False

    act_pc2 = tcm.create_pending_action("open", "pc2", {}, ttl_seconds=60)
    assert (
        await tcm.execute_confirmed_action(
            act_pc2.confirm_id, AsyncMock(), pre_check=lambda _p: (_ for _ in ()).throw(RuntimeError("pc boom"))
        )
    )[0] is False

    act_ok_hub_err = tcm.create_pending_action("open", "ok_he", {}, ttl_seconds=60)
    with patch.object(ApprovalHub, "get_instance", side_effect=RuntimeError("hub err")):
        assert (await tcm.execute_confirmed_action(act_ok_hub_err.confirm_id, AsyncMock(return_value="done")))[
            0
        ] is True

    act_fail1 = tcm.create_pending_action("open", "fail1", {}, ttl_seconds=60)
    assert (await tcm.execute_confirmed_action(act_fail1.confirm_id, AsyncMock(side_effect=RuntimeError("exec boom"))))[
        0
    ] is False

    act_fail2 = tcm.create_pending_action("open", "fail2", {}, ttl_seconds=60)
    with patch.object(ApprovalHub, "get_instance", side_effect=RuntimeError("hub err")):
        assert (
            await tcm.execute_confirmed_action(act_fail2.confirm_id, AsyncMock(side_effect=RuntimeError("exec boom")))
        )[0] is False

    # cancel_action (hub err & missing) & list_pending (valid + expired)
    act_c1 = tcm.create_pending_action("open", "c1", {}, ttl_seconds=60)
    with patch.object(ApprovalHub, "get_instance", side_effect=RuntimeError("hub err")):
        assert tcm.cancel_action(act_c1.confirm_id) is True
    assert tcm.cancel_action("missing_confirm_id") is False

    act_valid = tcm.create_pending_action("open", "v1", {}, ttl_seconds=60)
    act_old = tcm.create_pending_action("open", "old1", {}, ttl_seconds=10)
    act_old.created_at = time.time() - 100.0
    pending_map = tcm.list_pending()
    assert act_valid.confirm_id in pending_map and act_old.confirm_id not in pending_map


@pytest.mark.asyncio
async def test_self_healing_executor_full_coverage() -> None:
    from monika.application.execution.service.self_healing_executor import MT5SelfHealingExecutor

    adapter = MagicMock()
    healer = MT5SelfHealingExecutor(broker_adapter=adapter)

    # Already successful
    assert (await healer.heal_and_reexecute(MagicMock(), {"success": True}, sl=1.0950, tp=1.1050, comment="c1"))[
        "success"
    ] is True

    # Attempt 1 (10016 invalid stops -> submit fails) -> Attempt 2 (backoff + in-flight position reconciled!)
    adapter.get_positions = AsyncMock(
        side_effect=[
            [],
            [{"symbol": "EURUSD", "comment": "c1", "ticket": 777, "price_open": 1.1000}],
        ]
    )
    adapter.submit_order = AsyncMock(return_value={"success": False, "retcode": 10016, "error": "invalid stops"})
    order_obj = MagicMock(symbol="EURUSD", comment="c1", client_order_id="cid_1", volume=0.1, requested_price=1.1000)

    with (
        patch.object(healer, "_heal_stops", AsyncMock(return_value=(1.0900, 1.1100))),
        patch("asyncio.sleep", AsyncMock()),
    ):
        res_reconciled = await healer.heal_and_reexecute(
            order_obj,
            {"success": False, "retcode": 10016, "error": "invalid stops"},
            sl=1.0950,
            tp=1.1050,
            comment="c1",
        )
        assert res_reconciled["success"] is True and res_reconciled["ticket"] == 777

    # Retcode 10014 (submit fails) -> Retcode 10004 (reprice succeeds)
    adapter.get_positions = AsyncMock(return_value=[])
    adapter.submit_order = AsyncMock(
        side_effect=[
            {"success": False, "retcode": 10004, "error": "requote"},
            {"success": True, "ticket": 888},
        ]
    )
    with (
        patch.object(healer, "_snap_volume", AsyncMock(return_value=0.10)),
        patch.object(healer, "_check_reprice_tolerance", AsyncMock(return_value=True)),
        patch("asyncio.sleep", AsyncMock()),
    ):
        res_repriced = await healer.heal_and_reexecute(
            order_obj,
            {"success": False, "retcode": 10014, "error": "invalid volume"},
            sl=1.0950,
            tp=1.1050,
            comment="c1",
        )
        assert res_repriced["success"] is True

    # Retcode 10004 (reprice submit fails -> non-recoverable 10019 breaks out)
    adapter.submit_order = AsyncMock(return_value={"success": False, "retcode": 10019, "error": "no money"})
    with (
        patch.object(healer, "_check_reprice_tolerance", AsyncMock(return_value=True)),
        patch("asyncio.sleep", AsyncMock()),
    ):
        res_nonrec = await healer.heal_and_reexecute(
            order_obj, {"success": False, "retcode": 10004, "error": "requote"}, sl=1.0950, tp=1.1050, comment="c1"
        )
        assert res_nonrec["success"] is False

    # Timeout in heal_and_reexecute
    async def _timeout_wait_for(coro: object, *args: object, **kwargs: object) -> object:
        if hasattr(coro, "close"):
            getattr(coro, "close")()
        raise TimeoutError("timed out")

    with patch("asyncio.wait_for", side_effect=_timeout_wait_for):
        res_to = await healer.heal_and_reexecute(
            order_obj, {"success": False, "retcode": 10004}, sl=1.0950, tp=1.1050, comment="c1"
        )
        assert res_to["success"] is False

    # _heal_stops branches: None info/tick, BUY tp<=min_allowed_tp, SELL sl<=min_allowed_sl & tp>=max_allowed_tp, exception
    fake_mt5 = MagicMock()
    fake_mt5.symbol_info.return_value = None
    fake_mt5.symbol_info_tick.return_value = None
    with patch.dict(sys.modules, {"MetaTrader5": fake_mt5}):
        assert await healer._heal_stops("EURUSD", 1.0950, 1.1050, True) is None

    fake_mt5.symbol_info.return_value = MagicMock(point=0.0001, digits=5, trade_stops_level=20, spread=2)
    fake_mt5.symbol_info_tick.return_value = MagicMock(ask=1.1000, bid=1.0998)
    with patch.dict(sys.modules, {"MetaTrader5": fake_mt5}):
        healed_buy = await healer._heal_stops("EURUSD", 1.0999, 1.1001, True)
        assert healed_buy is not None
        healed_sell = await healer._heal_stops("EURUSD", 1.0999, 1.0997, False)
        assert healed_sell is not None

    with patch("asyncio.to_thread", side_effect=RuntimeError("thread err")):
        assert await healer._heal_stops("EURUSD", 1.09, 1.11, True) is None

    # _snap_volume branches: None info, exception
    fake_mt5.symbol_info.return_value = None
    with patch.dict(sys.modules, {"MetaTrader5": fake_mt5}):
        assert await healer._snap_volume("EURUSD", 0.123) is None

    with patch("asyncio.to_thread", side_effect=RuntimeError("snap err")):
        assert await healer._snap_volume("EURUSD", 0.123) is None

    # _check_reprice_tolerance branches: None tick, drift > max_allowed, drift <= max_allowed, exception
    fake_mt5.symbol_info_tick.return_value = None
    with patch("monika.infrastructure.brokers.mt5_compat.get_mt5_module", return_value=fake_mt5):
        assert await healer._check_reprice_tolerance("EURUSD", order_obj, True, atr=0.0050) is False

    fake_mt5.symbol_info_tick.return_value = MagicMock(ask=1.1200, bid=1.1198)
    with patch("monika.infrastructure.brokers.mt5_compat.get_mt5_module", return_value=fake_mt5):
        assert await healer._check_reprice_tolerance("EURUSD", order_obj, True, atr=0.0050) is False

    fake_mt5.symbol_info_tick.return_value = MagicMock(ask=1.1002, bid=1.1000)
    with patch("monika.infrastructure.brokers.mt5_compat.get_mt5_module", return_value=fake_mt5):
        assert await healer._check_reprice_tolerance("EURUSD", order_obj, True, atr=0.0050) is True

    with patch("asyncio.to_thread", side_effect=RuntimeError("reprice err")):
        assert await healer._check_reprice_tolerance("EURUSD", order_obj, True, atr=0.0050) is False


@pytest.mark.asyncio
async def test_emergency_manager_full_coverage() -> None:
    import monika.application.execution.service.emergency_manager as em_mod
    from monika.application.execution.service.emergency_manager import EmergencyManagerMixin

    with patch.dict(sys.modules, {"monika.application.execution.execution_service": None}):
        with (
            patch("monika.infrastructure.database.db.get_session", return_value="real_sess"),
            patch("monika.infrastructure.database.db.transactional_advisory_lock", return_value="real_lock"),
        ):
            assert em_mod.get_session() == "real_sess"
            assert em_mod.transactional_advisory_lock("k") == "real_lock"

    class _DummyEM(EmergencyManagerMixin):
        def __init__(self) -> None:
            self.settings: dict[str, object] = {
                "paper_trading": {"initial_balance": 10000.0},
                "trading": {"mt5": {"magic": 20250101}},
            }
            self.dry_run = True
            self.mt5 = MagicMock(
                close_position=AsyncMock(return_value={"success": True, "profit": 25.0}),
                get_current_price=AsyncMock(return_value={"bid": 1.1050, "ask": 1.1052}),
                cancel_all_pending_orders=AsyncMock(side_effect=RuntimeError("cancel err")),
                close_all_positions=AsyncMock(return_value={"closed": 1, "failed": 0, "total": 1, "errors": []}),
                get_open_positions=AsyncMock(
                    return_value=[{"ticket": 501, "magic": 20250101, "symbol": "EURUSD", "profit": 10.0}]
                ),
            )
            self.broker_adapter = None
            self.gate = MagicMock(
                update_risk_state=AsyncMock(),
                pause_trading=AsyncMock(),
                resume_trading=AsyncMock(),
            )

        async def _get_equity(self) -> object:
            async def _coro() -> str:
                return "not_a_float"

            return _coro()

    em = _DummyEM()
    # Populate 500 ticket locks to trigger cleanup
    em._ticket_locks = {i: asyncio.Lock() for i in range(500)}
    lk = em.get_ticket_lock(999)
    assert len(em._ticket_locks) < 500

    # Lock already locked
    await lk.acquire()
    res_locked = await em.close_position_by_ticket(999)
    assert res_locked["success"] is False
    lk.release()

    # Already closed in DB & Paper position close via close_position_by_ticket
    pos_closed = MagicMock(status="closed", is_paper=False)
    with patch.object(em_mod, "get_session", return_value=_make_cm_session(_FakeSession(scalar_vals=[pos_closed]))):
        res_already = await em.close_position_by_ticket(100)
        assert res_already["already_closed"] is True

    # _close_paper_position branches: _get_current_price, mt5 dict/obj/error, last_bar fallback, partial vs full, paper record sell + OutcomeLinker error
    pos_paper = MagicMock(
        id=1,
        mt5_ticket=101,
        symbol="EURUSD",
        direction="sell",
        status="open",
        is_paper=True,
        volume=1.0,
        entry_price=1.1000,
        analysis_id=77,
    )
    paper_rec = MagicMock(
        analysis_id=77,
        status="open",
        entry_price=1.1000,
        stop_loss=1.1050,
        direction="sell",
        risk_pct=1.0,
        opened_at=datetime.now(UTC) - timedelta(hours=2),
    )
    bar_obj = MagicMock(close=1.0950)

    # 1. Partial close with _get_current_price
    setattr(em, "_get_current_price", AsyncMock(return_value=(1.0960, False, 1.0)))
    await em._close_paper_position(_FakeSession(), pos_paper, "user", "partial", volume=0.4)
    assert pos_paper.volume == 0.6
    delattr(em, "_get_current_price")

    # 2. Full close with mt5 object tick, then error fallback to last_bar, OutcomeLinker error
    em.mt5.get_current_price = AsyncMock(return_value=MagicMock(bid=0.0, ask=0.0))
    sess_paper = _FakeSession(scalar_vals=[bar_obj, paper_rec])
    with patch(
        "monika.application.analysis.memory.outcome_linker.OutcomeLinker.process_closed_position",
        AsyncMock(side_effect=RuntimeError("linker err")),
    ):
        res_p_close = await em._close_paper_position(sess_paper, pos_paper, "user", "manual")
        assert res_p_close["success"] is True

    # 3. Close via close_position_by_ticket when db_pos.is_paper is True
    pos_paper.status = "open"
    with (
        patch.object(em_mod, "get_session", return_value=_make_cm_session(_FakeSession(scalar_vals=[pos_paper]))),
        patch.object(em, "_close_paper_position", AsyncMock(return_value={"success": True})) as mock_cpp,
    ):
        await em.close_position_by_ticket(101, volume=0.2)
        mock_cpp.assert_awaited_once()

    # 4. Live close: broker_adapter pnl->profit mapping, partial & full close, TimeoutError, OutcomeLinker naive timestamps & error, dry_run=False equity
    pos_live = MagicMock(
        id=2,
        mt5_ticket=102,
        symbol="EURUSD",
        status="open",
        is_paper=False,
        volume=1.0,
        pnl=0.0,
        analysis_id=88,
        opened_at=datetime(2026, 5, 1, 10, 0, 0),
        closed_at=datetime(2026, 5, 1, 12, 0, 0),
    )
    em.broker_adapter = MagicMock(close_position=AsyncMock(return_value={"success": True, "pnl": 50.0}))
    with patch.object(
        em_mod, "get_session", side_effect=lambda: _make_cm_session(_FakeSession(scalar_vals=[pos_live]))
    ):
        # Partial close first
        await em.close_position_by_ticket(102, volume=0.3)
        assert pos_live.volume == 0.7
        # Full close with dry_run=False and OutcomeLinker error
        em.dry_run = False
        with patch(
            "monika.application.analysis.memory.outcome_linker.OutcomeLinker.process_closed_position",
            AsyncMock(side_effect=RuntimeError("real linker err")),
        ):
            await em.close_position_by_ticket(102)
            assert pos_live.status == "closed"

    # TimeoutError branch
    em.broker_adapter = MagicMock(close_position=AsyncMock(side_effect=TimeoutError("timeout")))
    with patch.object(em_mod, "get_session", side_effect=lambda: _make_cm_session(_FakeSession(scalar_vals=[None]))):
        res_to = await em.close_position_by_ticket(103)
        assert res_to["success"] is False

    # 5. trigger_circuit_breaker notifier exception
    with (
        patch.object(em_mod, "get_session", return_value=_make_cm_session(_FakeSession())),
        patch.object(
            em_mod, "AgentNotifier", return_value=MagicMock(send_warning=AsyncMock(side_effect=RuntimeError("n")))
        ),
    ):
        cb_res = await em.trigger_circuit_breaker("FlashCrash", 60)
        assert cb_res["success"] is True

    # 6. kill_switch branches: mt5 close_all_positions, TimeoutError, retry sleep, paper trades cleanup & error, SystemConfig add, remaining agent_positions alert error, final notifier error
    em.broker_adapter = None
    em.mt5.sync_positions_from_mt5 = AsyncMock()
    open_paper_1 = MagicMock(
        symbol="EURUSD",
        entry_price=1.1000,
        stop_loss=1.1050,
        direction="sell",
        risk_pct=1.0,
        opened_at=datetime.now(UTC) - timedelta(hours=1),
    )
    open_paper_2 = MagicMock(symbol="EURUSD", entry_price=0.0, stop_loss=0.0, direction="buy", opened_at=None)

    ks_sess = _FakeSession(
        scalar_vals=[bar_obj, None, None, None],
        rows_list=[[], [open_paper_1, open_paper_2], []],
    )
    with (
        patch.object(em_mod, "get_session", side_effect=lambda: _make_cm_session(ks_sess)),
        patch.object(em_mod, "safe_commit", AsyncMock()),
        patch("asyncio.sleep", AsyncMock()),
        patch(
            "monika.infrastructure.notifications.telegram_notifier.AgentNotifier.send_critical",
            AsyncMock(side_effect=RuntimeError("crit err")),
        ),
    ):
        await em.kill_switch(reason="test_ks")

    # kill_switch TimeoutError + no mt5/adapter fallback + paper_session error
    em_no_mt5 = _DummyEM()
    em_no_mt5.mt5 = MagicMock(spec=[])
    with (
        patch.object(em_mod, "get_session", side_effect=lambda: _make_cm_session(_FakeSession(fail_execute=True))),
        patch.object(em_mod, "safe_commit", AsyncMock()),
        patch("asyncio.sleep", AsyncMock()),
    ):
        try:
            await em_no_mt5.kill_switch(reason="test_ks2")
        except Exception:
            pass

    # 7. resume_trading without session
    with (
        patch.object(em_mod, "get_session", return_value=_make_cm_session(_FakeSession())),
    ):
        await em.resume_trading(session=None, requested_by="admin")

    # 8. close_positions_batch (live & paper, profit_only, loss_only, symbol filter)
    em.broker_adapter = MagicMock(
        get_open_positions=AsyncMock(
            return_value=[
                {"ticket": None},
                {"ticket": 201, "symbol": "GBPUSD", "profit": 10.0},
                {"ticket": 202, "symbol": "EURUSD", "profit": -5.0},
                {"ticket": 203, "symbol": "EURUSD", "profit": 15.0},
                {"ticket": 204, "symbol": "EURUSD", "profit": 20.0},
            ]
        )
    )
    p_db_1 = MagicMock(id=11, symbol="EURUSD", is_paper=True, pnl=-5.0)
    p_db_2 = MagicMock(id=12, symbol="EURUSD", is_paper=True, pnl=10.0)
    p_db_3 = MagicMock(id=13, symbol="EURUSD", is_paper=True, pnl=15.0)

    with (
        patch.object(
            em,
            "close_position_by_ticket",
            AsyncMock(side_effect=[{"success": True}, {"success": False, "error": "err204"}]),
        ),
        patch.object(
            em,
            "_close_paper_position",
            AsyncMock(side_effect=[{"success": True}, {"success": False}]),
        ),
        patch.object(
            em_mod,
            "get_session",
            side_effect=lambda: _make_cm_session(_FakeSession(rows_list=[[p_db_1, p_db_2, p_db_3]])),
        ),
    ):
        cf_res = await em.close_positions_batch(filter_type="profit_only", symbol="EURUSD")
        assert cf_res["success"] is False

    # Also test loss_only and mt5 fallback in close_positions_batch
    em.broker_adapter = None
    em.mt5.get_open_positions = AsyncMock(return_value=[{"ticket": 205, "symbol": "EURUSD", "profit": 10.0}])
    with (
        patch.object(
            em_mod,
            "get_session",
            side_effect=lambda: _make_cm_session(_FakeSession(rows_list=[[p_db_2]])),
        ),
    ):
        await em.close_positions_batch(filter_type="loss_only", symbol="EURUSD")


@pytest.mark.asyncio
async def test_position_synchronizer_full_coverage() -> None:
    import MetaTrader5 as mt5

    import monika.application.execution.service.position_synchronizer as ps_mod
    from monika.application.execution.service.position_synchronizer import PositionSynchronizerMixin

    # get_session & transactional_advisory_lock with and without execution_service in sys.modules
    fake_es = MagicMock(
        get_session=MagicMock(return_value="es_sess"),
        transactional_advisory_lock=MagicMock(return_value="es_lock"),
    )
    with patch.dict(sys.modules, {"monika.application.execution.execution_service": fake_es}):
        assert ps_mod.get_session() == "es_sess"
        assert ps_mod.transactional_advisory_lock("k") == "es_lock"

    with patch.dict(sys.modules, {"monika.application.execution.execution_service": None}):
        with (
            patch("monika.infrastructure.database.db.get_session", return_value="real_sess"),
            patch("monika.infrastructure.database.db.transactional_advisory_lock", return_value="real_lock"),
        ):
            assert ps_mod.get_session() == "real_sess"
            assert ps_mod.transactional_advisory_lock("k") == "real_lock"

    class _DummyPS(PositionSynchronizerMixin):
        def __init__(self) -> None:
            self.settings: dict[str, object] = {
                "execution": {"mt5_common_dir": "C:/tmp/mt5"},
                "trading": {
                    "auto_execute": True,
                    "risk": {"max_daily_sl_hits": 2, "pause_on_sl_limit": True, "sl_cooldown_hours": 2},
                },
            }
            self.mt5 = MagicMock(
                sync_positions_from_mt5=AsyncMock(return_value={"closed_positions": []}),
                get_open_positions=AsyncMock(return_value=[{"ticket": 301, "volume": 0.0}]),
                get_account_info=AsyncMock(side_effect=RuntimeError("acct err")),
                modify_position=AsyncMock(return_value={"success": True}),
                get_current_price=AsyncMock(return_value={"bid": 1.1050, "ask": 1.0950}),
                get_orders=AsyncMock(return_value=[]),
            )
            self.broker_adapter = None
            self.gate = MagicMock(
                update_risk_state=AsyncMock(side_effect=RuntimeError("gate update err")),
                pause_trading=AsyncMock(),
            )
            self.sizer = MagicMock(
                _get_instrument_spec=MagicMock(return_value=MagicMock(contract_size=100000.0)),
            )
            self._closing_tickets: set[int] = set()

        def get_ticket_lock(self, _ticket: int) -> asyncio.Lock:
            return asyncio.Lock()

        async def _transition_order_state(self, *_a: object, **_k: object) -> None:
            return None

    ps = _DummyPS()
    # 1. sync_positions_from_mt5 with and without session
    await ps.sync_positions_from_mt5(session=_FakeSession())
    with patch.object(ps, "sync_positions", AsyncMock(return_value={"ok": True})):
        await ps.sync_positions_from_mt5(session=None)

    # 2. sync_positions full flow: partial close volume update, closed_positions (SL, TP, trailing, breakeven, partial, other), OutcomeLinker bg task, TradeTrajectoryLogger, HeartbeatManager stale alert
    now = datetime.now(UTC)
    pos_sl = MagicMock(
        id=1,
        mt5_ticket=301,
        symbol="EURUSD",
        direction="buy",
        volume=0.1,
        entry_price=1.1000,
        sl=1.0950,
        tp=1.1100,
        pnl=-50.0,
        opened_at=now - timedelta(hours=2),
        closed_at=now,
        _mt5_close_reason=mt5.DEAL_REASON_SL,
        _mt5_exit_price=None,
        comment="",
    )
    pos_tp = MagicMock(
        id=2,
        mt5_ticket=302,
        symbol="EURUSD",
        direction="sell",
        volume=0.1,
        entry_price=1.1000,
        sl=1.1050,
        tp=1.0900,
        pnl=100.0,
        opened_at=now - timedelta(hours=1),
        closed_at=now,
        _mt5_close_reason=mt5.DEAL_REASON_TP,
        _mt5_exit_price=1.0900,
        comment="",
    )
    pos_trail = MagicMock(
        id=3,
        mt5_ticket=303,
        symbol="EURUSD",
        direction="buy",
        volume=0.1,
        entry_price=1.1000,
        sl=1.1010,
        tp=1.1100,
        pnl=10.0,
        opened_at=None,
        closed_at=None,
        _mt5_close_reason=999,
        _mt5_exit_price=1.1010,
        comment="trailing_sl",
    )
    pos_be = MagicMock(
        id=4,
        mt5_ticket=304,
        symbol="EURUSD",
        direction="buy",
        volume=0.1,
        entry_price=1.1000,
        sl=1.1000,
        tp=1.1100,
        pnl=0.0,
        opened_at=None,
        closed_at=None,
        _mt5_close_reason=999,
        _mt5_exit_price=1.1000,
        comment="breakeven",
    )
    pos_part = MagicMock(
        id=5,
        mt5_ticket=305,
        symbol="EURUSD",
        direction="buy",
        volume=0.1,
        entry_price=1.1000,
        sl=1.0950,
        tp=1.1100,
        pnl=20.0,
        opened_at=None,
        closed_at=None,
        _mt5_close_reason=999,
        _mt5_exit_price=1.1020,
        comment="partial",
    )
    pos_other = MagicMock(
        id=6,
        mt5_ticket=306,
        symbol="EURUSD",
        direction="buy",
        volume=0.1,
        entry_price=1.1000,
        sl=1.0950,
        tp=1.1100,
        pnl=5.0,
        opened_at=None,
        closed_at=None,
        _mt5_close_reason=999,
        _mt5_exit_price=1.1005,
        comment="manual",
    )

    ps.mt5.sync_positions_from_mt5 = AsyncMock(
        return_value={"closed_positions": [pos_sl, pos_tp, pos_trail, pos_be, pos_part, pos_other]}
    )
    db_open_pos = MagicMock(mt5_ticket=301, volume=0.5)
    rel_analysis = MagicMock(id=55, confidence=0.8)

    sync_sess = _FakeSession(scalar_vals=[rel_analysis] * 10)
    with (
        patch.object(ps_mod, "get_session", side_effect=lambda: _make_cm_session(sync_sess)),
        patch(
            "monika.infrastructure.database.repositories.position_repository.PositionRepository",
            return_value=MagicMock(
                get_open_positions=AsyncMock(return_value=[db_open_pos]),
                update_volume=AsyncMock(),
            ),
        ),
        patch.object(ps, "_handle_stop_loss_hit", AsyncMock()),
        patch(
            "monika.application.analysis.memory.outcome_linker.OutcomeLinker.process_closed_position",
            AsyncMock(side_effect=RuntimeError("bg linker err")),
        ),
        patch(
            "monika.application.benchmark.trade_trajectory_logger.TradeTrajectoryLogger.update_trajectory_outcome",
            side_effect=RuntimeError("traj err"),
        ),
        patch(
            "monika.infrastructure.brokers.ea_bridge.heartbeat_writer.HeartbeatManager.check_ea_alive",
            return_value=(False, 120),
        ),
        patch(
            "monika.infrastructure.notifications.telegram_notifier.AgentNotifier.send_critical",
            AsyncMock(side_effect=RuntimeError("alert err")),
        ),
    ):
        await ps.sync_positions()
        await asyncio.sleep(0)

    # Also test PositionRepository exception, TradeOutcome exception, HeartbeatManager exception in sync_positions
    ps.mt5.sync_positions_from_mt5 = AsyncMock(return_value={"closed_positions": [pos_other]})
    with (
        patch.object(ps_mod, "get_session", side_effect=lambda: _make_cm_session(_FakeSession(fail_execute=True))),
        patch(
            "monika.infrastructure.database.repositories.position_repository.PositionRepository",
            side_effect=RuntimeError("repo err"),
        ),
        patch(
            "monika.infrastructure.brokers.ea_bridge.heartbeat_writer.HeartbeatManager",
            side_effect=RuntimeError("hb err"),
        ),
    ):
        await ps.sync_positions()

    # 3. _handle_stop_loss_hit: today_sl_hits >= max_daily_sl and notifier error
    with patch(
        "monika.infrastructure.notifications.telegram_notifier.AgentNotifier.send_warning",
        AsyncMock(side_effect=RuntimeError("sl notif err")),
    ):
        await ps._handle_stop_loss_hit(_FakeSession(scalar_vals=[3]), pos_sl)

    # 4. modify_position_sl_tp: closing_tickets pre-lock & in-lock, closed in DB, paper position update, live success & failure
    ps._closing_tickets.add(401)
    assert (await ps.modify_position_sl_tp(401, sl=1.09))["success"] is False
    ps._closing_tickets.clear()

    class _LockAddsTicket:
        async def __aenter__(self) -> None:
            ps._closing_tickets.add(402)

        async def __aexit__(self, *_a: object) -> None:
            ps._closing_tickets.discard(402)

    with patch.object(ps, "get_ticket_lock", return_value=_LockAddsTicket()):
        assert (await ps.modify_position_sl_tp(402, sl=1.09))["success"] is False

    # DB closed & paper position in modify_position_sl_tp
    with patch.object(
        ps_mod,
        "get_session",
        return_value=_make_cm_session(_FakeSession(scalar_vals=[MagicMock(status="closed", is_paper=False)])),
    ):
        assert (await ps.modify_position_sl_tp(403, sl=1.09))["success"] is False

    paper_db_pos = MagicMock(status="open", is_paper=True, analysis_id=99, sl=1.08, tp=1.12)
    with (
        patch.object(ps_mod, "get_session", return_value=_make_cm_session(_FakeSession(scalar_vals=[paper_db_pos]))),
        patch("monika.core.analytics.paper_tracker.PaperTracker.update_paper_trade_sl", AsyncMock()),
    ):
        res_mod_p = await ps.modify_position_sl_tp(404, sl=1.09, tp=1.13)
        assert res_mod_p["paper"] is True

    # Live modify success & failure
    live_db_pos = MagicMock(status="open", is_paper=False, symbol="EURUSD", sl=1.08, tp=1.12)
    with patch.object(
        ps_mod,
        "get_session",
        side_effect=lambda: _make_cm_session(_FakeSession(scalar_vals=[live_db_pos, live_db_pos])),
    ):
        ps.mt5.modify_position = AsyncMock(return_value={"success": True})
        assert (await ps.modify_position_sl_tp(405, sl=1.09, tp=1.13))["success"] is True
        ps.mt5.modify_position = AsyncMock(return_value={"success": False, "error": "mod err"})
        assert (await ps.modify_position_sl_tp(405, sl=1.09, tp=1.13))["success"] is False

    # 5. apply_immediate_breakeven: empty positions, and mixed positions (not in profit, buy already BE, sell already BE, paper update, live success, live failure)
    with patch.object(ps_mod, "get_session", return_value=_make_cm_session(_FakeSession(rows_list=[[]]))):
        res_be_empty = await ps.apply_immediate_breakeven(symbol="EURUSD", ticket=500)
        assert res_be_empty["updated_count"] == 0

    p_not_prof = MagicMock(
        id=1, mt5_ticket=501, symbol="EURUSD", direction="buy", entry_price=1.2000, sl=1.1900, tp=1.2200, is_paper=False
    )
    p_buy_be = MagicMock(
        id=2, mt5_ticket=502, symbol="EURUSD", direction="buy", entry_price=1.1000, sl=1.1000, tp=1.1200, is_paper=False
    )
    p_sell_be = MagicMock(
        id=3,
        mt5_ticket=503,
        symbol="EURUSD",
        direction="sell",
        entry_price=1.1000,
        sl=1.1000,
        tp=1.0800,
        is_paper=False,
    )
    p_paper_be = MagicMock(
        id=4, mt5_ticket=504, symbol="EURUSD", direction="buy", entry_price=1.1000, sl=1.0900, tp=1.1200, is_paper=True
    )
    p_live_ok = MagicMock(
        id=5,
        mt5_ticket=505,
        symbol="EURUSD",
        direction="sell",
        entry_price=1.1000,
        sl=1.1100,
        tp=1.0800,
        is_paper=False,
    )
    p_live_fail = MagicMock(
        id=6, mt5_ticket=506, symbol="EURUSD", direction="buy", entry_price=1.1000, sl=1.0900, tp=1.1200, is_paper=False
    )

    ps.mt5.get_current_price = AsyncMock(
        side_effect=[
            RuntimeError("quote err"),
            {"bid": 1.1050, "ask": 1.0950},
            {"bid": 1.1050, "ask": 1.0950},
            {"bid": 1.1050, "ask": 1.0950},
            {"bid": 1.1050, "ask": 1.0950},
            {"bid": 1.1050, "ask": 1.0950},
        ]
    )
    ps.mt5.modify_position = AsyncMock(side_effect=[{"success": True}, {"success": False, "error": "be err"}])
    with patch.object(
        ps_mod,
        "get_session",
        return_value=_make_cm_session(
            _FakeSession(rows_list=[[p_not_prof, p_buy_be, p_sell_be, p_paper_be, p_live_ok, p_live_fail]])
        ),
    ):
        res_be_all = await ps.apply_immediate_breakeven(only_profit=True)
        assert res_be_all["updated_count"] == 2

    # 6. reconcile_inflight_orders: mt5 fallback, fetch error abort, params_json parsing, flush error, notifier error
    inflight_matched = MagicMock(
        id=10,
        client_order_id="cid_match",
        mt5_ticket=601,
        symbol="EURUSD",
        direction="buy",
        order_type="market",
        requested_volume=0.1,
        requested_price=1.1000,
        stop_loss_price=None,
        take_profit_price=None,
        sl=None,
        tp=None,
        params_json='{"sl": 1.0950, "tp": 1.1100}',
        analysis_id=1,
    )
    inflight_unmatched = MagicMock(
        id=11,
        client_order_id="cid_unmatch",
        mt5_ticket=699,
        symbol="GBPUSD",
        direction="buy",
        order_type="market",
        requested_volume=0.1,
        requested_price=1.2500,
        replay_policy="never",
    )

    # First test broker fetch failure abort
    ps.mt5.get_open_positions = AsyncMock(side_effect=RuntimeError("mt5 down"))
    with patch.object(
        ps_mod, "get_session", return_value=_make_cm_session(_FakeSession(rows_list=[[inflight_matched]]))
    ):
        rec_abort = await ps.reconcile_inflight_orders()
        assert rec_abort["reconciled"] == 0

    # Now test mt5 fallback success with params_json, existing_pos exception, flush exception, and unmatched notifier exception
    ps.mt5.get_open_positions = AsyncMock(
        return_value=[
            {
                "ticket": 601,
                "symbol": "EURUSD",
                "direction": "buy",
                "comment": "cid_match",
                "price_open": 1.1001,
                "volume": 0.1,
            }
        ]
    )
    ps.mt5.get_orders = AsyncMock(return_value=[])
    rec_sess = _FakeSession(rows_list=[[inflight_matched, inflight_unmatched]])
    orig_exec = rec_sess.execute
    exec_count = 0

    async def _rec_exec(*a: object, **k: object) -> _FakeExecResult:
        nonlocal exec_count
        exec_count += 1
        if exec_count == 2:
            raise RuntimeError("pos lookup err")
        return await orig_exec(*a, **k)

    setattr(rec_sess, "execute", _rec_exec)
    rec_sess.fail_flush = True
    with (
        patch.object(ps_mod, "get_session", return_value=_make_cm_session(rec_sess)),
        patch.object(ps_mod.OrderLifecycleService, "transition_order_state", AsyncMock()),
        patch(
            "monika.infrastructure.notifications.telegram_notifier.AgentNotifier.send_critical",
            AsyncMock(side_effect=RuntimeError("crit err")),
        ),
    ):
        rec_ok = await ps.reconcile_inflight_orders()
        assert rec_ok["reconciled"] == 1
        assert rec_ok["interrupted"] == 1


@pytest.mark.asyncio
async def test_analysis_executor_preflight_submission_full_coverage() -> None:
    from monika.application.execution.execution_service import ExecutionService
    from monika.application.execution.service.executors.analysis_preflight import PreflightContext
    import monika.application.execution.service.order_executor as oe_mod
    from monika.application.execution.service.order_executor import ExecutionResult, _EXECUTED_ANALYSIS_IDS
    from monika.domain.risk.position_sizing import SizingResult
    from monika.domain.risk.risk_gate import RiskVerdict

    svc = ExecutionService(
        settings={
            "paper_trading": {
                "enabled": True,
                "initial_balance": 10000.0,
                "min_paper_trades_before_live": 5,
                "min_paper_win_rate_before_live": 0.6,
            },
            "trading": {
                "paper_trading": {"enabled": True},
                "auto_execute": True,
                "auto_execute_min_confidence": 0.7,
                "risk": {"max_concurrent_positions": 5},
            },
            "execution": {
                "max_execute_age_minutes": 15,
                "max_price_staleness_seconds": 60,
                "pre_trade_assertions_enabled": True,
            },
            "data_quality": {"max_brief_age_execution_hours": 12.0},
        },
        mt5_client=MagicMock(
            ensure_connected=AsyncMock(return_value=True),
            get_current_price=AsyncMock(return_value={"bid": 1.1000, "ask": 1.1002}),
            close_position=AsyncMock(return_value={"success": True}),
        ),
        dry_run=True,
    )

    # 1. analysis_executor.py: _restore_executed_ids_from_db, execute_by_analysis_id (not found & found), _log_result (risk_blocked, failed, exception)
    with (
        patch.object(oe_mod, "get_session", return_value=_make_cm_session(_FakeSession())),
        patch(
            "monika.application.execution.service.reconciliation.ReconciliationHelper.restore_executed_ids_from_db",
            AsyncMock(),
        ) as mock_rest,
    ):
        await svc._restore_executed_ids_from_db()
        mock_rest.assert_awaited_once()

    sess_no_an = _FakeSession()
    setattr(sess_no_an, "get", AsyncMock(return_value=None))
    with patch.object(oe_mod, "get_session", return_value=_make_cm_session(sess_no_an)):
        with pytest.raises(ValueError, match="not found"):
            await svc.execute_by_analysis_id(999)

    fake_an = MagicMock(id=1, symbol="EURUSD", decision="buy")
    sess_with_an = _FakeSession()
    setattr(sess_with_an, "get", AsyncMock(return_value=fake_an))
    res_dummy = ExecutionResult(
        symbol="EURUSD",
        analysis_id=1,
        decision="buy",
        sizing=None,
        risk_approved=False,
        risk_checks_passed=[],
        risk_checks_failed=["f"],
        risk_rejection_reasons=["r"],
        executed=False,
        mt5_ticket=None,
        executed_price=None,
        executed_lots=None,
        mt5_error="err",
        position_id=None,
        timestamp=datetime.now(UTC),
        elapsed_ms=10,
    )
    with (
        patch.object(oe_mod, "get_session", return_value=_make_cm_session(sess_with_an)),
        patch.object(svc, "execute_analysis", AsyncMock(return_value=res_dummy)),
    ):
        assert (await svc.execute_by_analysis_id(1)).symbol == "EURUSD"

    with patch("monika.infrastructure.brokers.audit_logger.TradeAuditLogger.log_result", AsyncMock()):
        await svc._log_result(_FakeSession(), res_dummy, 1)
        res_failed = ExecutionResult(**{**res_dummy.__dict__, "risk_approved": True, "executed": False})
        await svc._log_result(_FakeSession(), res_failed, 1)
        with patch("monika.core.telemetry.metrics_exporter.metrics.inc_counter", side_effect=RuntimeError("m err")):
            await svc._log_result(_FakeSession(), res_failed, 1)

    # 2. analysis_preflight.py branches
    sizing_ok = SizingResult(
        symbol="EURUSD",
        direction="BUY",
        entry_price=1.1000,
        stop_loss=1.0950,
        take_profit=1.1100,
        account_equity=10000.0,
        risk_percent=1.0,
        risk_amount_usd=100.0,
        sl_distance_price=0.0050,
        sl_distance_pips=50.0,
        pip_value_per_lot=10.0,
        raw_lots=0.10,
        recommended_lots=0.10,
        rr_ratio=2.0,
        is_valid=True,
    )
    verdict_ok = RiskVerdict(approved=True, symbol="EURUSD", proposed_lots=0.1, checks_passed=["ok"], checks_failed=[])
    verdict_no = RiskVerdict(
        approved=False,
        symbol="EURUSD",
        proposed_lots=0.1,
        checks_passed=[],
        checks_failed=["dd"],
        rejection_reasons=["dd"],
    )

    def _make_analysis(**overrides: object) -> MagicMock:
        defaults: dict[str, object] = {
            "id": 1001,
            "symbol": "EURUSD",
            "decision": "buy",
            "confidence": 0.85,
            "confluence_score": 8,
            "stop_loss": 1.0950,
            "take_profit_1": 1.1100,
            "entry_zone": {"price": 1.1000, "order_type": "market"},
            "generated_at": datetime.now(UTC),
            "rationale": "post-release bullish setup. Strong momentum.",
            "key_evidence": '["ev1"]',
            "confluence_factors_json": None,
            "decision_source": "llm",
            "risk_multiplier": 0.1,
            "priced_in_score": 2.0,
            "specialist_biases_json": '{"tech": "bull"}',
            "debate_verdict": "buy",
            "debate_bull_thesis": "bull",
        }
        defaults.update(overrides)
        return MagicMock(**defaults)

    # 2a. ESTOP active
    with patch("monika.application.agent.estop.is_estop_active", return_value=True):
        r_estop, _ = await svc._validate_analysis_preflight(_FakeSession(), _make_analysis())
        assert r_estop is not None and "estop_active" in r_estop.risk_checks_failed

    # 2b. Live graduation gate: invalid int strings -> paper_trades_count < min_paper_trades, closed/win_rate < min, and exception
    svc.dry_run = False
    svc.settings["paper_trading"] = {
        "enabled": False,
        "min_paper_trades_before_live": 5,
        "min_paper_win_rate_before_live": 0.6,
    }
    svc.settings["trading"] = {
        "paper_trading": {"enabled": False, "min_paper_trades_before_live": 5, "min_paper_win_rate_before_live": 0.6},
        "auto_execute": True,
        "auto_execute_min_confidence": 0.7,
    }
    r_grad1, _ = await svc._validate_analysis_preflight(
        _FakeSession(scalar_vals=["bad_int", "bad_closed", "bad_win"]),
        _make_analysis(generated_at=datetime.now(UTC) - timedelta(hours=2)),
    )
    assert r_grad1 is not None and r_grad1.executed is False

    r_grad2, _ = await svc._validate_analysis_preflight(_FakeSession(scalar_vals=[10, 5, 1]), _make_analysis())
    assert r_grad2 is not None and r_grad2.executed is False

    # Graduation DB error + naive generated_at stale analysis rejection
    naive_old = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=60)
    r_stale, _ = await svc._validate_analysis_preflight(
        _FakeSession(fail_execute=True), _make_analysis(generated_at=naive_old)
    )
    assert r_stale is not None and r_stale.executed is False
    svc.dry_run = True

    # 2c. Brief check: naive brief.generated_at, post_brief_events block, magnitude staleness block & error, brief outer exception
    brief_naive = MagicMock(generated_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1))
    ev_high = MagicMock(event_name="NFP", event_time=datetime.now(UTC))
    with patch.object(
        oe_mod, "get_session", side_effect=lambda: _make_cm_session(_FakeSession(scalar_vals=[brief_naive, ev_high]))
    ):
        r_brief_ev, _ = await svc._validate_analysis_preflight(_FakeSession(), _make_analysis(brief_id=10))
        assert r_brief_ev is not None and r_brief_ev.executed is False

    with (
        patch.object(
            oe_mod, "get_session", side_effect=lambda: _make_cm_session(_FakeSession(scalar_vals=[brief_naive, None]))
        ),
        patch(
            "monika.application.protocol.brief_contamination_guard.BriefContaminationGuard.check_magnitude_based_staleness",
            AsyncMock(return_value=(True, "price moved 2%")),
        ),
    ):
        r_mag, _ = await svc._validate_analysis_preflight(_FakeSession(), _make_analysis(brief_id=10))
        assert r_mag is not None and r_mag.executed is False

    # 2d. Duplicate in _EXECUTED_ANALYSIS_IDS & duplicate in DB
    _EXECUTED_ANALYSIS_IDS[2002] = time.time()
    r_dup_mem, _ = await svc._validate_analysis_preflight(_FakeSession(), _make_analysis(id=2002))
    assert r_dup_mem is not None and r_dup_mem.executed is False
    _EXECUTED_ANALYSIS_IDS.clear()

    r_dup_db, _ = await svc._validate_analysis_preflight(
        _FakeSession(scalar_vals=[MagicMock(id=99)]), _make_analysis(id=2003)
    )
    assert r_dup_db is not None and r_dup_db.executed is False
    _EXECUTED_ANALYSIS_IDS.clear()

    # 2e. Live MT5 disconnected abort
    from monika.infrastructure.brokers.broker_adapter import MT5LiveAdapter

    svc.dry_run = False
    svc.settings["paper_trading"] = {"enabled": False, "min_paper_trades_before_live": 0}
    svc.settings["trading"]["paper_trading"] = {"enabled": False, "min_paper_trades_before_live": 0}
    svc.broker_adapter = MT5LiveAdapter(svc.mt5, settings=svc.settings, dry_run=False, service=svc)
    svc.mt5.ensure_connected = AsyncMock(return_value=False)
    r_disc, _ = await svc._validate_analysis_preflight(_FakeSession(scalar_vals=[None, None]), _make_analysis(id=2004))
    assert r_disc is not None and r_disc.executed is False
    svc.mt5.ensure_connected = AsyncMock(return_value=True)
    svc.dry_run = True

    # 2f. Post-release news exemption, invalid entry_zone JSON, USDJPY cache update, stale price abort
    with patch.object(svc, "_get_current_price", AsyncMock(return_value=(150.0, True, 999.0))):
        r_p_stale, _ = await svc._validate_analysis_preflight(
            _FakeSession(scalar_vals=[None, None], rows_list=[[], [MagicMock(event_name="CPI")]]),
            _make_analysis(id=2005, symbol="USDJPY", entry_zone="{bad_json", catalyst="post-release"),
        )
        assert r_p_stale is not None and r_p_stale.executed is False

    # USDJPY non-stale + live spread check: mt5 fallback invalid tick (bid<=0) & exception fail-closed
    svc.dry_run = False
    svc.broker_adapter = None
    svc.mt5.get_current_price = AsyncMock(return_value={"bid": 0.0, "ask": 0.0})
    with patch.object(svc, "_get_current_price", AsyncMock(return_value=(150.0, False, 1.0))):
        r_sp_zero, _ = await svc._validate_analysis_preflight(
            _FakeSession(scalar_vals=[None, None]),
            _make_analysis(id=2006, symbol="USDJPY", entry_zone={"price": "bad_float"}),
        )
        assert r_sp_zero is not None and r_sp_zero.executed is False

        svc.mt5.get_current_price = AsyncMock(side_effect=RuntimeError("spread crash"))
        r_sp_err, _ = await svc._validate_analysis_preflight(
            _FakeSession(scalar_vals=[None, None]),
            _make_analysis(id=2007, symbol="USDJPY"),
        )
        assert r_sp_err is not None and r_sp_err.executed is False

    # 2g. Market price drift rejection, live account_equity<=0 abort, dry_run account_equity fallback, VIX fetch & error, risk_multiplier clamping & error, risk gate rejection, edge confidence rejection, scorecard rejection, min_verifiable confluence rejection, verify_confluence failure, adversarial hard_block & recommend_block
    with patch.object(svc, "_get_current_price", AsyncMock(return_value=(1.2000, False, 1.0))):
        svc.dry_run = True
        r_drift, _ = await svc._validate_analysis_preflight(
            _FakeSession(scalar_vals=[None, None]),
            _make_analysis(id=2008, entry_zone={"price": 1.1000, "order_type": "market"}),
        )
        assert r_drift is not None and r_drift.executed is False

    with (
        patch.object(svc, "_get_current_price", AsyncMock(return_value=(1.1000, False, 1.0))),
        patch.object(svc, "_get_equity", AsyncMock(return_value=0.0)),
    ):
        svc.dry_run = False
        svc.broker_adapter = MagicMock(get_tick=AsyncMock(return_value={"bid": 1.1000, "ask": 1.1001}))
        r_eq_live, _ = await svc._validate_analysis_preflight(
            _FakeSession(scalar_vals=[None, None]),
            _make_analysis(id=2009),
            account_equity=None,
        )
        assert r_eq_live is not None and r_eq_live.executed is False

        # Now dry_run=True with VIX row, clamped risk_multiplier, and risk gate rejection
        svc.dry_run = True
        with (
            patch.object(svc.sizer, "calculate_with_session", AsyncMock(return_value=sizing_ok)),
            patch.object(svc.gate, "check", AsyncMock(return_value=verdict_no)),
            patch.object(svc, "_log_result", AsyncMock()),
        ):
            r_rg_no, _ = await svc._validate_analysis_preflight(
                _FakeSession(scalar_vals=[None, None, MagicMock(close=18.5)]),
                _make_analysis(id=2010, risk_multiplier=0.1),
                account_equity=None,
            )
            assert r_rg_no is not None and r_rg_no.risk_approved is False

        # Risk gate approved -> edge signal confidence < min_confidence
        class _FlakyFloat:
            def __init__(self) -> None:
                self.calls = 0

            def __float__(self) -> float:
                self.calls += 1
                if self.calls == 1:
                    raise ValueError("bad float")
                return 1.0

        with (
            patch.object(svc.sizer, "calculate_with_session", AsyncMock(return_value=sizing_ok)),
            patch.object(svc.gate, "check", AsyncMock(return_value=verdict_ok)),
        ):
            r_conf_no, _ = await svc._validate_analysis_preflight(
                _FakeSession(scalar_vals=[None, None, None]),
                _make_analysis(
                    id=2011,
                    confidence=0.4,
                    decision_source="edge_registry",
                    risk_multiplier=_FlakyFloat(),
                ),
                account_equity=10000.0,
            )
            assert r_conf_no is not None and r_conf_no.executed is False

            # Scorecard rejection
            with patch(
                "monika.application.execution.service.executors.analysis_preflight.evaluate_analysis_scorecard",
                return_value=(False, "low expectancy"),
            ):
                r_sc_no, _ = await svc._validate_analysis_preflight(
                    _FakeSession(scalar_vals=[None, None, None]),
                    _make_analysis(id=2012, confidence=0.9, decision_source="concordant"),
                    account_equity=10000.0,
                )
                assert r_sc_no is not None and r_sc_no.executed is False

            # Confluence score < min_verifiable
            with patch(
                "monika.application.execution.service.executors.analysis_preflight.evaluate_analysis_scorecard",
                return_value=(True, "ok"),
            ):
                r_cf_low, _ = await svc._validate_analysis_preflight(
                    _FakeSession(scalar_vals=[None, None, None]),
                    _make_analysis(id=2013, confluence_score=1),
                    account_equity=10000.0,
                )
                assert r_cf_low is not None and r_cf_low.executed is False

                # verify_confluence failed
                with patch(
                    "monika.application.analysis.validators.confluence_verifier.verify_confluence",
                    AsyncMock(return_value={"verified": False, "blocking_issues": ["fake_fvg"]}),
                ):
                    r_vc_no, _ = await svc._validate_analysis_preflight(
                        _FakeSession(scalar_vals=[None, None, None]),
                        _make_analysis(id=2014, confluence_score=8),
                        account_equity=10000.0,
                    )
                    assert r_vc_no is not None and r_vc_no.executed is False

                # Adversarial check: cached invalid JSON -> run_adversarial_check -> hard_block, then recommend_block + low quality
                with (
                    patch(
                        "monika.application.analysis.validators.confluence_verifier.verify_confluence",
                        AsyncMock(return_value={"verified": True, "blocking_issues": []}),
                    ),
                    patch(
                        "monika.application.analysis.validators.adversarial_check.run_adversarial_check",
                        AsyncMock(
                            side_effect=[
                                {"hard_block": True, "hard_block_reason": "news trap"},
                                {
                                    "hard_block": False,
                                    "recommend_block": True,
                                    "overall_quality": "low",
                                    "block_reason": "weak",
                                    "strongest_counter_argument": "divergence",
                                },
                            ]
                        ),
                    ),
                    patch.object(
                        oe_mod,
                        "AgentNotifier",
                        return_value=MagicMock(send_warning=AsyncMock(side_effect=RuntimeError("warn err"))),
                    ),
                ):
                    r_adv_hard, _ = await svc._validate_analysis_preflight(
                        _FakeSession(scalar_vals=[None, None, None, MagicMock(value="{bad")]),
                        _make_analysis(id=2015),
                        account_equity=10000.0,
                    )
                    assert r_adv_hard is not None and r_adv_hard.executed is False

                    r_adv_rec, _ = await svc._validate_analysis_preflight(
                        _FakeSession(scalar_vals=[None, None, None, None]),
                        _make_analysis(id=2016),
                        account_equity=10000.0,
                    )
                    assert r_adv_rec is not None and r_adv_rec.executed is False

    # 3. analysis_submission.py (_submit_and_record_order) branches
    ctx = PreflightContext(
        start=datetime.now(UTC),
        symbol="EURUSD",
        decision="buy",
        sizing=sizing_ok,
        verdict=verdict_ok,
        is_edge_signal=True,
        current_price=1.1000,
        order_type="market",
        entry_price=1.1000,
        sl_price=1.0950,
        tp_price=1.1100,
        account_equity=10000.0,
        is_post_release=False,
    )

    # 3a. Lock not acquired
    @asynccontextmanager
    async def _lock_false(*_a: object, **_k: object) -> AsyncIterator[bool]:
        yield False

    with patch.object(oe_mod, "transactional_advisory_lock", side_effect=_lock_false):
        r_nl = await svc._submit_and_record_order(_FakeSession(), _make_analysis(id=3001), ctx)
        assert r_nl.executed is False

    @asynccontextmanager
    async def _lock_true(*_a: object, **_k: object) -> AsyncIterator[bool]:
        yield True

    with patch.object(oe_mod, "transactional_advisory_lock", side_effect=_lock_true):
        # 3b. Duplicate post-lock
        _EXECUTED_ANALYSIS_IDS[3002] = time.time()
        r_dup_pl = await svc._submit_and_record_order(_FakeSession(), _make_analysis(id=3002), ctx)
        assert r_dup_pl.executed is False
        _EXECUTED_ANALYSIS_IDS.clear()

        # 3c. Symbol open position already exists pre-MT5 recheck
        r_sym_open = await svc._submit_and_record_order(
            _FakeSession(scalar_vals=[None, 999]), _make_analysis(id=3003), ctx
        )
        assert r_sym_open.executed is False

        # 3d. Total active positions >= max_concurrent in first pre-MT5 recheck
        r_max_c1 = await svc._submit_and_record_order(
            _FakeSession(scalar_vals=[None, None, 5, 0]), _make_analysis(id=3004), ctx
        )
        assert r_max_c1.executed is False

        # 3e. Exception in first pre-MT5 recheck
        r_cnt_err1 = await svc._submit_and_record_order(
            _FakeSession(scalar_vals=[None, RuntimeError("cnt err")]), _make_analysis(id=3005), ctx
        )
        assert r_cnt_err1.executed is False

        # 3f. Evidence verifier branches (list, json str, non-json str, cf_raw list/str, rationale fallback, failed assertion, exception)
        svc.settings.setdefault("trading", {}).setdefault("risk", {})["confluence_verifier_enabled"] = True
        svc.evidence_verifier = MagicMock(pre_trade_assertions=AsyncMock(return_value=(False, ["missing_ob"])))
        with patch.object(svc, "_count_open_positions", AsyncMock(return_value=0)):
            for an_ev in (
                _make_analysis(id=3006, key_evidence=["ev1"]),
                _make_analysis(id=3007, key_evidence="plain text evidence\nline2"),
                _make_analysis(id=3008, key_evidence=None, confluence_factors_json=["cf1"]),
                _make_analysis(id=3009, key_evidence=None, confluence_factors_json='["cf_json"]'),
                _make_analysis(id=3010, key_evidence=None, confluence_factors_json="cf_plain\ncf2"),
                _make_analysis(
                    id=3011,
                    key_evidence=None,
                    confluence_factors_json=None,
                    rationale="First long sentence here. Second long sentence.",
                ),
            ):
                with patch(
                    "monika.application.execution.service.executors.analysis_submission.extract_quant_scorecard",
                    return_value={"edge": 1},
                ):
                    r_ev_fail = await svc._submit_and_record_order(
                        _FakeSession(scalar_vals=[None, None, 0]), an_ev, ctx
                    )
                    assert r_ev_fail.executed is False

        # Evidence verifier exception (non-fatal) + RateThrottler rejection
        svc.evidence_verifier = MagicMock(pre_trade_assertions=AsyncMock(side_effect=RuntimeError("ev crash")))
        svc.rate_throttler = MagicMock(
            wait_and_acquire=AsyncMock(return_value=MagicMock(allowed=False, reason="rate limit"))
        )
        with (
            patch.object(svc, "_count_open_positions", AsyncMock(return_value=0)),
            patch.object(svc, "_transition_order_state", AsyncMock()),
        ):
            r_thr = await svc._submit_and_record_order(
                _FakeSession(scalar_vals=[None, None, 0]), _make_analysis(id=3012), ctx
            )
            assert r_thr.executed is False

        # Second pre-MT5 recheck: total_exposure >= max_concurrent, and exception
        svc.rate_throttler = None
        with patch.object(svc, "_transition_order_state", AsyncMock()):
            r_max_c2 = await svc._submit_and_record_order(
                _FakeSession(scalar_vals=[None, None, 0, 0, 5, 0]), _make_analysis(id=3013), ctx
            )
            assert r_max_c2.executed is False

            r_cnt_err2 = await svc._submit_and_record_order(
                _FakeSession(scalar_vals=[None, None, 0, 0, RuntimeError("cnt2 err")]),
                _make_analysis(id=3014),
                ctx,
            )
            assert r_cnt_err2.executed is False

        # Broker submission: effect_gate=None -> broker_adapter.submit_order, partial fill (0 < exec_vol < req_vol), slippage calculation from exec_price, probe_lots <= 0.01, atr_row JSON, zero-trust verification warning, send_execution_notification fallback
        svc.effect_gate = None
        svc.evidence_verifier = MagicMock(
            pre_trade_assertions=AsyncMock(return_value=(True, [])),
            post_execution_reconciliation=AsyncMock(return_value={"verified": False, "issues": ["drift"]}),
        )
        svc.broker_adapter = MagicMock(
            spec=MT5LiveAdapter,
            submit_order=AsyncMock(
                return_value={
                    "success": True,
                    "ticket": 7001,
                    "price": 1.1002,
                    "volume": 0.005,
                    "slippage": None,
                }
            ),
            close_position=AsyncMock(return_value={"success": True}),
        )
        ctx_tiny = PreflightContext(
            **{**ctx.__dict__, "sizing": SizingResult(**{**sizing_ok.__dict__, "recommended_lots": 0.01})}
        )
        with (
            patch.object(svc, "_count_open_positions", AsyncMock(return_value=0)),
            patch.object(svc, "_transition_order_state", AsyncMock()),
            patch.object(svc, "_save_position", AsyncMock(return_value=801)),
            patch.object(svc, "_log_result", AsyncMock()),
            patch(
                "monika.core.analytics.paper_tracker.PaperTracker.open_paper_trade",
                AsyncMock(side_effect=RuntimeError("pt err")),
            ),
            patch(
                "monika.application.graph.nodes.risk.proposal_notifier.send_execution_notification",
                AsyncMock(side_effect=RuntimeError("card err")),
            ),
            patch.object(
                oe_mod,
                "AgentNotifier",
                return_value=MagicMock(
                    send_warning=AsyncMock(side_effect=RuntimeError("w err")),
                    send_info=AsyncMock(side_effect=RuntimeError("i err")),
                ),
            ),
        ):
            r_exec_ok = await svc._submit_and_record_order(
                _FakeSession(scalar_vals=[None, None, 0, 0, 0, 0, MagicMock(value_json="0.0050"), None]),
                _make_analysis(id=3015),
                ctx_tiny,
            )
            assert r_exec_ok.executed is True
            _EXECUTED_ANALYSIS_IDS.clear()

        # Orphan rollback when _save_position returns None in live mode, and close_position raises
        svc.dry_run = False
        svc.broker_adapter = MagicMock(
            submit_order=AsyncMock(return_value={"success": True, "ticket": 7002, "price": None, "volume": 0.1}),
            close_position=AsyncMock(side_effect=RuntimeError("close orphan err")),
        )
        with (
            patch.object(svc, "_count_open_positions", AsyncMock(return_value=0)),
            patch.object(svc, "_transition_order_state", AsyncMock()),
            patch.object(svc, "_save_position", AsyncMock(return_value=None)),
            patch.object(oe_mod, "AgentNotifier", return_value=MagicMock(send_critical=AsyncMock())),
        ):
            with pytest.raises(RuntimeError, match="Failed to persist position"):
                await svc._submit_and_record_order(
                    _FakeSession(scalar_vals=[None, None, 0, 0, 0, 0]),
                    _make_analysis(id=3016),
                    ctx,
                )

        # Broker failure path (mt5_result success=False -> TRADE FAILED notification error)
        svc.dry_run = True
        svc.broker_adapter = MagicMock(
            submit_order=AsyncMock(return_value={"success": False, "error": "rejected by broker"})
        )
        with (
            patch.object(svc, "_count_open_positions", AsyncMock(return_value=0)),
            patch.object(svc, "_transition_order_state", AsyncMock()),
            patch.object(svc, "_log_result", AsyncMock()),
            patch.object(
                oe_mod,
                "AgentNotifier",
                return_value=MagicMock(send_warning=AsyncMock(side_effect=RuntimeError("fail notif err"))),
            ),
        ):
            r_bfail = await svc._submit_and_record_order(
                _FakeSession(scalar_vals=[None, None, 0, 0, 0, 0]),
                _make_analysis(id=3017),
                ctx,
            )
            assert r_bfail.executed is False


@pytest.mark.asyncio
async def test_paired_preplanned_proposal_tranche_executors_full_coverage() -> None:
    from monika.application.execution.effect_gate import AbortRequested
    from monika.application.execution.execution_service import ExecutionService
    import monika.application.execution.service.order_executor as oe_mod
    from monika.application.execution.service.order_executor import ExecutionResult, _EXECUTED_ANALYSIS_IDS
    from monika.domain.risk.position_sizing import SizingResult
    from monika.domain.risk.risk_gate import RiskVerdict
    from monika.domain.risk.trade_proposal import TradeProposal

    svc = ExecutionService(
        settings={
            "paper_trading": {"enabled": True, "initial_balance": 10000.0},
            "trading": {"paper_trading": {"enabled": True}, "risk": {"max_concurrent_positions": 5}},
            "execution": {"max_price_staleness_seconds": 60},
        },
        mt5_client=MagicMock(
            ensure_connected=AsyncMock(return_value=True),
            get_symbol_info=AsyncMock(return_value={"contract_size": 100000.0}),
            place_order=AsyncMock(return_value={"success": True, "ticket": 8001, "price": 1.1000}),
            close_position=AsyncMock(return_value={"success": True}),
            get_current_price=AsyncMock(return_value={"bid": 1.1000, "ask": 1.1002}),
        ),
        dry_run=True,
    )

    sizing_ok = SizingResult(
        symbol="EURUSD",
        direction="BUY",
        entry_price=1.1000,
        stop_loss=1.0950,
        take_profit=1.1100,
        account_equity=10000.0,
        risk_percent=1.0,
        risk_amount_usd=100.0,
        sl_distance_price=0.0050,
        sl_distance_pips=50.0,
        pip_value_per_lot=10.0,
        raw_lots=0.10,
        recommended_lots=0.10,
        rr_ratio=2.0,
        is_valid=True,
    )
    sizing_bad = SizingResult(**{**sizing_ok.__dict__, "is_valid": False, "rejection_reasons": ["bad"]})
    verdict_ok = RiskVerdict(approved=True, symbol="EURUSD", proposed_lots=0.1, checks_passed=["ok"], checks_failed=[])
    verdict_no = RiskVerdict(
        approved=False,
        symbol="EURUSD",
        proposed_lots=0.1,
        checks_passed=[],
        checks_failed=["f"],
        rejection_reasons=["f"],
    )

    @asynccontextmanager
    async def _lock_false(*_a: object, **_k: object) -> AsyncIterator[bool]:
        yield False

    @asynccontextmanager
    async def _lock_true(*_a: object, **_k: object) -> AsyncIterator[bool]:
        yield True

    # 1. paired_executor.py (execute_paired_analyses)
    p_an = MagicMock(
        id=1, symbol="EURUSD", decision="buy", entry_zone={"price": 1.1000}, stop_loss=1.0950, take_profit_1=1.1100
    )
    h_an = MagicMock(
        id=2, symbol="GBPUSD", decision="sell", entry_zone={"price": 1.2500}, stop_loss=1.2550, take_profit_1=1.2400
    )

    # 1a. Live equity<=0 abort & dry_run equity fallback + lock not acquired
    svc.dry_run = False
    with patch.object(svc, "_get_equity", AsyncMock(return_value=0.0)):
        assert (await svc.execute_paired_analyses(_FakeSession(), p_an, h_an, "pg_123456", account_equity=None))[
            "success"
        ] is False

    svc.dry_run = True
    with (
        patch.object(svc, "_get_equity", AsyncMock(return_value=0.0)),
        patch.object(oe_mod, "transactional_advisory_lock", side_effect=_lock_false),
    ):
        assert (await svc.execute_paired_analyses(_FakeSession(), p_an, h_an, "pg_123456", account_equity=None))[
            "success"
        ] is False

    with patch.object(oe_mod, "transactional_advisory_lock", side_effect=_lock_true):
        # 1b. Invalid primary entry_zone, primary sizing invalid, missing symbol info, invalid hedge entry_zone, hedge_notional<=0, hedge sizing invalid, primary/hedge risk gate rejected, open_count+2 > max_pos
        p_bad_ez = MagicMock(symbol="EURUSD", entry_zone={"price": 0})
        assert (await svc.execute_paired_analyses(_FakeSession(), p_bad_ez, h_an, "pg_123456", 10000.0))[
            "success"
        ] is False

        with patch.object(svc.sizer, "calculate_with_session", AsyncMock(return_value=sizing_bad)):
            assert (await svc.execute_paired_analyses(_FakeSession(), p_an, h_an, "pg_123456", 10000.0))[
                "success"
            ] is False

        with patch.object(svc.sizer, "calculate_with_session", AsyncMock(return_value=sizing_ok)):
            svc.mt5.get_symbol_info = AsyncMock(return_value=None)
            assert (await svc.execute_paired_analyses(_FakeSession(), p_an, h_an, "pg_123456", 10000.0))[
                "success"
            ] is False

            svc.mt5.get_symbol_info = AsyncMock(return_value={"contract_size": 100000.0})
            h_bad_ez = MagicMock(symbol="GBPUSD", entry_zone={"price": 0})
            assert (await svc.execute_paired_analyses(_FakeSession(), p_an, h_bad_ez, "pg_123456", 10000.0))[
                "success"
            ] is False

            svc.mt5.get_symbol_info = AsyncMock(side_effect=[{"contract_size": 100000.0}, {"contract_size": -1.0}])
            assert (await svc.execute_paired_analyses(_FakeSession(), p_an, h_an, "pg_123456", 10000.0))[
                "success"
            ] is False

            svc.mt5.get_symbol_info = AsyncMock(return_value={"contract_size": 100000.0})
            with patch.object(svc.sizer, "calculate_with_session", AsyncMock(side_effect=[sizing_ok, sizing_bad])):
                assert (await svc.execute_paired_analyses(_FakeSession(), p_an, h_an, "pg_123456", 10000.0))[
                    "success"
                ] is False

            with patch.object(svc.gate, "check", AsyncMock(return_value=verdict_no)):
                assert (await svc.execute_paired_analyses(_FakeSession(), p_an, h_an, "pg_123456", 10000.0))[
                    "success"
                ] is False

            with patch.object(svc.gate, "check", AsyncMock(side_effect=[verdict_ok, verdict_no])):
                assert (await svc.execute_paired_analyses(_FakeSession(), p_an, h_an, "pg_123456", 10000.0))[
                    "success"
                ] is False

            with patch.object(svc.gate, "check", AsyncMock(return_value=verdict_ok)):
                with patch.object(svc, "_count_open_positions", AsyncMock(return_value=4)):
                    assert (await svc.execute_paired_analyses(_FakeSession(), p_an, h_an, "pg_123456", 10000.0))[
                        "success"
                    ] is False

                # 1c. Primary leg AbortRequested -> primary leg failed
                svc.rate_throttler = MagicMock(wait_and_acquire=AsyncMock())
                svc.effect_gate = MagicMock(admit=AsyncMock(side_effect=AbortRequested("abort leg1")))
                svc.broker_adapter = MagicMock()
                with (
                    patch.object(svc, "_count_open_positions", AsyncMock(return_value=0)),
                    patch.object(svc, "_transition_order_state", AsyncMock()),
                ):
                    assert (await svc.execute_paired_analyses(_FakeSession(), p_an, h_an, "pg_123456", 10000.0))[
                        "success"
                    ] is False

                # 1d. Primary leg succeeds (dry_run without adapter), Hedge leg fails -> rollback fails -> orphan_emergency persisted
                svc.broker_adapter = None
                svc.effect_gate = None
                svc.dry_run = False
                svc.mt5.place_order = AsyncMock(
                    side_effect=[
                        {"success": True, "ticket": 8101, "price": 1.1000},
                        {"success": False, "error": "leg2 rejected"},
                    ]
                )
                svc.mt5.close_position = AsyncMock(return_value={"success": False, "error": "close leg1 failed"})
                orphan_pos = MagicMock(status="open")
                with (
                    patch.object(svc, "_count_open_positions", AsyncMock(return_value=0)),
                    patch.object(svc, "_transition_order_state", AsyncMock()),
                    patch.object(svc, "_save_position", AsyncMock(return_value=901)),
                    patch.object(
                        oe_mod,
                        "AgentNotifier",
                        return_value=MagicMock(send_critical=AsyncMock(side_effect=RuntimeError("n err"))),
                    ),
                ):
                    res_pair_orph = await svc.execute_paired_analyses(
                        _FakeSession(scalar_vals=[orphan_pos]), p_an, h_an, "pg_123456", 10000.0
                    )
                    assert res_pair_orph["success"] is False
                    assert orphan_pos.status == "orphan_pending_close"

                # 1e. Both legs succeed (dry_run=True without adapter) + PaperTracker error, then DB save error in live mode closing both legs
                svc.dry_run = True
                with (
                    patch.object(svc, "_count_open_positions", AsyncMock(return_value=0)),
                    patch.object(svc, "_transition_order_state", AsyncMock()),
                    patch.object(svc, "_save_position", AsyncMock(return_value=902)),
                    patch(
                        "monika.core.analytics.paper_tracker.PaperTracker.open_paper_trade",
                        AsyncMock(side_effect=RuntimeError("pt err")),
                    ),
                ):
                    res_pair_ok = await svc.execute_paired_analyses(_FakeSession(), p_an, h_an, "pg_123456", 10000.0)
                    assert res_pair_ok["success"] is True

                svc.dry_run = False
                svc.mt5.place_order = AsyncMock(
                    side_effect=[
                        {"success": True, "ticket": 8201, "price": 1.1000},
                        {"success": True, "ticket": 8202, "price": 1.2500},
                    ]
                )
                svc.mt5.close_position = AsyncMock(side_effect=RuntimeError("close both failed"))
                with (
                    patch.object(svc, "_count_open_positions", AsyncMock(return_value=0)),
                    patch.object(svc, "_transition_order_state", AsyncMock()),
                    patch.object(svc, "_save_position", AsyncMock(side_effect=RuntimeError("db pair crash"))),
                    patch.object(oe_mod, "AgentNotifier", return_value=MagicMock(send_critical=AsyncMock())),
                ):
                    with pytest.raises(RuntimeError, match="db pair crash"):
                        await svc.execute_paired_analyses(_FakeSession(), p_an, h_an, "pg_123456", 10000.0)

    # 2. preplanned_executor.py (execute_preplanned_order)
    svc.dry_run = True
    # 2a. decision not buy/sell
    assert (await svc.execute_preplanned_order(_FakeSession(), "EURUSD", {"decision": "wait"})).executed is False

    # 2b. stale price abort
    with patch.object(svc, "_get_current_price", AsyncMock(return_value=(1.1000, True, 999.0))):
        assert (
            await svc.execute_preplanned_order(
                _FakeSession(),
                "EURUSD",
                {"decision": "buy", "entry_price": 1.1000, "stop_loss": 1.0950, "take_profit": 1.1100},
            )
        ).executed is False

    # 2c. Live spread check unacceptable & spread exception, live equity<=0 abort, dry_run equity fallback, sizing invalid
    with patch.object(svc, "_get_current_price", AsyncMock(return_value=(1.1000, False, 1.0))):
        svc.dry_run = False
        svc.broker_adapter = None
        svc.mt5.get_current_price = AsyncMock(return_value={"bid": 1.1000, "ask": 1.1500})
        assert (
            await svc.execute_preplanned_order(
                _FakeSession(),
                "EURUSD",
                {"decision": "buy", "entry_price": 1.1000, "stop_loss": 1.0950, "take_profit": 1.1100},
            )
        ).executed is False

        svc.mt5.get_current_price = AsyncMock(side_effect=RuntimeError("sp err"))
        with patch.object(svc, "_get_equity", AsyncMock(return_value=0.0)):
            assert (
                await svc.execute_preplanned_order(
                    _FakeSession(),
                    "EURUSD",
                    {"decision": "buy", "entry_price": 1.1000, "stop_loss": 1.0950, "take_profit": 1.1100},
                    account_equity=None,
                )
            ).executed is False

        svc.dry_run = True
        with (
            patch.object(svc, "_get_equity", AsyncMock(return_value=0.0)),
            patch.object(svc.sizer, "calculate_with_session", AsyncMock(return_value=sizing_bad)),
        ):
            assert (
                await svc.execute_preplanned_order(
                    _FakeSession(),
                    "EURUSD",
                    {"decision": "buy", "entry_price": 1.1000, "stop_loss": 1.0950, "take_profit": 1.1100},
                    account_equity=None,
                )
            ).executed is False

        # 2d. specified_lots clamping with invalid max_lot/min_lot on spec, risk gate rejected, advisory lock false, _count_open_positions error & >= max_concurrent, throttler rejected, self-healing invoked, AbortRequested, partial fill + slippage + _save_position, failed execution
        bad_spec = MagicMock(max_lot="bad", min_lot="bad")
        setattr(sizing_ok, "_instrument_spec", bad_spec)
        with (
            patch.object(svc.sizer, "calculate_with_session", AsyncMock(return_value=sizing_ok)),
            patch.object(svc.gate, "check", AsyncMock(return_value=verdict_no)),
            patch.object(svc, "_log_result", AsyncMock()),
        ):
            s_get_err = _FakeSession()
            setattr(s_get_err, "get", AsyncMock(side_effect=RuntimeError("get err")))
            assert (
                await svc.execute_preplanned_order(
                    s_get_err,
                    "EURUSD",
                    {
                        "decision": "buy",
                        "entry_price": 1.1000,
                        "stop_loss": 1.0950,
                        "take_profit": 1.1100,
                        "lot_size": 0.2,
                        "analysis_id": 10,
                    },
                    account_equity=10000.0,
                )
            ).risk_approved is False

        with (
            patch.object(svc.sizer, "calculate_with_session", AsyncMock(return_value=sizing_ok)),
            patch.object(svc.gate, "check", AsyncMock(return_value=verdict_ok)),
        ):
            with patch.object(oe_mod, "transactional_advisory_lock", side_effect=_lock_false):
                assert (
                    await svc.execute_preplanned_order(
                        _FakeSession(),
                        "EURUSD",
                        {"decision": "buy", "entry_price": 1.1000, "stop_loss": 1.0950, "take_profit": 1.1100},
                        account_equity=10000.0,
                    )
                ).executed is False

            with patch.object(oe_mod, "transactional_advisory_lock", side_effect=_lock_true):
                with patch.object(svc, "_count_open_positions", AsyncMock(side_effect=RuntimeError("pos err"))):
                    assert (
                        await svc.execute_preplanned_order(
                            _FakeSession(),
                            "EURUSD",
                            {"decision": "buy", "entry_price": 1.1000, "stop_loss": 1.0950, "take_profit": 1.1100},
                            account_equity=10000.0,
                        )
                    ).executed is False

                with patch.object(svc, "_count_open_positions", AsyncMock(return_value=5)):
                    assert (
                        await svc.execute_preplanned_order(
                            _FakeSession(),
                            "EURUSD",
                            {"decision": "buy", "entry_price": 1.1000, "stop_loss": 1.0950, "take_profit": 1.1100},
                            account_equity=10000.0,
                        )
                    ).executed is False

                # Throttler rejected
                svc.rate_throttler = MagicMock(
                    wait_and_acquire=AsyncMock(return_value=MagicMock(allowed=False, reason="throttled"))
                )
                with (
                    patch.object(svc, "_count_open_positions", AsyncMock(return_value=0)),
                    patch.object(svc, "_transition_order_state", AsyncMock()),
                ):
                    assert (
                        await svc.execute_preplanned_order(
                            _FakeSession(),
                            "EURUSD",
                            {"decision": "buy", "entry_price": 1.1000, "stop_loss": 1.0950, "take_profit": 1.1100},
                            account_equity=10000.0,
                        )
                    ).executed is False

                # AbortRequested from effect_gate
                svc.rate_throttler = None
                svc.broker_adapter = MagicMock()
                svc.effect_gate = MagicMock(admit=AsyncMock(side_effect=AbortRequested("abort preplanned")))
                with (
                    patch.object(svc, "_count_open_positions", AsyncMock(return_value=0)),
                    patch.object(svc, "_transition_order_state", AsyncMock()),
                ):
                    assert (
                        await svc.execute_preplanned_order(
                            _FakeSession(),
                            "EURUSD",
                            {"decision": "buy", "entry_price": 1.1000, "stop_loss": 1.0950, "take_profit": 1.1100},
                            account_equity=10000.0,
                        )
                    ).executed is False

                # Self-healing invoked on failure -> then partial fill success with AssetAnalysis object saved
                svc.effect_gate = None
                svc.broker_adapter = MagicMock(
                    submit_order=AsyncMock(return_value={"success": False, "error": "requote", "retcode": 10004})
                )
                from monika.infrastructure.database.models import AssetAnalysis

                real_an_obj = AssetAnalysis(id=55, symbol="EURUSD", decision="buy")
                s_with_an = _FakeSession()
                setattr(s_with_an, "get", AsyncMock(return_value=real_an_obj))
                with (
                    patch.object(svc, "_count_open_positions", AsyncMock(return_value=0)),
                    patch.object(svc, "_transition_order_state", AsyncMock()),
                    patch.object(svc, "_save_position", AsyncMock(return_value=955)),
                    patch.object(svc, "_log_result", AsyncMock()),
                    patch(
                        "monika.application.execution.service.self_healing_executor.MT5SelfHealingExecutor.heal_and_reexecute",
                        AsyncMock(
                            return_value={
                                "success": True,
                                "ticket": 8501,
                                "price": 1.1002,
                                "volume": 0.05,
                                "slippage": None,
                            }
                        ),
                    ),
                ):
                    res_pp_ok = await svc.execute_preplanned_order(
                        s_with_an,
                        "EURUSD",
                        {
                            "decision": "buy",
                            "entry_price": 1.1000,
                            "stop_loss": 1.0950,
                            "take_profit": 1.1100,
                            "analysis_id": 55,
                        },
                        account_equity=10000.0,
                    )
                    assert res_pp_ok.executed is True
                    _EXECUTED_ANALYSIS_IDS.clear()

    # 3. proposal_executor.py (execute_proposal)
    prop = TradeProposal(
        symbol="EURUSD",
        direction="BUY",
        entry_price=1.1000,
        stop_loss=1.0950,
        take_profit=1.1100,
        lot_size=0.1,
        metadata={"analysis_id": 10},
    )
    # 3a. ESTOP active
    with patch("monika.application.agent.estop.is_estop_active", return_value=True):
        assert (await svc.execute_proposal(_FakeSession(), prop)).executed is False

    # 3b. FortressAdmissionValidator rejects proposal
    with patch(
        "monika.domain.risk.trade_proposal.FortressAdmissionValidator.validate_proposal",
        return_value=(False, ["invalid"]),
    ):
        assert (await svc.execute_proposal(_FakeSession(), prop)).executed is False

    # 3c. Plugin pre_order veto, pre_order exception, post_order exception, risk_approved=False release_lock, and executed=False mark_failed
    fake_guard = MagicMock(
        generate_key=MagicMock(return_value="k_1"),
        acquire_lock=AsyncMock(return_value=(True, None)),
        release_lock=AsyncMock(),
        mark_completed=AsyncMock(),
        mark_failed=AsyncMock(),
    )
    svc.idempotency_guard = fake_guard

    fake_engine_veto = MagicMock(
        emit_waterfall=AsyncMock(return_value=(False, "vetoed")),
    )
    with patch("monika.application.plugins.engine.engine.get_plugin_engine", return_value=fake_engine_veto):
        assert (await svc.execute_proposal(_FakeSession(), prop)).executed is False

    fake_engine_err = MagicMock(
        emit_waterfall=AsyncMock(side_effect=RuntimeError("pre err")),
        emit_hook=AsyncMock(side_effect=RuntimeError("post err")),
    )
    res_unapproved = ExecutionResult(
        symbol="EURUSD",
        analysis_id=10,
        decision="buy",
        sizing=None,
        risk_approved=False,
        risk_checks_passed=[],
        risk_checks_failed=["f"],
        risk_rejection_reasons=["r"],
        executed=False,
        mt5_ticket=None,
        executed_price=None,
        executed_lots=None,
        mt5_error="err",
        position_id=None,
        timestamp=datetime.now(UTC),
        elapsed_ms=5,
    )
    res_exec_fail = ExecutionResult(**{**res_unapproved.__dict__, "risk_approved": True, "executed": False})
    with (
        patch("monika.application.plugins.engine.engine.get_plugin_engine", return_value=fake_engine_err),
        patch.object(svc, "execute_preplanned_order", AsyncMock(side_effect=[res_unapproved, res_exec_fail])),
    ):
        await svc.execute_proposal(_FakeSession(), prop)
        await svc.execute_proposal(_FakeSession(), prop)
        fake_guard.mark_failed.assert_awaited_once()

    # 4. tranche_executor.py (execute_tranche_order)
    sizing_ok.recommended_lots = 0.20
    t_an = MagicMock(
        id=90,
        symbol="EURUSD",
        decision="sell",
        current_price=1.1000,
        entry_price=1.1000,
        entry_zone={"price": 1.1000},
        stop_loss=1.1050,
        take_profit=1.0900,
        take_profit_1=1.0900,
        take_profit_2=None,
    )
    with patch(
        "monika.application.execution.service.executors.tranche_executor.get_instrument_spec",
        return_value=MagicMock(lot_step=0.01, min_lot=0.01),
    ):
        # 4a. sizing invalid & risk gate rejected
        with patch.object(svc.sizer, "calculate_with_session", AsyncMock(return_value=sizing_bad)):
            assert (await svc.execute_tranche_order(_FakeSession(), t_an, account_equity=None))["success"] is False

        with (
            patch.object(svc.sizer, "calculate_with_session", AsyncMock(return_value=sizing_ok)),
            patch.object(svc.gate, "check", AsyncMock(return_value=verdict_no)),
        ):
            assert (await svc.execute_tranche_order(_FakeSession(), t_an, account_equity=10000.0))["success"] is False

        # 4b. dry_run without broker_adapter -> both legs succeed -> DB save fails -> rollback
        svc.broker_adapter = None
        svc.dry_run = True
        svc.rate_throttler = MagicMock(wait_and_acquire=AsyncMock())
        sess_tranche_fail = _FakeSession()
        setattr(sess_tranche_fail, "commit", AsyncMock(side_effect=RuntimeError("db tranche err")))
        with (
            patch.object(svc.sizer, "calculate_with_session", AsyncMock(return_value=sizing_ok)),
            patch.object(svc.gate, "check", AsyncMock(return_value=verdict_ok)),
            patch.object(svc, "_transition_order_state", AsyncMock()),
            patch.object(svc, "_save_position", AsyncMock(return_value=1)),
        ):
            res_tr_dbfail = await svc.execute_tranche_order(sess_tranche_fail, t_an, account_equity=10000.0)
            assert res_tr_dbfail["success"] is False

        # 4c. Live mode: Leg 1 succeeds via mt5.place_order, Leg 2 raises -> Leg 1 rollback via mt5.close_position raises -> orphan_emergency
        svc.dry_run = False
        svc.mt5.place_order = AsyncMock(
            side_effect=[
                {"success": True, "ticket": 9101, "price": 1.1000},
                RuntimeError("leg2 crash"),
            ]
        )
        svc.mt5.close_position = AsyncMock(side_effect=RuntimeError("rollback crash"))
        with (
            patch.object(svc.sizer, "calculate_with_session", AsyncMock(return_value=sizing_ok)),
            patch.object(svc.gate, "check", AsyncMock(return_value=verdict_ok)),
            patch.object(svc, "_transition_order_state", AsyncMock()),
            patch.object(svc, "_save_position", AsyncMock(side_effect=RuntimeError("save orphan err"))),
            patch.object(
                oe_mod,
                "AgentNotifier",
                return_value=MagicMock(send_critical=AsyncMock(side_effect=RuntimeError("n err"))),
            ),
        ):
            res_tr_orph = await svc.execute_tranche_order(_FakeSession(), t_an, account_equity=10000.0)
            assert res_tr_orph["success"] is False


@pytest.mark.asyncio
async def test_application_execution_remaining_143_lines_coverage() -> None:
    """Close the final 143 missed lines across the 10 remaining files in monika.application.execution."""
    from monika.application.execution.effect_gate import AbortRequested
    from monika.application.execution.execution_service import ExecutionService
    import monika.application.execution.service.emergency_manager as em_mod
    from monika.application.execution.service.executors.analysis_preflight import PreflightContext
    import monika.application.execution.service.order_executor as oe_mod
    from monika.application.execution.service.order_executor import ExecutionResult
    import monika.application.execution.service.position_synchronizer as ps_mod
    from monika.application.execution.service.trade_confirm import TradeConfirmManager
    from monika.domain.risk.position_sizing import SizingResult
    from monika.domain.risk.risk_gate import RiskVerdict
    from monika.domain.risk.trade_proposal import TradeProposal
    from monika.infrastructure.brokers.broker_adapter import MT5LiveAdapter

    @asynccontextmanager
    async def _lock_true(*_a: object, **_k: object) -> AsyncIterator[bool]:
        yield True

    svc = ExecutionService(
        settings={
            "paper_trading": {"enabled": True, "initial_balance": 10000.0, "pause_system_on_daily_sl_limit": False},
            "trading": {
                "paper_trading": {"enabled": True, "pause_system_on_daily_sl_limit": False},
                "auto_execute": False,
                "min_paper_trades_before_live": 5,
                "graduation_min_win_rate": 0.6,
                "risk": {
                    "dynamic_risk_scaling": True,
                    "max_concurrent_positions": 5,
                    "max_daily_sl_hits": 1,
                },
            },
            "execution": {"max_execute_age_minutes": 15, "max_price_staleness_seconds": 60},
            "data_quality": {"max_brief_age_execution_hours": 12.0},
        },
        mt5_client=MagicMock(
            ensure_connected=AsyncMock(return_value=True),
            get_symbol_info=AsyncMock(return_value={"contract_size": 100000.0}),
            place_order=AsyncMock(return_value={"success": True, "ticket": 8001, "price": 1.1000}),
            close_position=AsyncMock(return_value={"success": True, "profit": 10.0}),
            get_current_price=AsyncMock(return_value={"bid": 1.1000, "ask": 1.1002}),
        ),
        dry_run=True,
    )

    # 1. emergency_manager.py: 133, 268, 273-274, 361-362, 424-426, 481-507, 511-512, 577
    # Line 133: close_position_by_ticket with broker_adapter=None on live position uses self.mt5.close_position
    svc.broker_adapter = None
    svc.mt5.close_position = AsyncMock(return_value={"success": True, "profit": 12.0})
    pos_live = MagicMock(
        id=1,
        mt5_ticket=101,
        symbol="EURUSD",
        direction="buy",
        status="open",
        is_paper=False,
        volume=1.0,
        pnl=0.0,
        analysis_id=None,
    )
    sess_live_101 = _FakeSession(scalar_vals=[pos_live, pos_live])
    with patch.object(em_mod, "get_session", side_effect=lambda: _make_cm_session(sess_live_101)):
        assert (await svc.close_position_by_ticket(101))["success"] is True

    # Lines 268, 273-274: _close_paper_position when _get_current_price is absent on EmergencyManagerMixin
    from monika.application.execution.service.emergency_manager import EmergencyManagerMixin

    class _BareEM(EmergencyManagerMixin):
        def __init__(self, mt5_obj: object, gate_obj: object) -> None:
            self.mt5 = mt5_obj
            self.gate = gate_obj
            self.dry_run = True
            self.settings = {"paper_trading": {"initial_balance": 10000.0}}

    bare_em = _BareEM(
        MagicMock(get_current_price=AsyncMock(return_value={"bid": 1.1005, "ask": 1.1007})),
        svc.gate,
    )
    pos_p1 = MagicMock(
        id=2,
        mt5_ticket=102,
        symbol="EURUSD",
        direction="buy",
        status="open",
        is_paper=True,
        volume=1.0,
        entry_price=1.1000,
        analysis_id=None,
    )
    res_p1 = await bare_em._close_paper_position(_FakeSession(), pos_p1, "user", "manual")
    assert res_p1["success"] is True

    bare_em.mt5 = MagicMock(get_current_price=AsyncMock(side_effect=RuntimeError("mt5 price err")))
    pos_p2 = MagicMock(
        id=3,
        mt5_ticket=103,
        symbol="EURUSD",
        direction="sell",
        status="open",
        is_paper=True,
        volume=1.0,
        entry_price=1.1000,
        analysis_id=None,
    )
    res_p2 = await bare_em._close_paper_position(
        _FakeSession(scalar_vals=[MagicMock(close=1.0990)]), pos_p2, "user", "manual"
    )
    assert res_p2["success"] is True

    # Lines 361-362: trigger_circuit_breaker when AgentNotifier().send_warning raises
    with (
        patch.object(em_mod, "get_session", return_value=_make_cm_session(_FakeSession())),
        patch(
            "monika.infrastructure.notifications.telegram_notifier.AgentNotifier.send_warning",
            AsyncMock(side_effect=RuntimeError("cb notif err")),
        ),
    ):
        assert (await svc.trigger_circuit_breaker("drawdown", 60))["success"] is True

    # Lines 424-426, 481-507, 511-512, 577: kill_switch
    svc.gate.pause_trading = AsyncMock()
    paper_row_1 = MagicMock(
        symbol="EURUSD",
        entry_price=1.1000,
        stop_loss=1.1050,
        direction="sell",
        risk_pct=1.0,
        opened_at=datetime.now(UTC) - timedelta(hours=1),
        status="open",
    )
    paper_row_2 = MagicMock(
        symbol="EURUSD",
        entry_price=0.0,
        stop_loss=0.0,
        direction="buy",
        risk_pct=1.0,
        opened_at=None,
        status="open",
    )
    svc.broker_adapter = MagicMock(
        cancel_all_orders=AsyncMock(return_value={"cancelled": 0}),
        close_all_positions=AsyncMock(
            side_effect=[
                TimeoutError("close timeout"),
                {"closed": 0, "failed": 0, "total": 0, "errors": []},
            ]
        ),
        get_open_positions=AsyncMock(return_value=[]),
    )
    svc.mt5.sync_positions_from_mt5 = AsyncMock()
    ks_sess_1 = _FakeSession(
        scalar_vals=[None, None, None, None, None, MagicMock(close=1.0980), None, None, None],
        rows_list=[[], [], [], [], [paper_row_1, paper_row_2]],
    )
    with (
        patch.object(em_mod, "get_session", side_effect=lambda: _make_cm_session(ks_sess_1)),
        patch.object(em_mod, "safe_commit", AsyncMock()),
        patch("asyncio.sleep", AsyncMock()),
    ):
        ks_res1 = await svc.kill_switch("test_timeout_and_papers")
        assert ks_res1["paper_closed"] == 2

    # Line 577 (no adapter and mt5 has no get_open_positions when total > 0) & lines 511-512 (paper_session raises)
    orig_mt5 = svc.mt5
    svc.broker_adapter = None
    svc.mt5 = MagicMock(spec=[])
    ks_sess_2 = _FakeSession(
        scalar_vals=[None, None, None, None, None, None],
        rows_list=[[], [], [paper_row_1]],
    )
    with (
        patch.object(em_mod, "get_session", side_effect=lambda: _make_cm_session(ks_sess_2)),
        patch.object(em_mod, "safe_commit", AsyncMock()),
        patch("asyncio.sleep", AsyncMock()),
    ):
        ks_res2 = await svc.kill_switch("no_adapter_no_mt5")
        assert ks_res2["total"] == 1

    ks_sess_3 = _FakeSession(
        scalar_vals=[None, None, RuntimeError("paper query err"), None, None],
        rows_list=[[], []],
    )
    with (
        patch.object(em_mod, "get_session", side_effect=lambda: _make_cm_session(ks_sess_3)),
        patch.object(em_mod, "safe_commit", AsyncMock()),
        patch("asyncio.sleep", AsyncMock()),
    ):
        await svc.kill_switch("paper_query_err")
    svc.mt5 = orig_mt5
    from monika.application.agent.estop import disarm_estop

    disarm_estop()
    if svc.effect_gate is not None:
        svc.effect_gate.reset()

    # 2. risk_evaluator.py: 125, 137-147
    with patch(
        "monika.core.analytics.paper_tracker.PaperTracker.get_statistics",
        AsyncMock(
            side_effect=[
                {"by_symbol": {"EURUSD": {"trades": 20, "win_rate": 60.0, "payoff_ratio": 2.0}}},
                {"by_symbol": {"EURUSD": {"trades": 20, "win_rate": 10.0, "payoff_ratio": 0.0}}},
            ]
        ),
    ):
        r_kelly_pos = await svc._get_dynamic_risk_percent(_FakeSession(), "EURUSD", 1.0)
        assert r_kelly_pos > 0
        r_kelly_neg = await svc._get_dynamic_risk_percent(_FakeSession(), "EURUSD", 1.0)
        assert r_kelly_neg == 0.0

    # 3. trade_confirm.py: 125, 157-159, 185-187
    tcm = TradeConfirmManager()
    assert (await tcm.execute_confirmed_action("nonexistent_id", AsyncMock()))[0] is False

    act_ok = tcm.create_pending_action("open", "ok_normal", {}, ttl_seconds=60)
    assert (await tcm.execute_confirmed_action(act_ok.confirm_id, AsyncMock(return_value="done")))[0] is True

    act_cancel = tcm.create_pending_action("open", "cancel_normal", {}, ttl_seconds=60)
    assert tcm.cancel_action(act_cancel.confirm_id) is True

    # 4. position_synchronizer.py: 125, 171-178, 321, 647-648
    now_dt = datetime.now(UTC)
    closed_with_comments = [
        MagicMock(
            id=20 + idx,
            mt5_ticket=5000 + idx,
            symbol="EURUSD",
            direction="buy",
            volume=0.1,
            entry_price=1.1000,
            sl=1.0950,
            tp=1.1100,
            pnl=10.0,
            opened_at=now_dt - timedelta(hours=1),
            closed_at=now_dt,
            _mt5_close_reason=999,
            _mt5_exit_price=1.1010,
            comment=c_txt,
        )
        for idx, c_txt in enumerate(["trailing_stop", "breakeven_sl", "partial_tp", "manual_close"], start=1)
    ]
    svc.mt5.sync_positions_from_mt5 = AsyncMock(return_value={"closed_positions": closed_with_comments})
    svc.mt5.get_account_info = AsyncMock(return_value={"equity": 10500.0})
    svc.gate.update_risk_state = AsyncMock()
    with (
        patch.object(
            ps_mod,
            "get_session",
            side_effect=lambda: _make_cm_session(_FakeSession(scalar_vals=[MagicMock(id=55, confidence=0.8)] * 6)),
        ),
        patch(
            "monika.infrastructure.database.repositories.position_repository.PositionRepository",
            return_value=MagicMock(get_open_positions=AsyncMock(return_value=[]), update_volume=AsyncMock()),
        ),
    ):
        await svc.sync_positions()
        await asyncio.sleep(0)

    # Line 321: _handle_stop_loss_hit when auto_execute=False and pause_system_on_daily_sl_limit=False
    await svc._handle_stop_loss_hit(_FakeSession(scalar_vals=[5]), closed_with_comments[0])

    # Lines 647-648: reconcile_inflight_orders when stop_loss_price=None and params_json is invalid JSON
    bad_json_ord = MagicMock(
        id=77,
        client_order_id="c_bad_json",
        mt5_ticket=6001,
        symbol="EURUSD",
        direction="buy",
        order_type="market",
        requested_volume=0.1,
        requested_price=1.1000,
        stop_loss_price=None,
        take_profit_price=None,
        sl=None,
        tp=None,
        params_json="{invalid_json",
        analysis_id=1,
    )
    svc.broker_adapter = None
    svc.mt5.get_open_positions = AsyncMock(
        return_value=[
            {
                "ticket": 6001,
                "symbol": "EURUSD",
                "direction": "buy",
                "comment": "c_bad_json",
                "price_open": 1.1000,
                "volume": 0.1,
            }
        ]
    )
    svc.mt5.get_orders = AsyncMock(return_value=[])
    with (
        patch.object(ps_mod, "get_session", return_value=_make_cm_session(_FakeSession(rows_list=[[bad_json_ord]]))),
        patch.object(ps_mod.OrderLifecycleService, "transition_order_state", AsyncMock()),
    ):
        rec_bad_json = await svc.reconcile_inflight_orders()
        assert rec_bad_json["reconciled"] == 1

    # 5. analysis_preflight.py: 229-233, 414-418, 484-486, 586, 620, 622-623, 661-664, 686-687, 780-784, 814-815
    sizing_ok = SizingResult(
        symbol="EURUSD",
        direction="BUY",
        entry_price=1.1000,
        stop_loss=1.0950,
        take_profit=1.1100,
        account_equity=10000.0,
        risk_percent=1.0,
        risk_amount_usd=100.0,
        sl_distance_price=0.0050,
        sl_distance_pips=50.0,
        pip_value_per_lot=10.0,
        raw_lots=0.20,
        recommended_lots=0.20,
        rr_ratio=2.0,
        is_valid=True,
    )
    sizing_bad = SizingResult(**{**sizing_ok.__dict__, "is_valid": False, "rejection_reasons": ["r"]})
    verdict_ok = RiskVerdict(approved=True, symbol="EURUSD", proposed_lots=0.20, checks_passed=["ok"], checks_failed=[])
    verdict_no = RiskVerdict(
        approved=False,
        symbol="EURUSD",
        proposed_lots=0.20,
        checks_passed=[],
        checks_failed=["r"],
        rejection_reasons=["r"],
    )

    def _mk_an(**ov: object) -> MagicMock:
        d: dict[str, object] = {
            "id": 501,
            "symbol": "EURUSD",
            "decision": "buy",
            "confidence": 0.85,
            "confluence_score": 8,
            "stop_loss": 1.0950,
            "take_profit_1": 1.1100,
            "entry_zone": {"price": 1.1000, "order_type": "market"},
            "generated_at": datetime.now(UTC),
            "rationale": "post-release bullish setup. Strong momentum.",
            "key_evidence": '["ev1"]',
            "confluence_factors_json": None,
            "decision_source": "llm",
            "risk_multiplier": 1.0,
            "priced_in_score": 2.0,
            "specialist_biases_json": '{"tech": "bull"}',
            "debate_verdict": "buy",
            "debate_bull_thesis": "bull",
            "brief_id": None,
            "brief_price_at_analysis": 1.1000,
            "atr_at_analysis": 0.0050,
        }
        d.update(ov)
        return MagicMock(**d)

    # Lines 229-233: live graduation gate insufficient_paper_win_rate
    svc.dry_run = False
    r_winrate, _ = await svc._validate_analysis_preflight(
        _FakeSession(scalar_vals=[10, 5, 1]), _mk_an(), account_equity=10000.0
    )
    assert r_winrate is not None and "insufficient_paper_win_rate" in r_winrate.risk_checks_failed

    # Lines 414-418: BriefContaminationGuard raises (414-415) and brief_session.execute raises (417-418)
    svc.dry_run = True
    brief_ok = MagicMock(generated_at=datetime.now(UTC) - timedelta(minutes=5))
    with (
        patch.object(
            oe_mod, "get_session", side_effect=lambda: _make_cm_session(_FakeSession(scalar_vals=[brief_ok, None]))
        ),
        patch.object(svc, "_get_current_price", AsyncMock(return_value=(1.1000, False, 1.0))),
        patch(
            "monika.application.protocol.brief_contamination_guard.BriefContaminationGuard.check_magnitude_based_staleness",
            AsyncMock(side_effect=RuntimeError("mag err")),
        ),
        patch.object(svc.sizer, "calculate_with_session", AsyncMock(return_value=sizing_bad)),
        patch.object(svc.gate, "check", AsyncMock(return_value=verdict_no)),
        patch.object(svc, "_log_result", AsyncMock()),
    ):
        await svc._validate_analysis_preflight(_FakeSession(), _mk_an(brief_id=10), account_equity=10000.0)

    with (
        patch.object(oe_mod, "get_session", side_effect=lambda: _make_cm_session(_FakeSession(fail_execute=True))),
        patch.object(svc, "_get_current_price", AsyncMock(return_value=(1.1000, False, 1.0))),
        patch.object(svc.sizer, "calculate_with_session", AsyncMock(return_value=sizing_bad)),
        patch.object(svc.gate, "check", AsyncMock(return_value=verdict_no)),
        patch.object(svc, "_log_result", AsyncMock()),
    ):
        await svc._validate_analysis_preflight(_FakeSession(), _mk_an(brief_id=10), account_equity=10000.0)

    # Lines 484-486: MT5LiveAdapter with mt5.ensure_connected returning False
    svc.dry_run = False
    svc.settings["trading"]["force_live_override"] = True
    svc.broker_adapter = MT5LiveAdapter.__new__(MT5LiveAdapter)
    svc.mt5.ensure_connected = AsyncMock(return_value=False)
    r_mt5_disc, _ = await svc._validate_analysis_preflight(_FakeSession(), _mk_an(), account_equity=10000.0)
    assert r_mt5_disc is not None and "mt5_disconnected" in r_mt5_disc.risk_checks_failed

    # Lines 586 (JPY symbol), 620, 622-623 (mt5.get_current_price returns None), 661-664 (mt5.get_current_price raises)
    svc.broker_adapter = None
    svc.mt5.get_current_price = AsyncMock(return_value=None)
    with (
        patch.object(svc, "_get_current_price", AsyncMock(return_value=(150.00, False, 1.0))),
        patch.object(svc.sizer, "calculate_with_session", AsyncMock(return_value=sizing_bad)),
        patch.object(svc.gate, "check", AsyncMock(return_value=verdict_no)),
        patch.object(svc, "_log_result", AsyncMock()),
    ):
        await svc._validate_analysis_preflight(
            _FakeSession(),
            _mk_an(symbol="USDJPY", entry_zone={"price": 150.00}, stop_loss=149.00, take_profit_1=152.00),
            account_equity=10000.0,
        )

    svc.mt5.get_current_price = AsyncMock(side_effect=RuntimeError("spread fetch err"))
    with (
        patch.object(svc, "_get_current_price", AsyncMock(return_value=(150.00, False, 1.0))),
        patch.object(svc.sizer, "calculate_with_session", AsyncMock(return_value=sizing_bad)),
        patch.object(svc.gate, "check", AsyncMock(return_value=verdict_no)),
        patch.object(svc, "_log_result", AsyncMock()),
    ):
        await svc._validate_analysis_preflight(
            _FakeSession(),
            _mk_an(symbol="USDJPY", entry_zone={"price": 150.00}, stop_loss=149.00, take_profit_1=152.00),
            account_equity=10000.0,
        )

    # Lines 686-687 (entry_zone price invalid float), 780-784 (not dry_run and equity <= 0), 814-815 (VIX query raises)
    svc.mt5.get_current_price = AsyncMock(return_value={"bid": 1.1000, "ask": 1.1002})
    with (
        patch.object(svc, "_get_current_price", AsyncMock(return_value=(1.1000, False, 1.0))),
        patch.object(svc, "_get_equity", AsyncMock(return_value=0.0)),
    ):
        r_zero_eq, _ = await svc._validate_analysis_preflight(
            _FakeSession(), _mk_an(entry_zone={"price": "invalid_float"}), account_equity=None
        )
        assert r_zero_eq is not None and "live_equity_unavailable" in r_zero_eq.risk_checks_failed

    svc.dry_run = True
    with (
        patch.object(svc, "_get_current_price", AsyncMock(return_value=(1.1000, False, 1.0))),
        patch.object(svc.sizer, "calculate_with_session", AsyncMock(return_value=sizing_bad)),
        patch.object(svc.gate, "check", AsyncMock(return_value=verdict_no)),
        patch.object(svc, "_log_result", AsyncMock()),
    ):
        await svc._validate_analysis_preflight(
            _FakeSession(scalar_vals=[None, None, RuntimeError("vix err")]), _mk_an(), account_equity=10000.0
        )

    # 6. analysis_submission.py: 509, 597, 665, 721-722, 793-794, 809-810, 835-836, 865-866, 883, 887-888
    ctx_sub = PreflightContext(
        start=datetime.now(UTC),
        symbol="EURUSD",
        decision="buy",
        sizing=sizing_ok,
        verdict=verdict_ok,
        is_edge_signal=False,
        current_price=1.1000,
        order_type="market",
        entry_price=1.1000,
        sl_price=1.0950,
        tp_price=1.1100,
        account_equity=10000.0,
        is_post_release=False,
    )
    sub_an = _mk_an(id=601, specialist_biases_json="{bad_json")

    with patch.object(oe_mod, "transactional_advisory_lock", side_effect=_lock_true):
        svc.rate_throttler = None
        # Line 509: broker_adapter is None raises RuntimeError
        svc.broker_adapter = None
        svc.effect_gate = None
        with (
            patch.object(svc, "_count_open_positions", AsyncMock(return_value=0)),
            patch.object(svc, "_transition_order_state", AsyncMock()),
            pytest.raises(RuntimeError, match="Broker adapter is not initialized"),
        ):
            await svc._submit_and_record_order(_FakeSession(), sub_an, ctx_sub)

        # Lines 597 (partial fill), 721-722 (bad atr json), 793-794 (add_all raises), 809-810 (DecisionLogger raises), 835-836 (bad biases json), 865-866 (trajectory_logger raises), 883 (existing cfg), 887-888 (commit raises)
        svc.broker_adapter = MagicMock(
            submit_order=AsyncMock(
                return_value={"success": True, "ticket": 7001, "price": 1.1001, "executed_volume": 0.10}
            )
        )
        sess_sub_1 = _FakeSession(
            scalar_vals=[None, None, 0, 0, 0, 0, MagicMock(value_json="bad_json"), MagicMock(value="old_ts")]
        )
        setattr(sess_sub_1, "add_all", MagicMock(side_effect=RuntimeError("trade plan err")))
        commit_calls = 0

        async def _commit_fail_on_second() -> None:
            nonlocal commit_calls
            commit_calls += 1
            if commit_calls >= 2:
                raise RuntimeError("cfg commit err")

        setattr(sess_sub_1, "commit", _commit_fail_on_second)
        with (
            patch.object(svc, "_count_open_positions", AsyncMock(return_value=0)),
            patch.object(svc, "_transition_order_state", AsyncMock()),
            patch.object(svc, "_save_position", AsyncMock(return_value=11)),
            patch.object(svc, "_log_result", AsyncMock()),
            patch("monika.core.analytics.paper_tracker.PaperTracker.open_paper_trade", AsyncMock()),
            patch(
                "monika.application.analysis.memory.decision_log.DecisionLogger.log_decision",
                AsyncMock(side_effect=RuntimeError("dl err")),
            ),
            patch.object(svc.trajectory_logger, "log_trajectory", side_effect=RuntimeError("traj err")),
            patch("monika.application.graph.nodes.risk.proposal_notifier.send_execution_notification", AsyncMock()),
        ):
            res_sub_1 = await svc._submit_and_record_order(sess_sub_1, sub_an, ctx_sub)
            assert res_sub_1.executed is True

        # Line 665: orphan rollback when broker_adapter becomes None after submit_order
        svc.dry_run = False
        svc.mt5.close_position = AsyncMock(return_value={"success": True})

        async def _save_pos_clearing_adapter(**_k: object) -> None:
            svc.broker_adapter = None
            return None

        svc.broker_adapter = MagicMock(
            submit_order=AsyncMock(
                return_value={"success": True, "ticket": 7002, "price": 1.1000, "executed_volume": 0.20}
            )
        )
        with (
            patch.object(svc, "_count_open_positions", AsyncMock(return_value=0)),
            patch.object(svc, "_transition_order_state", AsyncMock()),
            patch.object(svc, "_save_position", _save_pos_clearing_adapter),
            pytest.raises(RuntimeError, match="Failed to persist position"),
        ):
            await svc._submit_and_record_order(_FakeSession(), _mk_an(id=603), ctx_sub)
        svc.mt5.close_position.assert_awaited_once_with(7002)

        # 7. paired_executor.py: 257, 363, 390-398, 412, 448-449
        p_an = MagicMock(
            id=701,
            symbol="EURUSD",
            decision="buy",
            entry_zone={"price": 1.1000},
            stop_loss=1.0950,
            take_profit=1.1100,
            take_profit_1=1.1100,
        )
        h_an = MagicMock(
            id=702,
            symbol="GBPUSD",
            decision="sell",
            entry_zone={"price": 1.2500},
            stop_loss=1.2550,
            take_profit=1.2400,
            take_profit_1=1.2400,
        )
        svc.mt5.get_symbol_info = AsyncMock(return_value={"contract_size": 100000.0})

        # Lines 257, 363 (adapter is not None and self.effect_gate is None) & lines 448-449 (orphan primary _save_position raises)
        svc.effect_gate = None
        svc.dry_run = False
        svc.broker_adapter = MagicMock(
            submit_order=AsyncMock(
                side_effect=[
                    {"success": True, "ticket": 8101, "price": 1.1000},
                    {"success": False, "error": "leg2 fail"},
                ]
            ),
            close_position=AsyncMock(return_value={"success": False, "error": "rb fail"}),
        )
        with (
            patch.object(svc.sizer, "calculate_with_session", AsyncMock(return_value=sizing_ok)),
            patch.object(svc.gate, "check", AsyncMock(return_value=verdict_ok)),
            patch.object(svc, "_count_open_positions", AsyncMock(return_value=0)),
            patch.object(svc, "_transition_order_state", AsyncMock()),
            patch.object(svc, "_save_position", AsyncMock(side_effect=RuntimeError("save orphan primary err"))),
            patch.object(oe_mod, "AgentNotifier", return_value=MagicMock(send_critical=AsyncMock())),
        ):
            r_pair_1 = await svc.execute_paired_analyses(_FakeSession(), p_an, h_an, "pg_123456", 10000.0)
            assert r_pair_1["success"] is False
            assert p_an.execution_status == "orphan_emergency"

        # Lines 390-398 (effect_gate raises AbortRequested on LEG2)
        svc.dry_run = True
        svc.broker_adapter = MagicMock(
            submit_order=AsyncMock(return_value={"success": True, "ticket": 8102, "price": 1.1000}),
            close_position=AsyncMock(return_value={"success": True, "error": None}),
        )
        gate_calls = 0

        async def _admit_abort_on_second(fn: object, **_kw: object) -> dict[str, object]:
            nonlocal gate_calls
            gate_calls += 1
            if gate_calls == 2:
                raise AbortRequested("leg2 abort")
            res = fn() if callable(fn) else None
            return await res if hasattr(res, "__await__") else {"success": True, "ticket": 8102}

        svc.effect_gate = MagicMock(admit=_admit_abort_on_second)
        with (
            patch.object(svc.sizer, "calculate_with_session", AsyncMock(return_value=sizing_ok)),
            patch.object(svc.gate, "check", AsyncMock(return_value=verdict_ok)),
            patch.object(svc, "_count_open_positions", AsyncMock(return_value=0)),
            patch.object(svc, "_transition_order_state", AsyncMock()),
        ):
            r_pair_2 = await svc.execute_paired_analyses(_FakeSession(), p_an, h_an, "pg_123456", 10000.0)
            assert r_pair_2["success"] is False
            assert p_an.execution_status == "rolled_back"

        # Line 412: adapter=None, LEG1 succeeds in dry_run, LEG2 fails in mt5.place_order and sets dry_run=True for rollback
        svc.broker_adapter = None
        svc.effect_gate = None
        svc.dry_run = True

        async def _transition_flip_dry_on_leg2(_sess: object, _ord: object, status: object, **kw: object) -> None:
            details = kw.get("details")
            if (
                getattr(status, "value", status) == "submitted"
                and isinstance(details, dict)
                and details.get("leg") == 2
            ):
                svc.dry_run = False

        async def _mt5_leg2_fail_flip_dry(*_a: object, **_k: object) -> dict[str, object]:
            svc.dry_run = True
            return {"success": False, "error": "mt5 leg2 fail"}

        svc.mt5.place_order = _mt5_leg2_fail_flip_dry
        with (
            patch.object(svc.sizer, "calculate_with_session", AsyncMock(return_value=sizing_ok)),
            patch.object(svc.gate, "check", AsyncMock(return_value=verdict_ok)),
            patch.object(svc, "_count_open_positions", AsyncMock(return_value=0)),
            patch.object(svc, "_transition_order_state", side_effect=_transition_flip_dry_on_leg2),
        ):
            r_pair_3 = await svc.execute_paired_analyses(_FakeSession(), p_an, h_an, "pg_123456", 10000.0)
            assert r_pair_3["success"] is False
            assert p_an.execution_status == "rolled_back"

        # 8. preplanned_executor.py: 80, 98-101, 147-148, 195-196, 217-218, 247-251, 275-285, 423-424, 613-614, 653, 693-694, 747, 762, 791, 813-829
        exec_preplanned_fn = getattr(svc, "execute_preplanned_order")
        assert (await exec_preplanned_fn(_FakeSession(), "EURUSD", "not_a_dict")).executed is False

        # Lines 147-148: sl_price <= 0
        assert (
            await svc.execute_preplanned_order(
                _FakeSession(), "EURUSD", {"decision": "buy", "stop_loss": 0.0, "take_profit": 1.1100}
            )
        ).executed is False

        with patch.object(svc, "_get_current_price", AsyncMock(return_value=(1.1000, False, 1.0))):
            # Lines 195-196 (BUY sl_price >= current_price), 217-218 (SELL sl_price <= current_price)
            assert (
                await svc.execute_preplanned_order(
                    _FakeSession(), "EURUSD", {"decision": "buy", "stop_loss": 1.1050, "take_profit": 1.1100}
                )
            ).executed is False
            assert (
                await svc.execute_preplanned_order(
                    _FakeSession(), "EURUSD", {"decision": "sell", "stop_loss": 1.0950, "take_profit": 1.0900}
                )
            ).executed is False

            # Lines 247-251: percentage slippage exceeded
            assert (
                await svc.execute_preplanned_order(
                    _FakeSession(),
                    "EURUSD",
                    {
                        "decision": "buy",
                        "entry_price": 1.0000,
                        "stop_loss": 1.0950,
                        "take_profit": 1.1100,
                        "max_slippage_pct": 0.1,
                    },
                )
            ).executed is False

            # Lines 275-285: pips slippage exceeded
            assert (
                await svc.execute_preplanned_order(
                    _FakeSession(),
                    "EURUSD",
                    {
                        "decision": "buy",
                        "entry_price": 1.0990,
                        "stop_loss": 1.0950,
                        "take_profit": 1.1100,
                        "max_slippage_pct": 50.0,
                        "max_slippage_pips": 2.0,
                    },
                )
            ).executed is False

            # Lines 423-424 (sizing.sl_distance_pips invalid float with lot_size > 0), 613-614 (TradingEventStore.emit raises), 653 (broker_adapter is None)
            sizing_bad_pips = MagicMock(
                symbol="EURUSD",
                direction="BUY",
                entry_price=1.1000,
                stop_loss=1.0950,
                take_profit=1.1100,
                account_equity=10000.0,
                risk_percent=1.0,
                risk_amount_usd=100.0,
                sl_distance_price=0.0050,
                sl_distance_pips="not_a_float",
                pip_value_per_lot=10.0,
                raw_lots=0.10,
                recommended_lots=0.10,
                rr_ratio=2.0,
                is_valid=True,
                rejection_reasons=[],
            )
            svc.broker_adapter = None
            svc.effect_gate = None
            with (
                patch.object(svc.sizer, "calculate_with_session", AsyncMock(return_value=sizing_bad_pips)),
                patch.object(svc.gate, "check", AsyncMock(return_value=verdict_ok)),
                patch.object(svc, "_count_open_positions", AsyncMock(return_value=0)),
                patch.object(svc, "_transition_order_state", AsyncMock()),
                patch(
                    "monika.infrastructure.database.event_store.TradingEventStore.emit",
                    AsyncMock(side_effect=RuntimeError("emit err")),
                ),
                pytest.raises(RuntimeError, match="Broker adapter is not initialized"),
            ):
                await svc.execute_preplanned_order(
                    _FakeSession(),
                    "EURUSD",
                    {
                        "decision": "buy",
                        "entry_price": 1.1000,
                        "stop_loss": 1.0950,
                        "take_profit": 1.1100,
                        "lot_size": 0.15,
                    },
                    account_equity=10000.0,
                )

            # Lines 693-694 (heal_and_reexecute raises) & line 791 (mt5_result success=False -> OrderStatus.REJECTED)
            svc.broker_adapter = MagicMock(
                submit_order=AsyncMock(return_value={"success": False, "error": "broker rej"})
            )
            with (
                patch.object(svc.sizer, "calculate_with_session", AsyncMock(return_value=sizing_ok)),
                patch.object(svc.gate, "check", AsyncMock(return_value=verdict_ok)),
                patch.object(svc, "_count_open_positions", AsyncMock(return_value=0)),
                patch.object(svc, "_transition_order_state", AsyncMock()),
                patch.object(svc, "_log_result", AsyncMock()),
                patch(
                    "monika.application.execution.service.self_healing_executor.MT5SelfHealingExecutor.heal_and_reexecute",
                    AsyncMock(side_effect=RuntimeError("heal crash")),
                ),
            ):
                r_prep_rej = await svc.execute_preplanned_order(
                    _FakeSession(),
                    "EURUSD",
                    {"decision": "buy", "entry_price": 1.1000, "stop_loss": 1.0950, "take_profit": 1.1100},
                    account_equity=10000.0,
                )
                assert r_prep_rej.executed is False

            # Lines 747 (exec_price=None, slippage_pips=None), 762 (partial fill 0 < exec_vol < req_vol), 813-829 (eff_analysis_id=None saves Position directly)
            svc.broker_adapter = MagicMock(
                submit_order=AsyncMock(
                    return_value={
                        "success": True,
                        "ticket": 8901,
                        "price": None,
                        "slippage_pips": None,
                        "executed_volume": 0.05,
                    }
                )
            )
            with (
                patch.object(svc.sizer, "calculate_with_session", AsyncMock(return_value=sizing_ok)),
                patch.object(svc.gate, "check", AsyncMock(return_value=verdict_ok)),
                patch.object(svc, "_count_open_positions", AsyncMock(return_value=0)),
                patch.object(svc, "_transition_order_state", AsyncMock()),
                patch.object(svc, "_log_result", AsyncMock()),
            ):
                r_prep_part = await svc.execute_preplanned_order(
                    _FakeSession(),
                    "EURUSD",
                    {"decision": "buy", "entry_price": 1.1000, "stop_loss": 1.0950, "take_profit": 1.1100},
                    analysis_id=None,
                    account_equity=10000.0,
                )
                assert r_prep_part.executed is True

    # 9. proposal_executor.py: 187-188 (pre_order waterfall returns (True, dict_plan))
    prop_ok = TradeProposal(
        symbol="EURUSD",
        direction="BUY",
        entry_price=1.1000,
        stop_loss=1.0950,
        take_profit=1.1100,
        lot_size=0.10,
        account_equity=10000.0,
        confidence=0.85,
        rationale="test",
        source_agent="agent",
        metadata={"analysis_id": 10},
    )
    svc.idempotency_guard = MagicMock(
        generate_key=MagicMock(return_value="k_dict"),
        acquire_lock=AsyncMock(return_value=(True, None)),
        release_lock=AsyncMock(),
        mark_completed=AsyncMock(),
        mark_failed=AsyncMock(),
    )
    fake_engine_dict = MagicMock(
        emit_waterfall=AsyncMock(
            return_value=(True, {"decision": "buy", "stop_loss": 1.0950, "take_profit": 1.1100, "lot_size": 0.10})
        ),
        emit_hook=AsyncMock(),
    )
    res_exec_ok = ExecutionResult(
        symbol="EURUSD",
        analysis_id=10,
        decision="buy",
        sizing=sizing_ok,
        risk_approved=True,
        risk_checks_passed=["all"],
        risk_checks_failed=[],
        risk_rejection_reasons=[],
        executed=True,
        mt5_ticket=9001,
        executed_price=1.1000,
        executed_lots=0.10,
        mt5_error=None,
        position_id=1,
        timestamp=datetime.now(UTC),
        elapsed_ms=5,
    )
    with (
        patch("monika.application.plugins.engine.engine.get_plugin_engine", return_value=fake_engine_dict),
        patch.object(svc, "execute_preplanned_order", AsyncMock(return_value=res_exec_ok)),
    ):
        assert (await svc.execute_proposal(_FakeSession(), prop_ok)).executed is True

    # 10. tranche_executor.py: 233, 267, 276
    t_an2 = MagicMock(
        id=901,
        symbol="EURUSD",
        decision="buy",
        current_price=1.1000,
        entry_price=1.1000,
        entry_zone={"price": 1.1000},
        stop_loss=1.0950,
        take_profit=1.1100,
        take_profit_1=1.1100,
        take_profit_2=1.1200,
    )
    with patch(
        "monika.application.execution.service.executors.tranche_executor.get_instrument_spec",
        return_value=MagicMock(lot_step=0.01, min_lot=0.01),
    ):
        # Line 233 (awaitable res from submit_order) & line 267 (dry_run=True rollback when leg 2 fails)
        async def _leg1_coro() -> dict[str, object]:
            return {"success": True, "ticket": 9501, "price": 1.1000}

        async def _leg2_coro() -> dict[str, object]:
            return {"success": False, "error": "leg2 dry fail"}

        svc.dry_run = True
        svc.broker_adapter = MagicMock(submit_order=AsyncMock(side_effect=[_leg1_coro(), _leg2_coro()]))
        with (
            patch.object(svc.sizer, "calculate_with_session", AsyncMock(return_value=sizing_ok)),
            patch.object(svc.gate, "check", AsyncMock(return_value=verdict_ok)),
            patch.object(svc, "_transition_order_state", AsyncMock()),
        ):
            r_tr_dry = await svc.execute_tranche_order(_FakeSession(), t_an2, account_equity=10000.0)
            assert r_tr_dry["success"] is False
            assert t_an2.execution_status == "rolled_back"

        # Line 276: live mode leg 2 fails, adapter has no close_position and self.mt5 is None
        svc.dry_run = False
        svc.mt5 = None
        svc.broker_adapter = MagicMock(
            spec=["submit_order"],
            submit_order=AsyncMock(
                side_effect=[
                    {"success": True, "ticket": 9502, "price": 1.1000},
                    {"success": False, "error": "leg2 live fail"},
                ]
            ),
        )
        with (
            patch.object(svc.sizer, "calculate_with_session", AsyncMock(return_value=sizing_ok)),
            patch.object(svc.gate, "check", AsyncMock(return_value=verdict_ok)),
            patch.object(svc, "_transition_order_state", AsyncMock()),
            patch.object(svc, "_save_position", AsyncMock(return_value=55)),
            patch.object(oe_mod, "AgentNotifier", return_value=MagicMock(send_critical=AsyncMock())),
        ):
            r_tr_no_close = await svc.execute_tranche_order(_FakeSession(), t_an2, account_equity=10000.0)
            assert r_tr_no_close["success"] is False
            assert t_an2.execution_status == "orphan_emergency"
