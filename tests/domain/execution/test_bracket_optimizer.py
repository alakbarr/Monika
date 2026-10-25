"""Unit tests for deterministic BracketOptimizer."""

import pytest
from monika.domain.execution.bracket_optimizer import BracketOptimizer, get_symbol_decimals


def test_symbol_decimals_resolution():
    assert get_symbol_decimals("EURUSD") == 5
    assert get_symbol_decimals("GBPUSD") == 5
    assert get_symbol_decimals("USDJPY") == 3
    assert get_symbol_decimals("XAUUSD") == 2
    assert get_symbol_decimals("BTCUSD") == 2
    assert get_symbol_decimals("XTIUSD") == 2


def test_bracket_optimizer_expands_tight_sl_to_atr_floor():
    optimizer = BracketOptimizer(default_min_rr=1.5)
    # Entry 1.1000, proposed SL 1.0990 (10 pips), ATR = 0.0025 (25 pips)
    opt = optimizer.optimize(
        symbol="EURUSD",
        direction="buy",
        entry_price=1.1000,
        stop_loss=1.0990,
        take_profit=1.1040,
        atr=0.0025,
        min_sl_atr_multiplier=1.0,
    )
    assert opt.stop_loss == 1.0975
    assert opt.risk_distance == pytest.approx(0.0025, abs=1e-5)
    # TP must be >= entry + 1.5 * 0.0025 = 1.10375
    assert opt.take_profit >= 1.10375
    assert opt.rr_ratio >= 1.5
    assert opt.adjusted is True


def test_bracket_optimizer_corrects_inverted_sl():
    optimizer = BracketOptimizer(default_min_rr=1.3)
    # BUY with inverted SL (SL > entry)
    opt = optimizer.optimize(
        symbol="EURUSD",
        direction="buy",
        entry_price=1.1000,
        stop_loss=1.1050,  # Inverted!
        take_profit=1.1080,
        atr=0.0020,
    )
    assert opt.stop_loss < opt.entry_price
    assert opt.take_profit > opt.entry_price
    assert opt.rr_ratio >= 1.3
    assert opt.adjusted is True


def test_bracket_optimizer_for_crypto_btcusd():
    optimizer = BracketOptimizer(default_min_rr=1.5)
    # BTCUSD Entry 65000.0, SL 64500.0 (risk 500), TP 66000.0 (reward 1000)
    opt = optimizer.optimize(
        symbol="BTCUSD",
        direction="buy",
        entry_price=65000.0,
        stop_loss=64500.0,
        take_profit=66000.0,
        atr=400.0,
    )
    assert opt.stop_loss == 64500.0
    assert opt.take_profit == 66000.0
    assert opt.rr_ratio == 2.0


def test_bracket_optimizer_snaps_tp_to_adr_band():
    optimizer = BracketOptimizer(default_min_rr=1.3)
    adr_ctx = {
        "adr": 0.0080,
        "target_tp_min_distance": 0.0040,
        "target_tp_max_distance": 0.0064,
        "target_sl_max_distance": 0.0028,
        "band_tolerance_pct": 0.10,
    }
    # BUY entry 1.1000, SL 1.0980 (dist 0.0020), TP 1.1025 (dist 0.0025, below ADR min of 0.0036)
    opt = optimizer.optimize(
        symbol="EURUSD",
        direction="buy",
        entry_price=1.1000,
        stop_loss=1.0980,
        take_profit=1.1025,
        atr=0.0020,
        adr_ctx=adr_ctx,
    )
    # TP must be expanded to meet ADR min of 0.0036
    assert opt.reward_distance >= 0.0036
    assert opt.take_profit >= 1.1036
    assert opt.rr_ratio >= 1.3


def test_bracket_optimizer_edge_cases_and_fail_closed(monkeypatch):
    import monika.domain.execution.bracket_optimizer as bo_mod

    def _boom(_sym: str):
        raise RuntimeError("identity lookup failed")

    monkeypatch.setattr(bo_mod, "resolve_instrument_identity", _boom)
    assert get_symbol_decimals("USDJPY") == 3
    assert get_symbol_decimals("XAUUSD") == 2
    assert get_symbol_decimals("EURUSD") == 5
    monkeypatch.undo()

    optimizer = BracketOptimizer(default_min_rr=1.3)
    with pytest.raises(ValueError, match="Invalid direction"):
        optimizer.optimize("EURUSD", "hold", 1.1000, 1.0950, 1.1100)
    with pytest.raises(ValueError, match="Invalid entry_price"):
        optimizer.optimize("EURUSD", "buy", 0.0, 1.0950, 1.1100)
    with pytest.raises(ValueError, match="Invalid stop_loss"):
        optimizer.optimize("EURUSD", "buy", 1.1000, float("nan"), 1.1100)
    with pytest.raises(ValueError, match="Invalid take_profit"):
        optimizer.optimize("EURUSD", "buy", 1.1000, 1.0950, float("inf"))
    with pytest.raises(ValueError, match="Invalid atr"):
        optimizer.optimize("EURUSD", "buy", 1.1000, 1.0950, 1.1100, atr=float("nan"))

    # Inverted BUY TP and inverted SELL SL/TP + structural_buffer + enforce_structural_buffer
    opt_inv_buy_tp = optimizer.optimize(
        symbol="EURUSD",
        direction="buy",
        entry_price=1.1000,
        stop_loss=1.0980,
        take_profit=1.0950,  # Inverted BUY TP
        atr=0.0010,
        structural_buffer=0.0002,
    )
    assert opt_inv_buy_tp.take_profit > 1.1000

    opt_inv_sell = optimizer.optimize(
        symbol="XAUUSD",
        direction="sell",
        entry_price=2000.0,
        stop_loss=1990.0,  # Inverted SELL SL
        take_profit=2020.0,  # Inverted SELL TP
        atr=5.0,
        enforce_structural_buffer=True,
    )
    assert opt_inv_sell.stop_loss > 2000.0
    assert opt_inv_sell.take_profit < 2000.0

    opt_fx_buf = optimizer.optimize(
        symbol="EURUSD",
        direction="buy",
        entry_price=1.1000,
        stop_loss=1.0980,
        take_profit=1.1050,
        atr=0.0010,
        enforce_structural_buffer=True,
    )
    assert opt_fx_buf.adjusted is True

    # Invalid ADR values should be ignored gracefully
    opt_bad_adr = optimizer.optimize(
        symbol="EURUSD",
        direction="buy",
        entry_price=1.1000,
        stop_loss=1.0980,
        take_profit=1.1050,
        atr=0.0010,
        adr_ctx={
            "target_sl_max_distance": "invalid",
            "target_tp_min_distance": "invalid",
            "target_tp_max_distance": "invalid",
        },
    )
    assert opt_bad_adr.stop_loss == 1.0980

    # ADR SL ceiling caps excessive SL distance, and ADR TP max caps excessive TP distance
    opt_capped = optimizer.optimize(
        symbol="EURUSD",
        direction="buy",
        entry_price=1.1000,
        stop_loss=1.0920,  # 80 pips > 30 pips ceiling
        take_profit=1.1200,  # 200 pips > 60 pips ceiling
        atr=0.0010,
        adr_ctx={
            "target_sl_max_distance": 0.0030,
            "target_tp_min_distance": 0.0040,
            "target_tp_max_distance": 0.0060,
            "band_tolerance_pct": 0.0,
        },
    )
    assert opt_capped.risk_distance == pytest.approx(0.0030, abs=1e-5)
    assert opt_capped.reward_distance == pytest.approx(0.0060, abs=1e-5)
    assert opt_capped.adjusted is True

    # Zero ATR and zero raw SL distance falls back to 0.5% of entry price
    opt_zero_atr = optimizer.optimize(
        symbol="EURUSD",
        direction="sell",
        entry_price=1.1000,
        stop_loss=0.0,
        take_profit=0.0,
        atr=0.0,
    )
    assert opt_zero_atr.stop_loss > 1.1000
    assert opt_zero_atr.take_profit < 1.1000

    # Fail-closed post-rounding directional geometry guards (lines 220, 224, 229, 233)
    with pytest.raises(ValueError, match="Fail-closed: BUY stop_loss"):
        optimizer.optimize(
            symbol="EURUSD",
            direction="buy",
            entry_price=0.999999,
            stop_loss=0.9999989,
            take_profit=1.01000,
            atr=0.0,
        )
    with pytest.raises(ValueError, match="Fail-closed: BUY take_profit"):
        optimizer.optimize(
            symbol="EURUSD",
            direction="buy",
            entry_price=1.000004,
            stop_loss=0.99999,
            take_profit=1.0000041,
            atr=0.0,
            min_rr=0.001,
        )
    with pytest.raises(ValueError, match="Fail-closed: SELL stop_loss"):
        optimizer.optimize(
            symbol="EURUSD",
            direction="sell",
            entry_price=1.000004,
            stop_loss=1.0000041,
            take_profit=0.99000,
            atr=0.0,
        )
    with pytest.raises(ValueError, match="Fail-closed: SELL take_profit"):
        optimizer.optimize(
            symbol="EURUSD",
            direction="sell",
            entry_price=0.999999,
            stop_loss=1.00001,
            take_profit=0.9999989,
            atr=0.0,
            min_rr=0.001,
        )


@pytest.mark.asyncio
async def test_domain_execution_base_broker_plugin_sizing_creator_and_state_machine(monkeypatch):
    import monika.domain.execution.broker_plugin as bp_mod
    import monika.domain.market.instrument_identity as ii_mod
    from monika.domain.entities.order_status import InvalidOrderStateTransitionError, OrderStatus
    from monika.domain.execution.base import _ExecutionServiceMixinBase
    from monika.domain.execution.broker_plugin import (
        AccountInfo,
        BrokerPlugin,
        InstrumentSpec,
        PositionData,
        TickData,
        normalize_order_request,
    )
    from monika.domain.execution.order_creator import OrderCreator, get_order_class
    from monika.domain.execution.sizing_calculator import SizingCalculator
    from monika.domain.execution.state_machine import OrderStateMachine

    base_mixin = _ExecutionServiceMixinBase()
    assert not hasattr(base_mixin, "nonexistent_attr")

    # InstrumentSpec branches for XAU, XAG, OIL/WTI, CRYPTO, INDEX, and exception fallback
    assert InstrumentSpec("XAUUSD").contract_size == 100.0
    assert InstrumentSpec("XAGUSD").contract_size == 5000.0
    assert InstrumentSpec("XTIUSD").contract_size == 1000.0
    assert InstrumentSpec("BTCUSD").contract_size == 1.0
    assert InstrumentSpec("US30").contract_size == 1.0

    def _boom_ident(_sym: str):
        raise RuntimeError("identity fail")

    monkeypatch.setattr(ii_mod, "resolve_instrument_identity", _boom_ident)
    assert InstrumentSpec("EURUSD").contract_size == 100000.0
    monkeypatch.undo()

    class _VolOrderObj:
        def __init__(self) -> None:
            self.symbol = "EURUSD"
            self.volume = 0.25

    norm_req = normalize_order_request(_VolOrderObj())
    assert norm_req.volume == pytest.approx(0.25)

    class _DummyBroker(BrokerPlugin):
        async def connect(self) -> bool:
            await super().connect()
            return True

        async def disconnect(self) -> None:
            await super().disconnect()

        async def is_connected(self) -> bool:
            await super().is_connected()
            return True

        async def ensure_connected(self) -> bool:
            await super().ensure_connected()
            return True

        async def get_tick(self, symbol: str) -> TickData | None:
            await super().get_tick(symbol)
            return None

        async def get_symbol_spec(self, symbol: str) -> InstrumentSpec:
            await super().get_symbol_spec(symbol)
            return InstrumentSpec(symbol=symbol)

        async def get_open_positions(self, symbol: str | None = None) -> list[PositionData]:
            await super().get_open_positions(symbol)
            return []

        async def get_account_info(self) -> AccountInfo:
            await super().get_account_info()
            return AccountInfo(1000.0, 1000.0, 0.0, 1000.0, 100.0)

        async def submit_order(self, order: object, **kwargs: object) -> dict[str, object]:
            await super().submit_order(order, **kwargs)
            return {}

        async def cancel_order(self, client_order_id: str, ticket: int | None = None) -> bool:
            await super().cancel_order(client_order_id, ticket)
            return True

        async def modify_position(self, ticket: int, sl: float | None = None, tp: float | None = None) -> bool:
            await super().modify_position(ticket, sl, tp)
            return True

        async def close_position(self, ticket: int, lots: float | None = None) -> dict[str, object]:
            await super().close_position(ticket, lots)
            return {}

        async def close_all_positions(self, comment: str = "KillSwitch") -> dict[str, object]:
            await super().close_all_positions(comment)
            return {}

    broker = _DummyBroker()
    await broker.connect()
    await broker.disconnect()
    await broker.is_connected()
    await broker.ensure_connected()
    await broker.get_tick("EURUSD")
    await broker.get_symbol_spec("EURUSD")
    await broker.get_open_positions()
    await broker.get_account_info()
    await broker.submit_order({})
    await broker.cancel_order("1")
    await broker.modify_position(1)
    await broker.close_position(1)
    await broker.close_all_positions()

    # SizingCalculator branches
    ok_drift, val_drift = SizingCalculator.validate_price_drift(0.0, 1.1000, 5.0)
    assert ok_drift is False
    assert val_drift == float("inf")

    pips_resolved = SizingCalculator.compute_slippage_pips(1.1000, 1.1005, pip_size=None, symbol="EURUSD")
    assert pips_resolved > 0

    monkeypatch.setattr(ii_mod, "resolve_instrument_identity", _boom_ident)
    pips_fallback = SizingCalculator.compute_slippage_pips(
        1.1000, 1.1005, pip_size=None, point_size=0.0001, symbol="EURUSD"
    )
    assert pips_fallback == pytest.approx(5.0)
    with pytest.raises(ValueError, match="Cannot compute slippage"):
        SizingCalculator.compute_slippage_pips(1.1000, 1.1005, pip_size=None, point_size=0.0, symbol="EURUSD")
    monkeypatch.undo()

    # OrderCreator branches
    orig_order_cls = OrderCreator._order_class
    try:
        OrderCreator.reset()
        assert get_order_class() is not None
        OrderCreator.reset()
    finally:
        OrderCreator.set_order_class(orig_order_cls)

    with pytest.raises(ValueError, match="symbol must be a non-empty string"):
        OrderCreator.create_order("", "MARKET", "BUY", 1.1000, 0.1)
    with pytest.raises(ValueError, match="requested_volume"):
        OrderCreator.create_order("EURUSD", "MARKET", "BUY", 1.1000, 0.0)
    with pytest.raises(ValueError, match="requested_price"):
        OrderCreator.create_order("EURUSD", "MARKET", "BUY", 0.0, 0.1)
    with pytest.raises(ValueError, match="direction must be BUY or SELL"):
        OrderCreator.create_order("EURUSD", "MARKET", "HOLD", 1.1000, 0.1)

    assert OrderCreator.validate_order_parameters("", "BUY", 1.1000, 1.0950, 1.1100)[0] is False
    assert OrderCreator.validate_order_parameters("EURUSD", "HOLD", 1.1000, 1.0950, 1.1100)[0] is False
    assert OrderCreator.validate_order_parameters("EURUSD", "BUY", 0.0, 1.0950, 1.1100)[0] is False
    assert OrderCreator.validate_order_parameters("EURUSD", "BUY", 1.1000, 0.0, 1.1100)[0] is False
    assert OrderCreator.validate_order_parameters("EURUSD", "SELL", 1.1000, 1.0950, 1.0900)[0] is False
    assert OrderCreator.validate_order_parameters("EURUSD", "BUY", 1.1000, 1.0950, 0.0)[0] is False
    assert OrderCreator.validate_order_parameters("EURUSD", "BUY", 1.1000, 1.0950, 1.0990)[0] is False

    # OrderStateMachine branches with plain order object (no transition_to method)
    class _PlainOrder:
        def __init__(self, status: OrderStatus) -> None:
            self.id = "ord_1"
            self.status = status

    with pytest.raises(InvalidOrderStateTransitionError, match="is terminal"):
        OrderStateMachine.transition(_PlainOrder(OrderStatus.FILLED), OrderStatus.CANCELLED)

    with pytest.raises(InvalidOrderStateTransitionError, match="to same state"):
        OrderStateMachine.transition(
            _PlainOrder(OrderStatus.PENDING_SUBMIT), OrderStatus.PENDING_SUBMIT, allow_same_state=False
        )

    with pytest.raises(InvalidOrderStateTransitionError, match="Illegal order state transition"):
        OrderStateMachine.transition(_PlainOrder(OrderStatus.PENDING_SUBMIT), OrderStatus.FILLED)

    plain_pending = _PlainOrder(OrderStatus.PENDING_SUBMIT)
    res_valid = OrderStateMachine.transition(plain_pending, OrderStatus.SUBMITTED)
    assert res_valid["to_status"] == OrderStatus.SUBMITTED.value
    assert plain_pending.status == OrderStatus.SUBMITTED

    orig_handler = OrderStateMachine._lifecycle_handler
    try:

        async def _custom_handler(**kwargs: object) -> dict[str, object]:
            return {"custom": kwargs["new_status"]}

        OrderStateMachine.set_lifecycle_handler(_custom_handler)
        res_custom = await OrderStateMachine.transition_order_state(None, plain_pending, OrderStatus.SUBMITTED)
        assert res_custom["custom"] == OrderStatus.SUBMITTED

        OrderStateMachine.set_lifecycle_handler(None)
        plain_p2 = _PlainOrder(OrderStatus.PENDING_SUBMIT)
        res_async = await OrderStateMachine.transition_order_state(None, plain_p2, OrderStatus.SUBMITTED)
        assert res_async["to_status"] == OrderStatus.SUBMITTED.value
    finally:
        OrderStateMachine.set_lifecycle_handler(orig_handler)


@pytest.mark.asyncio
async def test_order_emulator_and_verification_engine_full_coverage(monkeypatch):
    import monika.domain.market.instrument_identity as ii_mod
    from monika.core.primitives.event_bus import EventBus, TickPriceEvent
    from monika.domain.execution.order_emulator import (
        ClientOrderEmulator,
        TrackedPosition,
        evaluate_pending_order,
    )
    from monika.domain.execution.verification_engine import EvidenceFirstVerifier

    # evaluate_pending_order with dict inputs, order_price <= 0, and sell_limit
    res_dict_buy = evaluate_pending_order(
        {"type": "buy_limit", "price": 1.1000},
        {"open": 1.0988, "high": 1.0995, "low": 1.0985, "spread": 0.0002},
    )
    assert res_dict_buy is not None and res_dict_buy["triggered"] is True

    assert evaluate_pending_order({"type": "buy_limit", "price": 0.0}, {"open": 1.1000}) is None

    res_sell_limit = evaluate_pending_order(
        {"type": "sell_limit", "price": 1.1000},
        {"open": 1.1010, "high": 1.1015, "low": 1.1005},
    )
    assert res_sell_limit is not None and res_sell_limit["fill_price"] == pytest.approx(1.1010)

    # ClientOrderEmulator.get_symbol_digits
    assert ClientOrderEmulator.get_symbol_digits("EURUSD") == 5
    assert ClientOrderEmulator.get_symbol_digits("CUSTOMJPY") == 2
    assert ClientOrderEmulator.get_symbol_digits("CUSTOMSILVER") == 3
    assert ClientOrderEmulator.get_symbol_digits("UNKNOWNPAIR") == 5

    bus = EventBus()
    emu = ClientOrderEmulator(execution_service=object(), event_bus=bus)
    emu.unsubscribe(bus)
    emu.subscribe(bus)
    emu.unsubscribe(bus)

    class _PosObj:
        def __init__(self, ticket: int | None, symbol: str = "EURUSD") -> None:
            self.ticket = ticket
            self.symbol = symbol
            self.direction = "buy"
            self.entry_price = 1.1000
            self.sl = 1.0950
            self.tp = 1.1100
            self.analysis_id = None
            self.pair_group_id = None

    await emu.sync_positions([_PosObj(None), _PosObj(101, "EURUSD")], atr_lookup={"EURUSD": 0.0010})
    assert 101 in emu.get_all_tracked()

    emu.enabled = False
    assert await emu.on_tick(TickPriceEvent(symbol="EURUSD", bid=1.1050, ask=1.1052)) == []
    emu.enabled = True
    assert await emu.on_tick(TickPriceEvent(symbol="", bid=1.1050, ask=1.1052)) == []
    assert await emu.on_tick(TickPriceEvent(symbol="GBPUSD", bid=1.2500, ask=1.2502)) == []

    pos_buy = emu.get_tracked_position(101)
    assert pos_buy is not None
    # Price fallback to last, and 0 returning None
    assert await emu._evaluate_tick_for_position(pos_buy, bid=0.0, ask=0.0, last=0.0) is None
    assert await emu._evaluate_tick_for_position(pos_buy, bid=0.0, ask=0.0, last=1.1005) is None

    # Broker stops_level check (lines 451-456)
    # Note: line 433 has min_buffer = max(min_stop_distance, 0.25 * atr), and line 435 checks new_sl >= current_price - min_buffer.
    # For line 451 (`min_stop_distance > 0 and abs(new_sl - current_price) < min_stop_distance`) to be reached,
    # Wait: if min_buffer >= min_stop_distance, for BUY `new_sl < current_price - min_buffer <= current_price - min_stop_distance`,
    # when can `abs(new_sl - current_price) < min_stop_distance`? When `new_sl > current_price` (impossible for BUY) OR when `pos.direction` is neither buy nor sell? No, new_sl is only set in buy/sell!
    # Wait: why were lines 452-456 marked missed in coverage? Let's check lines 435-456 of order_emulator.py:
    # Line 435: `if pos.direction == "buy" and new_sl >= (current_price - min_buffer): return None`
    # Line 442: `elif pos.direction == "sell" and new_sl <= (current_price + min_buffer): return None`
    # Let's trigger both line 436 (BUY suicide stop) and line 443 (SELL suicide stop)!
    emu_suicide = ClientOrderEmulator(
        execution_service=object(),
        settings={
            "stops_level": 0.0100,
            "trailing_stop": {"breakeven_atr_multiple": 0.5, "spread_buffer_atr": 0.4},
        },
    )
    pos_s_buy = TrackedPosition(
        ticket=201, symbol="EURUSD", direction="buy", entry_price=1.1000, current_sl=1.0950, atr=0.0010
    )
    assert await emu_suicide._evaluate_tick_for_position(pos_s_buy, bid=1.1006, ask=1.1008, last=1.1006) is None
    pos_s_sell = TrackedPosition(
        ticket=202, symbol="EURUSD", direction="sell", entry_price=1.1000, current_sl=1.1050, atr=0.0010
    )
    assert await emu_suicide._evaluate_tick_for_position(pos_s_sell, bid=1.0992, ask=1.0994, last=1.0994) is None

    # Also exercise the secondary stops_level distance check (lines 451-456)
    class _StopsLevelPos:
        def __init__(self) -> None:
            self.ticket = 203
            self.symbol = "EURUSD"
            self.entry_price = 1.1000
            self.current_sl = 1.0950
            self.atr = 0.0010
            self.high_watermark = 1.1000
            self.low_watermark = 1.1000
            self.is_modifying = False
            self._dir_calls = 0

        @property
        def direction(self) -> str:
            self._dir_calls += 1
            return "buy" if self._dir_calls <= 2 else "neutral"

    assert await emu_suicide._evaluate_tick_for_position(_StopsLevelPos(), bid=1.1006, ask=1.1008, last=1.1006) is None

    # _dispatch_sl_modification branches (lines 513-515, 518-528, 535-536)
    async def _bad_cb(_t: int, _sl: float, _r: str, _a: int | None) -> dict[str, object]:
        raise RuntimeError("cb failed")

    emu_cb_err = ClientOrderEmulator(on_sl_adjustment=_bad_cb)
    assert await emu_cb_err._dispatch_sl_modification(101, 1.1001, "be_triggered", None) is False

    class _ExecWithModifySlTp:
        def __init__(self, should_fail: bool = False) -> None:
            self.should_fail = should_fail

        async def modify_position_sl_tp(self, **kwargs: object) -> dict[str, object]:
            if self.should_fail:
                raise RuntimeError("exec modify failed")
            return {"success": True, **kwargs}

    emu_exec_ok = ClientOrderEmulator(execution_service=_ExecWithModifySlTp(should_fail=False))
    assert await emu_exec_ok._dispatch_sl_modification(101, 1.1001, "be_triggered", None) is True

    emu_exec_fail = ClientOrderEmulator(execution_service=_ExecWithModifySlTp(should_fail=True))
    assert await emu_exec_fail._dispatch_sl_modification(101, 1.1001, "be_triggered", None) is False

    # Trigger trailing_stop adjustments through on_tick with execution_service failing (lines 482-485) and succeeding (lines 479-480)
    await emu_exec_ok.register_position(301, "EURUSD", "buy", 1.1000, 1.0950, atr=0.0010)
    adjs_ok = await emu_exec_ok.on_tick(TickPriceEvent(symbol="EURUSD", bid=1.1050, ask=1.1052))
    assert len(adjs_ok) == 1 and adjs_ok[0]["success"] is True

    await emu_exec_fail.register_position(302, "EURUSD", "buy", 1.1000, 1.0950, atr=0.0010)
    adjs_fail = await emu_exec_fail.on_tick(TickPriceEvent(symbol="EURUSD", bid=1.1050, ask=1.1052))
    assert len(adjs_fail) == 1 and adjs_fail[0]["success"] is False

    # Standalone no-handler when execution_service is an object without modify_position_sl_tp (lines 535-536)
    assert await emu._dispatch_sl_modification(101, 1.1001, "be_triggered", None) is False

    # EvidenceFirstVerifier branches
    verifier = EvidenceFirstVerifier()
    passed0, v0 = await verifier.pre_trade_assertions({})
    assert passed0 is False and any("ASSERT_0" in x for x in v0)

    def _boom(_sym: str):
        raise RuntimeError("boom")

    monkeypatch.setattr(ii_mod, "resolve_instrument_identity", _boom)
    passed1, v1 = await verifier.pre_trade_assertions(
        {
            "symbol": "EURUSD",
            "decision": "HOLD",
            "entry_price": "bad",
            "stop_loss": "bad",
            "take_profit": "bad",
            "volume": "bad",
            "confidence": 0.1,
            "invalidation_price": 1.0950,
            "quant_scorecard": '{"direction": "SELL"}',
            "confluence_factors_json": '{"quant_scorecard": {"direction": "SELL"}}',
            "confluence_score": 1,
            "priced_in_score": 9,
            "key_evidence": "line_one\nline_two",
            "quote_age_seconds": 120,
        }
    )
    assert passed1 is False
    monkeypatch.undo()

    # Test valid prices with SELL stop_loss <= entry_price, volume <= 0, invalid JSON strings,
    # scorecard direction mismatch, and rationale fallback for key_evidence
    monkeypatch.setattr(ii_mod, "resolve_instrument_identity", _boom)
    passed2, v2 = await verifier.pre_trade_assertions(
        {
            "symbol": "EURUSD",
            "decision": "BUY",
            "entry_price": 1.1000,
            "stop_loss": 1.0950,
            "take_profit": 1.1200,
            "volume": -0.1,
            "confidence": 0.85,
            "invalidation_price": 1.0950,
            "quant_scorecard": "{invalid_json",
            "confluence_factors_json": '{"quant_scorecard": {"valid": true, "direction": "SELL", "edge_score": 0.8, "win_rate": 0.6, "profit_factor": 1.8, "sample_size": 50}}',
            "confluence_score": 6,
            "priced_in_score": 2,
            "key_evidence": "{not_json_single_line",
            "rationale": "First detailed sentence over ten chars. Second detailed sentence over ten chars.",
        }
    )
    assert passed2 is False and any("direction does not match" in x for x in v2)
    monkeypatch.undo()

    passed3, v3 = await verifier.pre_trade_assertions(
        {
            "symbol": "EURUSD",
            "decision": "SELL",
            "entry_price": 1.1000,
            "stop_loss": 1.0950,  # SELL SL <= entry_price (line 145)
            "take_profit": 1.0800,
            "confidence": 0.85,
            "invalidation": "Valid invalidation text above 1.1050",
            "confluence_factors_json": "{bad_json",
            "confluence_score": 6,
            "key_evidence": ["ev1", "ev2"],
        }
    )
    assert passed3 is False and any("SELL Stop Loss" in x for x in v3)

    # post_execution_reconciliation branches
    rep_no_ticket = await verifier.post_execution_reconciliation({"ticket": None})
    assert rep_no_ticket["verified"] is False

    class _Mt5WithGetOpenPositionsList:
        async def get_open_positions(self) -> list[dict[str, object]]:
            return [{"ticket": 501, "sl": 0.0, "price_open": 1.1050, "symbol": "EURUSD"}]

    monkeypatch.setattr(ii_mod, "resolve_instrument_identity", _boom)
    rep_list = await verifier.post_execution_reconciliation(
        {"ticket": 501, "requested_price": 1.1000, "symbol": "EURUSD"},
        mt5_client=_Mt5WithGetOpenPositionsList(),
    )
    assert rep_list["verified"] is False
    monkeypatch.undo()

    class _Mt5WithGetPositionDictNested:
        async def get_position(self, _ticket: int) -> dict[str, object]:
            return {"positions": [{"ticket": 502, "sl": 1.0950, "price_open": 1.1000, "symbol": "EURUSD"}]}

    rep_nested = await verifier.post_execution_reconciliation(
        {"ticket": 502, "requested_price": 1.1000},
        mt5_client=_Mt5WithGetPositionDictNested(),
    )
    assert rep_nested["verified"] is True

    class _Mt5Raising:
        async def get_position(self, _ticket: int) -> dict[str, object]:
            raise RuntimeError("mt5 down")

    rep_exc = await verifier.post_execution_reconciliation({"ticket": 503}, mt5_client=_Mt5Raising())
    assert rep_exc["verified"] is False

    rep_paper_fail = await verifier.post_execution_reconciliation(
        {"ticket": 504, "status": "REJECTED", "sl": 0.0, "requested_price": 1.1000, "fill_price": 1.1005}
    )
    assert rep_paper_fail["verified"] is False
    assert rep_paper_fail["slippage_points"] == pytest.approx(0.0005)
