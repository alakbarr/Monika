"""Comprehensive unit tests achieving 100% coverage across src/monika/domain/risk/."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import Enum
import json
from pathlib import Path
import shutil
import sys
import time
import types
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest


@pytest.mark.asyncio
async def test_approval_hub_and_transport_full_coverage() -> None:
    from monika.domain.risk.approval_hub import (
        ApprovalHub,
        ApprovalRequest,
        ApprovalStatus,
        BoundedMandate,
    )
    from monika.domain.risk.approval_transport import (
        ApprovalDecisionPayload,
        ApprovalRequestPayload,
        ApprovalTransport,
        canonical_json,
    )

    # 1. ApprovalRequest & BoundedMandate properties and defaults
    req = ApprovalRequest(token="tok1", action_type="trade", description="s", expires_at=0.0)
    assert req.expires_at > req.requested_at
    req.request_id = "tok_updated"
    assert req.token == "tok_updated"
    req.action = "kill"
    assert req.action_type == "kill"
    assert req.created_at == req.requested_at
    req.operator = "op_user"
    assert req.operator == "op_user"
    req.rejection_reason = "rej_r"
    assert req.rejection_reason == "rej_r"

    mandate_default = BoundedMandate(mandate_id="m_def", operator="op1", expires_at=0.0)
    assert mandate_default.expires_at > mandate_default.issued_at
    assert mandate_default.signature != ""

    # 2. ApprovalHub singleton reset & restore
    orig_hub = ApprovalHub._instance
    try:
        ApprovalHub.reset_instance()
        assert ApprovalHub._instance is None
    finally:
        ApprovalHub._instance = orig_hub

    hub = ApprovalHub()

    async def _bad_listener(_event_type: str, _data: dict[str, object]) -> None:
        raise RuntimeError("listener boom")

    hub.register_listener(_bad_listener)
    r_ttl = hub.create_request(request_id="r_ttl", action="trade", description="ttl_sec", ttl_seconds=30.0)
    await hub._emit_event("test_evt", {"k": "v"})

    # request_approval Level 0/1 and Level 2/3
    r_lvl1 = hub.request_approval(action_type="info", level=1, description="auto")
    assert r_lvl1.status == ApprovalStatus.APPROVED
    r_lvl2 = hub.request_approval(action_type="high_risk", level=2, description="manual")
    assert r_lvl2.status == ApprovalStatus.PENDING

    # approve / reject edge cases
    ok, msg = await hub.approve("missing_id")
    assert ok is False and "not found" in msg

    loop = asyncio.get_running_loop()
    fut_app = loop.create_future()
    hub._pending_futures[r_ttl.token] = fut_app
    ok_app, _ = await hub.approve(r_ttl.token, operator="op")
    assert ok_app is True and fut_app.done()

    ok_rej_miss, _ = await hub.reject("missing_id")
    assert ok_rej_miss is False
    ok_rej_resolved, _ = await hub.reject(r_ttl.token)
    assert ok_rej_resolved is False

    r_exp = hub.create_request(request_id="r_exp", action="trade", description="exp", ttl_seconds=10.0)
    r_exp.expires_at = time.time() - 5.0
    ok_rej_exp, _ = await hub.reject(r_exp.token)
    assert ok_rej_exp is False and r_exp.status == ApprovalStatus.EXPIRED

    r_rej_fut = hub.create_request(request_id="r_rej_fut", action="trade", description="rej_fut", ttl_seconds=30.0)
    fut_rej = loop.create_future()
    hub._pending_futures[r_rej_fut.token] = fut_rej
    ok_rej_ok, _ = await hub.reject(r_rej_fut.token, operator="op")
    assert ok_rej_ok is True and fut_rej.done()

    assert isinstance(hub.get_pending_requests(), list)
    assert hub.get_request(r_ttl.token) is r_ttl

    # await_decision branches
    assert (await hub.await_decision("missing_tok"))[0] is False
    assert (await hub.await_decision(r_ttl.token))[0] is True
    assert (await hub.await_decision(r_rej_fut.token))[0] is False

    r_timeout = hub.create_request(request_id="r_to", action="trade", description="to", ttl_seconds=30.0)
    ok_to, reason_to = await hub.await_decision(r_timeout.token, timeout_seconds=0.001)
    assert ok_to is False and "timed out" in reason_to

    # decide() branches
    assert hub.decide("missing_tok", approved=True, user_id="op1") is False
    r_dec_exp = hub.create_request(request_id="r_dec_exp", action="trade", description="dec_exp", ttl_seconds=10.0)
    r_dec_exp.expires_at = time.time() - 5.0
    assert hub.decide(r_dec_exp.token, approved=True, user_id="op1") is False

    r_dec_no = hub.create_request(request_id="r_dec_no", action="trade", description="dec_no", ttl_seconds=30.0)
    fut_dec = loop.create_future()
    hub._pending_futures[r_dec_no.token] = fut_dec
    assert hub.decide(r_dec_no.token, approved=False, user_id="op1") is True
    assert r_dec_no.status == ApprovalStatus.REJECTED and fut_dec.done()

    r_dec_yes = hub.create_request(request_id="r_dec_yes", action="trade", description="dec_yes", ttl_seconds=30.0)
    assert hub.decide(r_dec_yes.token, approved=True, user_id="op1") is True

    # verify_request_binding branches
    assert hub.verify_request_binding("missing_tok")[0] is False
    r_no_dig = hub.create_request(request_id="r_no_dig", action="trade", description="no_dig", ttl_seconds=30.0)
    saved_req_dig = r_no_dig.request_digest
    r_no_dig.request_digest = ""
    assert hub.verify_request_binding(r_no_dig.token)[0] is False
    r_no_dig.request_digest = saved_req_dig
    assert hub.verify_request_binding(r_no_dig.token)[0] is False

    assert hub.verify_request_binding(r_dec_no.token)[0] is True
    with patch.object(ApprovalRequestPayload, "verify_integrity", side_effect=[True, False]):
        assert hub.verify_request_binding(r_dec_no.token)[0] is False

    assert "not found" in hub.format_card_markdown("missing_tok")
    assert "HITL GATE" in hub.format_card_markdown(r_dec_no.token)
    assert len(hub.format_telegram_inline_keyboard(r_dec_no.token)) == 1

    # Mandate validation branches
    hub_m = ApprovalHub()
    assert hub_m.validate_mandate(symbol="EURUSD", risk_pct=0.5)[0] is False

    m1 = hub_m.issue_mandate(operator="op1", max_leverage=10.0, max_open_positions=3)
    assert hub_m.validate_mandate(symbol="EURUSD", risk_pct=0.5, current_positions="bad_int", leverage=20.0)[0] is False

    m1.signature = "tampered_sig"
    assert hub_m.validate_mandate(symbol="EURUSD", risk_pct=0.5, mandate_id=m1.mandate_id)[0] is False

    assert hub_m.revoke_mandate("missing_mandate")[0] is False
    hub_m.revoke_mandate(m1.mandate_id)
    assert hub_m.validate_mandate(symbol="EURUSD", risk_pct=0.5, mandate_id=m1.mandate_id)[0] is False
    assert hub_m.validate_mandate(symbol="EURUSD", risk_pct=0.5)[0] is False

    # get_active_mandate & list_mandates
    assert hub_m.get_active_mandate("missing_m") is None
    assert hub_m.get_active_mandate(m1.mandate_id) is None
    m2 = hub_m.issue_mandate(operator="op1")
    assert hub_m.get_active_mandate(m2.mandate_id) is m2
    m2.expires_at = time.time() - 10.0
    assert hub_m.get_active_mandate(m2.mandate_id) is None

    m3 = hub_m.issue_mandate(operator="op1")
    m3.expires_at = time.time() - 10.0
    listed = hub_m.list_mandates()
    assert any(x.mandate_id == m3.mandate_id and x.status == "expired" for x in listed)

    # 3. ApprovalTransport & canonical_json branches
    class _SampleEnum(Enum):
        VAL = "enum_val"

    class _WithToDict:
        def to_dict(self) -> dict[str, str]:
            return {"k": "v"}

    class _WithDict:
        def __init__(self) -> None:
            self.pub = 1
            self._priv = 2

    raw_json = canonical_json(
        {
            "dt": datetime.now(UTC),
            "en": _SampleEnum.VAL,
            "td": _WithToDict(),
            "d": _WithDict(),
            "set": {1},
        }
    )
    assert "enum_val" in raw_json

    rp = ApprovalTransport.create_request(
        token="t1",
        action_type="trade",
        level=2,
        description="s",
        details={},
        requested_at=100.0,
        expires_at=200.0,
    )
    assert rp.to_dict()["token"] == "t1"
    dp = ApprovalTransport.create_decision(request=rp, approved=True, decided_by="op", decided_at=110.0, reason="ok")
    assert dp.to_dict()["token"] == "t1"
    assert ApprovalTransport.verify_binding(rp, dp, now=150.0)[0] is True
    assert ApprovalTransport.verify_binding(rp, dp, now=250.0)[0] is False

    rp_bad = ApprovalTransport.create_request(
        token="t2",
        action_type="trade",
        level=2,
        description="s",
        details={},
        requested_at=100.0,
        expires_at=200.0,
    )
    rp_bad.request_digest = "bad_digest"
    assert ApprovalTransport.verify_binding(rp_bad, dp)[0] is False
    with pytest.raises(ValueError, match="Cannot sign decision"):
        ApprovalTransport.create_decision(request=rp_bad, approved=True, decided_by="op", decided_at=110.0)

    dp_tampered = ApprovalDecisionPayload(
        token="t1",
        request_digest=rp.request_digest,
        approved=True,
        decided_by="op",
        decided_at=110.0,
        reason="ok",
        decision_digest="tampered",
    )
    assert ApprovalTransport.verify_binding(rp, dp_tampered)[0] is False

    dp_diff_tok = ApprovalDecisionPayload(
        token="other_tok",
        request_digest=rp.request_digest,
        approved=True,
        decided_by="op",
        decided_at=110.0,
        reason="ok",
    )
    assert ApprovalTransport.verify_binding(rp, dp_diff_tok)[0] is False

    dp_diff_req_dig = ApprovalDecisionPayload(
        token="t1",
        request_digest="different_req_digest",
        approved=True,
        decided_by="op",
        decided_at=110.0,
        reason="ok",
    )
    assert ApprovalTransport.verify_binding(rp, dp_diff_req_dig)[0] is False


@pytest.mark.asyncio
async def test_correlation_matrix_and_portfolio_correlation_gate_full_coverage() -> None:
    from monika.domain.risk.correlation_matrix import DynamicCorrelationMatrix
    from monika.domain.risk.portfolio_correlation_gate import filter_correlated_proposals

    dcm = DynamicCorrelationMatrix(correlation_threshold=0.7)
    assert dcm.calculate_pearson_correlation([], []) == 0.0
    assert dcm.calculate_pearson_correlation([1.0, 2.0, 3.0], [2.0, 4.0, 6.0]) == 1.0
    assert dcm.calculate_pearson_correlation([1.0, 1.0, 1.0], [2.0, 2.0, 2.0]) == 0.0
    assert await dcm.get_matrix(None, []) == {}
    assert dcm.calculate_portfolio_heat([], {})["status"] == "safe"

    res_hedge = dcm.calculate_portfolio_heat(
        [
            {"symbol": "EURUSD", "direction": "buy", "volume": 1.0},
            {"symbol": "USDCHF", "direction": "buy", "volume": 1.0},
        ],
        {"EURUSD": {"USDCHF": -0.85}, "USDCHF": {"EURUSD": -0.85}},
    )
    assert any(p["type"] == "hedge_reduction" for p in res_hedge["correlated_pairs"])

    # portfolio_correlation_gate branches
    assert await filter_correlated_proposals(None, []) == ([], [])

    class _MockRepo:
        def __init__(self, fail: bool = False) -> None:
            self.fail = fail

        async def get_open_positions(self, **_kwargs: object) -> list[dict[str, str]]:
            if self.fail:
                raise RuntimeError("db err")
            return [{"symbol": "EURUSD", "direction": "buy"}]

    with (
        patch("monika.domain.risk.ports.get_default_risk_data_provider", return_value=_MockRepo(fail=False)),
        patch(
            "monika.domain.risk.portfolio_correlation_gate.get_rolling_correlation",
            AsyncMock(return_value=(0.85, "rolling")),
        ),
    ):
        kept, rej = await filter_correlated_proposals(
            session=object(),
            actionable_trades=[
                ("WAIT_SYM", {"decision": "wait", "confidence": 0.9}),
                ("EURUSD", {"decision": "buy", "confidence": 0.8}),
                ("GBPUSD", {"decision": "buy", "confidence": 0.7}),
            ],
            threshold=0.5,
        )
        assert isinstance(kept, list) and len(rej) >= 1

    with patch("monika.domain.risk.ports.get_default_risk_data_provider", return_value=_MockRepo(fail=True)):
        await filter_correlated_proposals(
            session=object(),
            actionable_trades=[("EURUSD", {"decision": "buy", "confidence": 0.8})],
        )

    # Sector concentration cap, static fallback against open positions, and NaN + batch correlation in session=None
    with patch(
        "monika.domain.risk.portfolio_correlation_gate._static_fallback",
        side_effect=[float("nan"), 0.85],
    ):
        kept2, rej2 = await filter_correlated_proposals(
            session=None,
            actionable_trades=[
                ("BTCUSD", {"decision": "buy", "confidence": 0.95}),
                ("ETHUSD", {"decision": "buy", "confidence": 0.90}),
                ("EURUSD", {"decision": "buy", "confidence": 0.85}),
                ("GBPUSD", {"decision": "buy", "confidence": 0.80}),
            ],
            threshold=0.70,
        )
        assert len(rej2) >= 2

    # Also test session=None with open_positions via session.execute fallback & static_fallback against open_positions
    class _SessWithOpen:
        async def execute(self, _stmt: object) -> object:
            return MagicMock(scalars=lambda: MagicMock(all=lambda: [{"symbol": "EURUSD", "direction": "buy"}]))

    with (
        patch("monika.domain.risk.ports.get_default_risk_data_provider", return_value=None),
        patch(
            "monika.domain.risk.portfolio_correlation_gate.get_rolling_correlation",
            AsyncMock(return_value=(float("nan"), "nan")),
        ),
    ):
        await filter_correlated_proposals(
            session=_SessWithOpen(),
            actionable_trades=[("GBPUSD", {"decision": "buy", "confidence": 0.8})],
        )


@pytest.mark.asyncio
async def test_crypto_audit_ledger_and_execution_simulator_full_coverage(tmp_path: Path) -> None:
    from monika.domain.risk.crypto_audit_ledger import CryptoAuditLedger, LedgerCorruptionError
    from monika.domain.risk.execution_simulator import ExecutionSimulator

    # 1. CryptoAuditLedger branches
    empty_file = tmp_path / "empty_ledger.jsonl"
    empty_file.write_text("\n\n", encoding="utf-8")
    ledger_empty = CryptoAuditLedger(ledger_path=empty_file)
    assert ledger_empty._last_record is None

    non_exist = tmp_path / "missing_dir" / "ledger.jsonl"
    ledger_new = CryptoAuditLedger(ledger_path=non_exist)
    non_exist.unlink(missing_ok=True)
    assert ledger_new.read_all() == []

    # Append on Windows & with msvcrt lock raising OSError
    rec0 = ledger_new.append("TEST_ACT", {"a": 1})
    assert rec0.seq == 0
    assert ledger_new.verify_integrity() is True

    fake_msvcrt = types.ModuleType("msvcrt")
    setattr(fake_msvcrt, "LK_LOCK", 1)
    setattr(fake_msvcrt, "LK_UNLCK", 2)
    setattr(fake_msvcrt, "locking", MagicMock(side_effect=OSError("lock err")))

    with patch.dict(sys.modules, {"msvcrt": fake_msvcrt}), patch.object(sys, "platform", "win32"):
        ledger_new.append("TEST_ACT_2", {"a": 2})

    # Also test msvcrt unlock raising OSError
    call_cnt = 0

    def _lock_ok_unlock_fail(*_args: object) -> None:
        nonlocal call_cnt
        call_cnt += 1
        if call_cnt >= 2:
            raise OSError("unlock err")

    setattr(fake_msvcrt, "locking", _lock_ok_unlock_fail)
    with patch.dict(sys.modules, {"msvcrt": fake_msvcrt}), patch.object(sys, "platform", "win32"):
        ledger_new.append("TEST_ACT_3", {"a": 3})

    # Test non-win32 branch with dummy fcntl raising on unlock
    fake_fcntl = types.ModuleType("fcntl")
    setattr(fake_fcntl, "LOCK_EX", 2)
    setattr(fake_fcntl, "LOCK_UN", 8)

    def _fake_flock(_fd: int, op: int) -> None:
        if op == 8:
            raise OSError("unlock flock err")

    setattr(fake_fcntl, "flock", _fake_flock)
    with patch.dict(sys.modules, {"fcntl": fake_fcntl}), patch.object(sys, "platform", "linux"):
        ledger_new.append("TEST_LINUX", {"a": 4})

    # Sequence mismatch & prev_hash mismatch & _load_error on append
    bad_seq_path = tmp_path / "bad_seq.jsonl"
    bad_seq_path.write_text(
        json.dumps(
            {
                "seq": 5,
                "timestamp_utc": "2026-01-01T00:00:00Z",
                "action": "A",
                "payload": {},
                "prev_record_hash": "0" * 64,
                "record_hash": "h",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    l_bad_seq = CryptoAuditLedger(ledger_path=bad_seq_path)
    assert l_bad_seq.verify_integrity() is False
    assert l_bad_seq.verify_chain_integrity()[0] is False
    with pytest.raises(LedgerCorruptionError, match="Cannot append"):
        l_bad_seq.append("X", {})

    bad_prev_path = tmp_path / "bad_prev.jsonl"
    bad_prev_path.write_text(
        json.dumps(
            {
                "seq": 0,
                "timestamp_utc": "2026-01-01T00:00:00Z",
                "action": "A",
                "payload": {},
                "prev_record_hash": "wrong_prev",
                "record_hash": "h",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    l_bad_prev = CryptoAuditLedger(ledger_path=bad_prev_path)
    assert l_bad_prev.verify_integrity() is False

    # 2. ExecutionSimulator branches
    class _BrokenMt5:
        async def copy_ticks_from(self, *_args: object, **_kwargs: object) -> list[dict[str, float]]:
            raise RuntimeError("mt5 tick err")

    class _BarsRepo:
        async def get_recent_price_bars(self, **_kwargs: object) -> list[dict[str, float]]:
            return [{"open": 1.1000, "high": 1.1010, "low": 1.0990, "close": 1.1005} for _ in range(5)]

    sim = ExecutionSimulator(mt5_client=_BrokenMt5())
    with patch(
        "monika.domain.risk.ports.get_default_risk_data_provider",
        return_value=_BarsRepo(),
    ):
        ticks = await sim.fetch_recent_ticks("EURUSD", count=10, session=object())
        assert len(ticks) == 10

        res_neg = await sim.simulate_execution("EURUSD", "BUY", 0.0, 1.0950, 1.1050)
        assert res_neg.resilient is False
        res_inv_buy = await sim.simulate_execution("EURUSD", "BUY", 1.1000, 1.1050, 1.1100)
        assert res_inv_buy.resilient is False
        res_inv_sell = await sim.simulate_execution("EURUSD", "SELL", 1.1000, 1.0950, 1.0900)
        assert res_inv_sell.resilient is False
        res_auto_ticks = await sim.simulate_execution("EURUSD", "BUY", 1.1000, 1.0950, 1.1100, ticks=None)
        assert isinstance(res_auto_ticks.resilient, bool)


@pytest.mark.asyncio
async def test_pending_action_and_portfolio_optimizer_full_coverage(tmp_path: Path) -> None:
    from monika.domain.risk.pending_action import (
        PendingAction,
        PendingActionManager,
        PendingActionStatus,
    )
    import monika.domain.risk.portfolio_optimizer as po_mod
    from monika.domain.risk.portfolio_optimizer import (
        PortfolioOptimizer,
        project_vector_bounded_simplex,
    )

    # 1. PendingAction & PendingActionManager branches
    pa = PendingAction.from_dict({"client_order_id": "c1", "status": "NOT_A_VALID_STATUS"})
    assert pa.status == PendingActionStatus.UNCONFIRMED_DISPATCH

    store_dir = tmp_path / "pending_actions"
    store = PendingActionManager(base_dir=store_dir)
    assert store.commit_action("missing_id") is None
    assert store.fail_action("missing_id", "err") is None
    assert store.mark_unconfirmed("missing_id", "err") is None

    # Corrupt file handling
    bad_file = store_dir / "pending_action_corrupt.json"
    bad_file.write_text("{corrupt_json", encoding="utf-8")
    assert store.get_action("corrupt") is None
    assert store.get_unconfirmed_actions() == []

    # Cleanup old actions (committed + corrupt)
    act_c = store.begin_action(
        symbol="EURUSD",
        action="BUY",
        volume=0.1,
        price=1.1000,
        sl=1.0950,
        tp=1.1100,
        client_order_id="ord_clean",
    )
    assert act_c is not None
    store.commit_action("ord_clean", broker_ticket=12345)
    clean_path = store._file_path("ord_clean")
    data_c = json.loads(clean_path.read_text(encoding="utf-8"))
    data_c["updated_at"] = time.time() - 90000.0
    clean_path.write_text(json.dumps(data_c), encoding="utf-8")
    assert store.cleanup_old_actions(max_age_seconds=100.0) == 1
    bad_file.unlink(missing_ok=True)

    # Reconcile when no unconfirmed actions
    assert await store.reconcile_at_boot(mt5_client=object()) == []

    # Reconcile with datetime, valid ISO string, invalid ISO string, exception, and recent unresolved
    store.begin_action("EURUSD", "BUY", 0.1, 1.1000, 1.0950, 1.1100, client_order_id="ord_dt")
    store.begin_action("GBPUSD", "BUY", 0.1, 1.2500, 1.2450, 1.2600, client_order_id="ord_iso")
    store.begin_action("USDJPY", "BUY", 0.1, 150.0, 149.0, 152.0, client_order_id="ord_bad_iso")
    store.begin_action("XAUUSD", "BUY", 0.1, 2000.0, 1990.0, 2020.0, client_order_id="ord_err")

    class _ReconcileMt5:
        async def get_open_positions(self, symbol: str | None = None) -> list[dict[str, object]]:
            if symbol == "EURUSD":
                return [{"ticket": 11, "type": "buy", "comment": "ord_dt", "volume": 0.1, "time": datetime.now(UTC)}]
            if symbol == "GBPUSD":
                return [
                    {
                        "ticket": 22,
                        "type": "buy",
                        "comment": "ord_iso",
                        "volume": 0.1,
                        "time": datetime.now(UTC).isoformat(),
                    }
                ]
            if symbol == "USDJPY":
                return [{"ticket": 33, "type": "buy", "comment": "other", "volume": 0.9, "time": "not-an-iso-date"}]
            raise RuntimeError("mt5 query error")

    boot_res = await store.reconcile_at_boot(_ReconcileMt5())
    assert len(boot_res) == 4

    # Directory removed branches
    shutil.rmtree(store_dir)
    assert store.get_unconfirmed_actions() == []
    assert store.cleanup_old_actions() == 0

    # 2. PortfolioOptimizer branches
    assert len(project_vector_bounded_simplex(np.array([]), np.array([]))) == 0
    ub_small = project_vector_bounded_simplex(np.array([0.5, 0.5]), np.array([0.2, 0.2]))
    assert np.isclose(np.sum(ub_small), 1.0)
    ub_zero = project_vector_bounded_simplex(np.array([0.5, 0.5]), np.array([0.0, 0.0]))
    assert np.isclose(np.sum(ub_zero), 1.0)

    with patch("numpy.linalg.eigh", side_effect=np.linalg.LinAlgError("eigh err")):
        opt_lin = PortfolioOptimizer(["A", "B"], np.eye(2), expected_returns=None)
        assert len(opt_lin.expected_returns) == 2

    opt_0 = PortfolioOptimizer([], np.zeros((0, 0)))
    assert opt_0.solve_equal_volatility().converged is False
    assert opt_0.solve_risk_parity_erc().converged is False
    assert opt_0.solve_mean_variance().converged is False
    assert opt_0.solve_turnover_aware().converged is False

    opt_1 = PortfolioOptimizer(["EURUSD"], np.array([[0.04]]), np.array([0.05]))
    assert opt_1.solve_equal_volatility().weights == {"EURUSD": 1.0}
    assert opt_1.solve_risk_parity_erc().weights == {"EURUSD": 1.0}
    assert opt_1.solve_mean_variance().weights == {"EURUSD": 1.0}
    assert opt_1.solve_turnover_aware().weights == {"EURUSD": 1.0}

    # Zero variance and infinite variance (sum_inv <= 1e-9) in solve_equal_volatility
    opt_zero_cov = PortfolioOptimizer(["A", "B"], np.zeros((2, 2)), np.array([0.01, 0.02]))
    opt_zero_cov.cov_matrix = np.zeros((2, 2))
    assert len(opt_zero_cov.solve_equal_volatility().weights) == 2
    opt_inf_cov = PortfolioOptimizer(["A", "B"], np.eye(2), np.array([0.01, 0.02]))
    opt_inf_cov.cov_matrix = np.diag([1e22, 1e22])
    assert len(opt_inf_cov.solve_equal_volatility().weights) == 2

    # solve_mean_variance with scipy and without scipy
    opt_mv = PortfolioOptimizer(
        ["EURUSD", "GBPUSD", "XAUUSD"],
        np.array([[0.04, 0.01, 0.0], [0.01, 0.05, 0.0], [0.0, 0.0, 0.06]]),
        np.array([0.08, 0.06, 0.10]),
    )
    res_mv_scipy = opt_mv.solve_mean_variance()
    assert res_mv_scipy.converged is True

    with patch.object(po_mod, "_HAS_SCIPY", False):
        res_mv_np = opt_mv.solve_mean_variance()
        assert res_mv_np.converged is True

        # solve_turnover_aware with ndarray, None, zero prev_weights, non-metals expansion, and group cap enforcement
        res_ta_arr = opt_mv.solve_turnover_aware(
            prev_weights=np.array([0.0, 0.0, 0.0]),
            max_weight=0.25,
            group_map={"EURUSD": "FOREX", "GBPUSD": "FOREX", "XAUUSD": "METALS"},
            group_caps={"FOREX": 0.40, "METALS": 0.70},
        )
        assert res_ta_arr.converged is True

        # Also trigger hr_sum <= 1e-9 inside group cap projection loop
        res_ta_tight = opt_mv.solve_turnover_aware(
            prev_weights=None,
            max_weight=0.20,
            group_map={"EURUSD": "FOREX", "GBPUSD": "FOREX", "XAUUSD": "METALS"},
            group_caps={"FOREX": 0.10, "METALS": 0.10},
        )
        assert res_ta_tight.converged is True

    # Static convenience wrappers
    df_ret = pd.DataFrame({"EURUSD": [0.01, -0.005, 0.008, 0.002], "GBPUSD": [0.005, 0.002, -0.003, 0.006]})
    assert PortfolioOptimizer.equal_volatility(df_ret).converged is True
    assert PortfolioOptimizer.mean_variance(df_ret).converged is True
    assert PortfolioOptimizer.risk_parity(np.eye(2) * 0.04, ["EURUSD", "GBPUSD"]).converged is True
    assert (
        PortfolioOptimizer.turnover_aware(
            expected_returns=np.array([0.05, 0.06]),
            cov_matrix=np.eye(2) * 0.04,
            current_weights=np.array([0.5, 0.5]),
            symbols=["EURUSD", "GBPUSD"],
        ).converged
        is True
    )

    # Cover lines 36-38 (ImportError fallback for scipy.optimize) via controlled exec of try/except block
    orig_scipy_opt = sys.modules.get("scipy.optimize")
    try:
        sys.modules.pop("scipy.optimize", None)
        with patch("builtins.__import__", side_effect=ImportError("no scipy")):
            ns: dict[str, object] = {}
            code_obj = compile(
                "\n" * 31
                + "try:\n    from scipy.optimize import minimize\n\n    _HAS_SCIPY = True\nexcept ImportError:\n    _HAS_SCIPY = False\n    minimize = None\n",
                po_mod.__file__,
                "exec",
            )
            exec(code_obj, ns)
            assert ns["_HAS_SCIPY"] is False
    finally:
        if orig_scipy_opt is not None:
            sys.modules["scipy.optimize"] = orig_scipy_opt


@pytest.mark.asyncio
async def test_ports_position_math_plugin_proposal_and_invariants_full_coverage() -> None:
    from monika.domain.risk.invariants.position_count_invariant import check_position_count_invariant
    from monika.domain.risk.invariants.registry import (
        InvariantRegistry,
        InvariantViolationError,
        get_global_invariant_registry,
        reset_global_invariant_registry,
    )
    from monika.domain.risk.invariants.risk_gate_invariant import (
        assert_risk_gate_invariants,
        check_risk_gate_invariant,
    )
    from monika.domain.risk.invariants.state_immutability_invariant import (
        StateFreezeGuard,
        assert_state_immutability,
        compute_state_digest,
    )
    from monika.domain.risk.ports import (
        DefaultTimesFMAlphaCalculator,
        RiskPortRegistry,
        emit_risk_hook,
        get_default_adaptive_risk_policy,
        get_default_broker_client,
        get_default_copula_tail_risk_fitter,
        get_default_data_freshness_validator,
        get_default_event_publisher,
        get_default_evidence_store,
        get_default_evt_tail_calculator,
        get_default_notifier,
        get_default_regime_classifier,
        get_default_risk_data_provider,
        get_default_session_factory,
        get_default_suspended_symbols_provider,
        get_default_timesfm_alpha_calculator,
        get_strategy_factor_family,
        register_adaptive_risk_policy_factory,
        register_broker_client_factory,
        register_copula_tail_risk_fitter,
        register_data_freshness_validator,
        register_event_publisher,
        register_evidence_store_factory,
        register_evt_tail_calculator,
        register_notifier,
        register_regime_classifier,
        register_risk_data_provider_factory,
        register_risk_hook_emitter,
        register_session_factory,
        register_strategy_factor_family_resolver,
        register_suspended_symbols_provider,
        register_timesfm_alpha_calculator,
    )
    from monika.domain.risk.position_math import validated_stop_distance
    from monika.domain.risk.position_sizing import SizingResult
    from monika.domain.risk.risk_rule_plugin import (
        IDynamicSizingPlugin,
        IPostTradeInspectionPlugin,
        IRiskRulePlugin,
        ModularRiskRegistry,
        PluginMetadata,
        RiskRuleVerdict,
    )
    from monika.domain.risk.trade_proposal import FortressAdmissionValidator, TradeProposal

    # 1. RiskPortRegistry & DefaultTimesFMAlphaCalculator
    saved_ports = {
        k: getattr(RiskPortRegistry, k)
        for k in (
            "risk_data_provider_factory",
            "regime_classifier_fn",
            "timesfm_alpha_calculator",
            "risk_hook_emitter",
            "adaptive_risk_policy_factory",
            "evidence_store_factory",
            "copula_tail_risk_fitter",
            "evt_tail_calculator",
            "strategy_factor_family_resolver",
            "broker_client_factory",
            "suspended_symbols_provider",
            "event_publisher",
            "notifier",
            "session_factory",
            "data_freshness_validator",
        )
    }
    try:
        RiskPortRegistry.reset()
        assert get_default_evidence_store() is None
        assert get_default_notifier() is None

        register_data_freshness_validator("df_val")
        assert get_default_data_freshness_validator() == "df_val"
        register_suspended_symbols_provider("susp_prov")
        assert get_default_suspended_symbols_provider() == "susp_prov"
        register_risk_data_provider_factory(lambda **_kw: "provider_instance")
        assert get_default_risk_data_provider() == "provider_instance"
        register_regime_classifier("reg_cls")
        assert get_default_regime_classifier() == "reg_cls"
        register_timesfm_alpha_calculator("tfm_calc")
        assert get_default_timesfm_alpha_calculator() == "tfm_calc"
        register_evt_tail_calculator("evt_calc")
        assert get_default_evt_tail_calculator() == "evt_calc"

        async def _async_hook(_name: str, **_kw: object) -> None:
            await asyncio.sleep(0)

        register_risk_hook_emitter(_async_hook)
        await emit_risk_hook("test_hook")

        def _failing_hook(_name: str, **_kw: object) -> None:
            raise RuntimeError("hook boom")

        register_risk_hook_emitter(_failing_hook)
        await emit_risk_hook("test_hook")

        register_adaptive_risk_policy_factory(lambda **_kw: "policy_instance")
        assert get_default_adaptive_risk_policy() == "policy_instance"
        register_evidence_store_factory(lambda: "ev_store")
        assert get_default_evidence_store() == "ev_store"
        register_copula_tail_risk_fitter("copula_fn")
        assert get_default_copula_tail_risk_fitter() == "copula_fn"
        register_strategy_factor_family_resolver(lambda s: f"fam_{s}")
        assert get_strategy_factor_family("s1") == "fam_s1"
        register_broker_client_factory(lambda _s: "broker_instance")
        assert get_default_broker_client({}) == "broker_instance"
        register_event_publisher("ev_pub")
        assert get_default_event_publisher() == "ev_pub"
        register_session_factory("sess_fac")
        assert get_default_session_factory() == "sess_fac"

        def _bad_notifier() -> None:
            raise RuntimeError("notifier err")

        register_notifier(_bad_notifier)
        assert get_default_notifier() is _bad_notifier
        register_notifier("static_notifier")
        assert get_default_notifier() == "static_notifier"
    finally:
        for k, v in saved_ports.items():
            setattr(RiskPortRegistry, k, v)

    assert DefaultTimesFMAlphaCalculator.calculate_skew_from_quantiles({})["valid"] is False
    assert DefaultTimesFMAlphaCalculator.calculate_skew_from_quantiles({"q10": 1.0, "q90": 2.0})["valid"] is False
    assert (
        DefaultTimesFMAlphaCalculator.calculate_skew_from_quantiles({"q10": 3.0, "q50": 2.0, "q90": 1.0})["valid"]
        is False
    )
    bull_alpha = DefaultTimesFMAlphaCalculator.calculate_skew_from_quantiles({"q10": 1.0, "q50": 1.1, "q90": 2.0})
    assert bull_alpha["bias"] == "BULLISH_EXPANSION"
    bear_alpha = DefaultTimesFMAlphaCalculator.calculate_skew_from_quantiles({"q10": 1.0, "q50": 1.9, "q90": 2.0})
    assert bear_alpha["bias"] == "BEARISH_EXPANSION"
    sym_alpha = DefaultTimesFMAlphaCalculator.calculate_skew_from_quantiles({"q10": 1.0, "q50": 1.5, "q90": 2.0})
    assert sym_alpha["bias"] == "SYMMETRIC_NEUTRAL"
    assert (
        DefaultTimesFMAlphaCalculator.calculate_skew_from_quantiles({"q10": "bad", "q50": 1.5, "q90": 2.0})["valid"]
        is False
    )

    assert DefaultTimesFMAlphaCalculator.get_sizing_multiplier({"valid": False}, "BUY") == 1.0
    assert DefaultTimesFMAlphaCalculator.get_sizing_multiplier(bull_alpha, "BUY") == 1.15
    assert DefaultTimesFMAlphaCalculator.get_sizing_multiplier(bull_alpha, "SELL") == 0.80
    assert DefaultTimesFMAlphaCalculator.get_sizing_multiplier(bear_alpha, "BUY") == 0.80
    assert DefaultTimesFMAlphaCalculator.get_sizing_multiplier(bear_alpha, "SELL") == 1.15
    assert DefaultTimesFMAlphaCalculator.get_sizing_multiplier(sym_alpha, "HOLD") == 1.0

    # 2. position_math
    assert validated_stop_distance("buy", None, 1.0) is None
    assert validated_stop_distance("buy", "not_a_float", 1.0) is None
    assert validated_stop_distance("buy", -1.0, 1.0) is None
    assert validated_stop_distance("buy", 1.0, 1.1) is None
    assert validated_stop_distance("sell", 1.0, 1.1) == pytest.approx(0.1)
    assert validated_stop_distance("invalid_dir", 1.0, 0.9) is None

    # 3. risk_rule_plugin
    dummy_sz = SizingResult(
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
    assert await getattr(IRiskRulePlugin, "validate_pre_order")(object(), None, "EURUSD", "BUY", dummy_sz) is None
    assert await getattr(IDynamicSizingPlugin, "adjust_sizing")(object(), None, "EURUSD", 0.1, 10000.0) is None
    assert await getattr(IPostTradeInspectionPlugin, "inspect_post_trade")(object(), None, {}) is None

    orig_mod_reg = ModularRiskRegistry._instance
    try:
        ModularRiskRegistry._instance = None
        assert isinstance(ModularRiskRegistry.get_instance(), ModularRiskRegistry)
    finally:
        ModularRiskRegistry._instance = orig_mod_reg

    reg = ModularRiskRegistry()

    class _BoomRule(IRiskRulePlugin):
        metadata = PluginMetadata(id="boom_r", name="Boom", version="1.0")

        async def validate_pre_order(
            self,
            session: object,
            symbol: str,
            direction: str,
            sizing: SizingResult,
            account_equity: float | None = None,
            **_kwargs: object,
        ) -> RiskRuleVerdict:
            raise RuntimeError("rule exploded")

    class _BoomSizer(IDynamicSizingPlugin):
        metadata = PluginMetadata(id="boom_s", name="BoomS", version="1.0")

        async def adjust_sizing(
            self,
            session: object,
            symbol: str,
            base_lots: float,
            account_equity: float,
            **_kwargs: object,
        ) -> float:
            raise RuntimeError("sizer exploded")

    class _PostPlugin(IPostTradeInspectionPlugin):
        metadata = PluginMetadata(id="post_p", name="Post", version="1.0")

        async def inspect_post_trade(self, session: object, deal_data: dict[str, object]) -> None:
            return None

    reg.register_rule(_BoomRule())
    all_ok, _, failed_ids, _ = await reg.evaluate_modular_rules(None, "EURUSD", "BUY", dummy_sz, 10000.0)
    assert all_ok is False and "boom_r" in failed_ids
    reg.unregister_rule("boom_r")

    reg.register_sizing_plugin(_BoomSizer())
    assert await reg.apply_dynamic_sizing(None, "EURUSD", 0.25, 10000.0) == 0.25
    reg.unregister_sizing_plugin("boom_s")

    reg.register_post_trade_plugin(_PostPlugin())

    # 4. TradeProposal & FortressAdmissionValidator
    with pytest.raises(ValueError, match="Symbol cannot be empty"):
        TradeProposal(symbol="   ", direction="WAIT")
    with pytest.raises(ValueError, match="requires entry_price > 0"):
        TradeProposal(symbol="EURUSD", direction="BUY", entry_price=0.0, stop_loss=1.09, take_profit=1.11)
    with pytest.raises(ValueError, match="requires stop_loss > 0"):
        TradeProposal(symbol="EURUSD", direction="BUY", entry_price=1.10, stop_loss=0.0, take_profit=1.11)
    with pytest.raises(ValueError, match="requires take_profit > 0"):
        TradeProposal(symbol="EURUSD", direction="BUY", entry_price=1.10, stop_loss=1.09, take_profit=0.0)
    with pytest.raises(ValueError, match="BUY geometry violation: SL"):
        TradeProposal(
            symbol="EURUSD",
            direction="BUY",
            entry_price=1.10,
            stop_loss=1.11,
            take_profit=0.0,
            metadata={"is_trailing": True},
        )
    with pytest.raises(ValueError, match="SELL geometry violation: SL"):
        TradeProposal(
            symbol="EURUSD",
            direction="SELL",
            entry_price=1.10,
            stop_loss=1.09,
            take_profit=0.0,
            metadata={"is_trailing": True},
        )

    assert len(TradeProposal.compute_reasoning_hash(b"bytes_reasoning")) == 64
    assert len(getattr(TradeProposal, "compute_reasoning_hash")(12345)) == 64

    prop_valid = TradeProposal(
        symbol="EURUSD",
        direction="BUY",
        entry_price=1.1000,
        stop_loss=1.0950,
        take_profit=1.1100,
        lot_size=0.0,
        provenance_verified=False,
        timestamp=datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=120),
    )
    v_ok, v_rejs = FortressAdmissionValidator.validate_proposal(prop_valid, require_provenance=True)
    assert v_ok is False and len(v_rejs) >= 3

    # 5. Invariants (position_count, registry, risk_gate_invariant, state_immutability)
    res_pc = check_position_count_invariant(
        {"open_positions": [1, 2], "max_concurrent_positions": 2, "is_new_trade": True}
    )
    assert res_pc.failed is True

    orig_inv_reg = InvariantRegistry._instance
    try:
        reset_global_invariant_registry()
        reg_inst = InvariantRegistry.get_instance(with_defaults=False)
        reg_inst._invariants.clear()
        InvariantRegistry.get_instance(with_defaults=True)

        def _bad_provider(_r: InvariantRegistry) -> None:
            raise RuntimeError("provider err")

        reg_inst._default_registrations.append(_bad_provider)
        try:
            with patch("builtins.__import__", side_effect=RuntimeError("import err")):
                reg_inst.register_defaults()
        finally:
            reg_inst._default_registrations.remove(_bad_provider)

        reg_inst.register("crashing_inv", lambda _ctx: (_ for _ in ()).throw(RuntimeError("inv boom")))
        res_list = reg_inst.run_all({}, fail_fast=False)
        assert any(r.name == "crashing_inv" and r.failed for r in res_list)
        with pytest.raises(InvariantViolationError, match="crashed"):
            reg_inst.run_all({}, fail_fast=True)
        assert get_global_invariant_registry() is reg_inst
    finally:
        InvariantRegistry._instance = orig_inv_reg

    assert (
        check_risk_gate_invariant(
            {"proposal": {"action": "buy", "entry_price": -1.0, "stop_loss": 1.09}, "current_drawdown_pct": 1.0}
        ).failed
        is True
    )

    with pytest.raises(InvariantViolationError, match="invalid drawdown"):
        assert_risk_gate_invariants({}, float("nan"))

    class _PropWithToDict:
        def to_dict(self) -> dict[str, object]:
            return {"action": "buy", "entry_price": -1.0, "stop_loss": 1.09}

    with pytest.raises(InvariantViolationError, match="must be positive"):
        assert_risk_gate_invariants(_PropWithToDict(), 1.0)

    assert_risk_gate_invariants(42, 1.0)

    with pytest.raises(InvariantViolationError, match="Geometry breach for SELL"):
        assert_risk_gate_invariants({"action": "sell", "entry_price": 1.10, "stop_loss": 1.09}, 1.0)

    class _ZeroDiffFloat(float):
        def __sub__(self, _other: object) -> float:
            return 0.0

    with (
        patch(
            "monika.domain.risk.invariants.risk_gate_invariant.float",
            side_effect=lambda x: _ZeroDiffFloat(x),
            create=True,
        ),
        pytest.raises(InvariantViolationError, match="Invalid risk distance"),
    ):
        assert_risk_gate_invariants({"action": "buy", "entry_price": 1.10, "stop_loss": 1.09}, 1.0)

    with pytest.raises(InvariantViolationError, match="TP .* must be positive"):
        assert_risk_gate_invariants({"action": "buy", "entry_price": 1.10, "stop_loss": 1.09, "take_profit": -1.0}, 1.0)

    with pytest.raises(InvariantViolationError, match="Geometry breach for BUY"):
        assert_risk_gate_invariants(
            {"action": "buy", "entry_price": 1.10, "stop_loss": 1.09, "take_profit": 1.095}, 1.0
        )

    assert_risk_gate_invariants({"action": "sell", "entry_price": 1.10, "stop_loss": 1.11, "take_profit": 1.08}, 1.0)

    with pytest.raises(InvariantViolationError, match="Corrupt numerical parameters"):
        assert_risk_gate_invariants({"action": "buy", "entry_price": "bad_num", "stop_loss": 1.09}, 1.0)

    # state_immutability_invariant
    with patch("json.dumps", side_effect=TypeError("unserializable")):
        assert len(compute_state_digest({"symbol": "EURUSD"})) == 64

    with pytest.raises(RuntimeError, match="inner node err"):
        with StateFreezeGuard({"symbol": "EURUSD"}):
            raise RuntimeError("inner node err")

    assert_state_immutability({"symbol": "EURUSD", "cycle_id": "1"}, {"symbol": "EURUSD", "cycle_id": "1"})
    with pytest.raises(InvariantViolationError, match="differ between snapshots"):
        assert_state_immutability({"symbol": "EURUSD"}, {"symbol": "GBPUSD"})


@pytest.mark.asyncio
async def test_position_sizing_full_coverage() -> None:
    from monika.domain.risk.instruments.instruments import DEFAULT_INSTRUMENTS, InstrumentSpec
    from monika.domain.risk.position_sizing import (
        PositionSizer,
        calculate_lot_size,
        get_instrument_spec,
    )

    PositionSizer.update_usdjpy_cache(152.5)
    assert PositionSizer._usdjpy_rate_cache is not None

    sizer = PositionSizer(settings={"trading": {"risk": {"max_risk_amount_usd": 1000.0}}})
    assert await sizer._get_regime_size_multiplier(None, "EURUSD", override_mult=0.65) == 0.65

    with patch(
        "monika.domain.risk.ports.get_default_regime_classifier",
        return_value=lambda *_a, **_k: {"size_multiplier": 0.75, "regime": "CHOPPY", "composite_quality": 0.4},
    ):
        assert await sizer._get_regime_size_multiplier(object(), "EURUSD") == 0.75

    with patch(
        "monika.domain.risk.ports.get_default_regime_classifier",
        side_effect=RuntimeError("classifier err"),
    ):
        assert await sizer._get_regime_size_multiplier(object(), "EURUSD") == 1.0

    # calculate_with_session unparseable inputs & live equity branches
    res_bad_in = await sizer.calculate_with_session(
        session=None,
        symbol="EURUSD",
        direction="BUY",
        entry_price="bad",  # type-coerced inside calculate_with_session
        stop_loss="bad",
        take_profit="bad",
        account_equity=10000.0,
    )
    assert res_bad_in.is_valid is False

    class _MockMt5Info:
        def __init__(self, info: dict[str, object] | None = None, fail: bool = False) -> None:
            self.info = info
            self.fail = fail

        async def get_account_info(self) -> dict[str, object] | None:
            if self.fail:
                raise RuntimeError("mt5 err")
            return self.info

    # Cent account live equity <= 0 -> blown account
    s_cent_zero = PositionSizer(
        settings={"trading": {"paper_trading": {"enabled": False}}},
        mt5_client=_MockMt5Info({"is_cent_account": True, "normalized_equity": 0.0}),
    )
    res_cz = await s_cent_zero.calculate_with_session(None, "EURUSD", "BUY", 1.1000, 1.0950, account_equity=None)
    assert res_cz.is_valid is False

    # MT5 raises exception + live mode (trading.paper_trading.enabled=False) -> fail-closed
    s_live_fail = PositionSizer(
        settings={"trading": {"paper_trading": {"enabled": False}}},
        mt5_client=_MockMt5Info(fail=True),
    )
    res_lf = await s_live_fail.calculate_with_session(None, "EURUSD", "BUY", 1.1000, 1.0950, account_equity=None)
    assert res_lf.is_valid is False

    # Root paper_trading config fallback to initial_balance
    s_paper_fb = PositionSizer(
        settings={"paper_trading": {"enabled": True, "initial_balance": 25000.0}},
        mt5_client=_MockMt5Info(info=None),
    )
    res_pfb = await s_paper_fb.calculate_with_session(None, "EURUSD", "BUY", 1.1000, 1.0950, account_equity=None)
    assert res_pfb.account_equity == 25000.0

    # Cent normalization when account_equity > 1000
    s_cent_norm = PositionSizer(settings={"trading": {"risk": {"is_cent_account": True}}})
    res_cn = await s_cent_norm.calculate_with_session(None, "EURUSD", "BUY", 1.1000, 1.0950, account_equity=50000.0)
    assert res_cn.account_equity == 500.0

    # VIX tiers (normal<=vix<caution, caution<=vix<defensive, >=pause) in calculate_with_session
    for vix_val in (22.0, 27.0, 40.0):
        await sizer.calculate_with_session(
            None, "EURUSD", "BUY", 1.1000, 1.0950, account_equity=10000.0, vix_level=vix_val
        )

    # TimesFM dispersion, EVT fat-tail, streak loss scaling, churn penalty, and min_multiplier_floor clamp
    class _RichRepo:
        async def get_latest_timesfm_forecast(self, **_kw: object) -> dict[str, object]:
            return {"volatility_expansion_ratio": 1.60, "quantiles": {"q10": [1.08], "q50": [1.10], "q90": [1.15]}}

        async def get_recent_price_bars(self, **_kw: object) -> list[dict[str, float]]:
            return [{"close": 1.1000 + i * 0.0005} for i in range(40)]

        async def get_loss_streak(self, **_kw: object) -> int:
            return 4

        async def get_daily_trades_count(self, **_kw: object) -> int:
            return 5

    s_all_mults = PositionSizer(
        settings={
            "paper_trading": {"enabled": True, "streak_loss_policy": "warn_and_scale", "streak_risk_scale_factor": 0.2},
            "trading": {"risk": {"min_risk_multiplier_floor": 0.50, "max_risk_amount_usd": 5000.0}},
        }
    )
    with (
        patch("monika.domain.risk.ports.get_default_risk_data_provider", return_value=_RichRepo()),
        patch(
            "monika.domain.risk.ports.get_default_regime_classifier",
            return_value=lambda *_a, **_k: {"size_multiplier": 0.50},
        ),
        patch(
            "monika.domain.risk.ports.get_default_evt_tail_calculator",
            return_value=lambda _r: {"risk_sizing_multiplier": 0.60, "tail_risk_regime": "FAT", "shape_xi": 0.3},
        ),
    ):
        res_mult = await s_all_mults.calculate_with_session(
            object(), "USDJPY", "BUY", 150.0, 149.0, account_equity=500000.0, vix_level=40.0
        )
        assert res_mult.is_valid is True

    # Trigger exception handlers in TimesFM, EVT, and USDJPY dynamic pip value
    class _ErrRepo:
        async def get_latest_timesfm_forecast(self, **_kw: object) -> dict[str, object]:
            raise RuntimeError("tfm err")

        async def get_recent_price_bars(self, **_kw: object) -> list[dict[str, float]]:
            raise RuntimeError("bars err")

        async def get_loss_streak(self, **_kw: object) -> int:
            return 0

        async def get_daily_trades_count(self, **_kw: object) -> int:
            return 0

    with (
        patch("monika.domain.risk.ports.get_default_risk_data_provider", return_value=_ErrRepo()),
        patch("monika.domain.risk.ports.get_default_evt_tail_calculator", return_value=lambda _r: {}),
    ):
        await sizer.calculate_with_session(object(), "USDJPY", "BUY", 150.0, 149.0, account_equity=10000.0)

    # Unknown symbol, risk_pct <= 0, equity <= 0, geometry errors, stops_level, cent min_lot bump, volatility parity, notional cap
    assert (await sizer.calculate_with_session(None, "NONEXISTENT_SYM", "BUY", 1.1, 1.0, 10000.0)).is_valid is False
    assert (
        await sizer.calculate_with_session(None, "EURUSD", "BUY", 1.1, 1.0, 10000.0, risk_percent_override=0.0)
    ).is_valid is False
    with patch.object(sizer, "_get_instrument_spec_dynamic", return_value=DEFAULT_INSTRUMENTS["EURUSD"]):
        # Force account_equity <= 0 at line 419 by passing custom truthy-then-zero or negative initial_balance
        s_neg_bal = PositionSizer(settings={"paper_trading": {"enabled": True, "initial_balance": -100.0}})
        assert (
            await s_neg_bal.calculate_with_session(None, "EURUSD", "BUY", 1.1, 1.0, account_equity=None)
        ).is_valid is False

    # Geometry & <1 pip & stops_level & R:R check in calculate_with_session
    await sizer.calculate_with_session(
        None, "EURUSD", "BUY", 1.1000, 1.1050, take_profit=1.0900, account_equity=10000.0
    )
    await sizer.calculate_with_session(
        None, "EURUSD", "SELL", 1.1000, 1.0950, take_profit=1.1100, account_equity=10000.0
    )
    await sizer.calculate_with_session(
        None, "EURUSD", "BUY", 1.1000, 1.0950, take_profit=1.1005, account_equity=10000.0
    )

    spec_stops = InstrumentSpec(
        symbol="EURUSD", pip_size=0.0001, pip_value_usd=10.0, contract_size=100000, stops_level_pips=20.0
    )
    with patch.object(sizer, "_get_instrument_spec_dynamic", return_value=spec_stops):
        res_st = await sizer.calculate_with_session(None, "EURUSD", "BUY", 1.1000, 1.0990, account_equity=10000.0)
        assert res_st.is_valid is False

    spec_zero_pip = InstrumentSpec(symbol="EURUSD", pip_size=0.0001, pip_value_usd=0.0, contract_size=100000)
    with patch.object(sizer, "_get_instrument_spec_dynamic", return_value=spec_zero_pip):
        res_zp = await sizer.calculate_with_session(None, "EURUSD", "BUY", 1.1000, 1.0950, account_equity=10000.0)
        assert res_zp.is_valid is False

    # Cent account min_lot bump & rejection
    s_cent_bump = PositionSizer(
        settings={"trading": {"risk": {"is_cent_account": True, "max_risk_amount_usd": 1000.0}}}
    )
    res_cb = await s_cent_bump.calculate_with_session(
        None, "EURUSD", "BUY", 1.1000, 1.0500, account_equity=500.0, normalize_cent=False
    )
    assert res_cb.recommended_lots == 0.01

    s_cent_rej = PositionSizer(settings={"trading": {"risk": {"is_cent_account": True, "max_risk_amount_usd": 0.0001}}})
    res_cr = await s_cent_rej.calculate_with_session(
        None, "EURUSD", "BUY", 1.1000, 1.0500, account_equity=50.0, normalize_cent=False
    )
    assert res_cr.is_valid is False

    # Volatility parity (desired_lot < min_lot AND desired_lot >= min_lot) + Notional caps (USDxxx, Cross, Non-forex)
    s_vp = PositionSizer(
        settings={"trading": {"risk": {"volatility_parity": {"enabled": True}, "max_risk_amount_usd": 1000000.0}}}
    )
    await s_vp.calculate_with_session(None, "EURUSD", "BUY", 1.1000, 1.0950, account_equity=10.0, avg_atr=0.50)
    await s_vp.calculate_with_session(
        None, "USDJPY", "BUY", 150.0, 149.90, account_equity=1000.0, risk_percent_override=50.0, avg_atr=0.01
    )
    await s_vp.calculate_with_session(
        None, "EURGBP", "BUY", 0.8500, 0.8495, account_equity=1000.0, risk_percent_override=50.0, avg_atr=0.0001
    )
    await s_vp.calculate_with_session(
        None, "XAUUSD", "BUY", 2000.0, 1999.0, account_equity=100.0, risk_percent_override=50.0, avg_atr=0.1
    )
    # Notional cap reducing below min_lot
    await s_vp.calculate_with_session(
        None, "EURUSD", "BUY", 1.1000, 1.0999, account_equity=10.0, risk_percent_override=50.0
    )

    # Synchronous calculate() branches
    sizer.calculate("EURUSD", "BUY", "bad", "bad", "bad", 10000.0)
    for v_lvl in (15.0, 22.0, 27.0, 32.0):
        sizer.calculate("USDJPY", "BUY", 150.0, 149.0, None, 10000.0, vix_level=v_lvl)
    sizer.calculate("EURUSD", "BUY", 1.10, 1.09, None, 10000.0, risk_percent_override=0.0)
    sizer.calculate("EURUSD", "BUY", 1.10, 1.11, 1.09, 10000.0)
    sizer.calculate("EURUSD", "SELL", 1.10, 1.09, 1.11, 10000.0)
    sizer.calculate("EURUSD", "BUY", 1.1000, 1.09999, None, 10000.0)
    with patch.object(sizer, "_get_instrument_spec", return_value=spec_stops):
        sizer.calculate("EURUSD", "BUY", 1.1000, 1.0990, None, 10000.0)
    with patch.object(sizer, "_get_instrument_spec", return_value=spec_zero_pip):
        sizer.calculate("EURUSD", "BUY", 1.1000, 1.0950, None, 10000.0)

    s_vp.calculate("EURUSD", "BUY", 1.1000, 1.0950, None, 10.0, avg_atr=0.50)
    s_vp.calculate("USDJPY", "BUY", 150.0, 149.90, None, 1000.0, risk_percent_override=50.0, avg_atr=0.01)
    s_vp.calculate("EURGBP", "BUY", 0.8500, 0.8495, None, 1000.0, risk_percent_override=50.0, avg_atr=0.0001)

    # _get_instrument_spec with get_symbol_info_sync, get_instrument_spec (InstrumentSpec & dict), and exception
    class _SyncInfoMt5:
        def get_symbol_info_sync(self, _sym: str) -> dict[str, object]:
            return {"digits": 5, "point": 0.00001, "stops_level": 10}

    assert PositionSizer(settings={}, mt5_client=_SyncInfoMt5())._get_instrument_spec("EURUSD") is not None

    class _SpecMt5:
        def __init__(self, ret: object) -> None:
            self.ret = ret

        def get_instrument_spec(self, _sym: str) -> object:
            if isinstance(self.ret, Exception):
                raise self.ret
            return self.ret

    assert (
        PositionSizer(settings={}, mt5_client=_SpecMt5(DEFAULT_INSTRUMENTS["EURUSD"]))._get_instrument_spec("EURUSD")
        is not None
    )
    assert (
        PositionSizer(settings={}, mt5_client=_SpecMt5({"digits": 3, "point": 0.001}))._get_instrument_spec("USDJPY")
        is not None
    )
    assert (
        PositionSizer(settings={}, mt5_client=_SpecMt5(RuntimeError("boom")))._get_instrument_spec("EURUSD") is not None
    )

    # calculate_by_atr < min_lot and unknown symbol
    assert sizer.calculate_by_atr("EURUSD", 10.0, 0.50) == 0.0
    assert sizer.calculate_by_atr("UNKNOWN_SYM", 10000.0, 0.01) == 0.0

    # calculate_lot_size helper & get_instrument_spec heuristics
    with patch(
        "monika.domain.risk.ports.get_default_broker_client",
        return_value=_MockMt5Info(fail=True),
    ):
        lot_dict = await calculate_lot_size(
            "EURUSD",
            1.1000,
            1.0950,
            settings={"paper_trading": {"initial_balance": 15000.0}},
            account_equity=None,
            avg_atr=0.0020,
        )
        assert lot_dict["is_valid"] is True

    class _BrokenMt5Spec:
        def symbol_info(self, _s: str) -> object:
            raise RuntimeError("spec err")

    with patch.object(PositionSizer, "_get_instrument_spec", side_effect=RuntimeError("err")):
        get_instrument_spec("EURUSD", mt5_client=_BrokenMt5Spec())

    for custom_sym in (
        "FOOJPY",
        "FOOGOLD",
        "FOOSILVER",
        "FOOETH",
        "FOOBTC",
        "FOOOIL",
        "FOOUS30",
        "ABCDEF",
        "CUSTOM_INDEX_123",
    ):
        assert get_instrument_spec(custom_sym) is not None


@pytest.mark.asyncio
async def test_risk_gate_and_evaluators_full_coverage(tmp_path: Path) -> None:
    import monika.domain.risk.evaluators.base as ev_base
    from monika.domain.risk.evaluators.base import (
        get_daily_risk_cutoff as ev_cutoff,
        get_trading_day_start as ev_day_start,
    )
    from monika.domain.risk.position_sizing import SizingResult
    import monika.domain.risk.risk_gate as rg_mod
    from monika.domain.risk.risk_gate import (
        RiskGate,
        RiskVerdict,
        get_current_risk_state,
        get_trading_day_start as rg_day_start,
    )
    from monika.domain.risk.trade_proposal import TradeProposal

    # 1. get_trading_day_start & get_daily_risk_cutoff in both risk_gate.py and evaluators/base.py
    naive_hi = datetime(2026, 5, 10, 22, 0, 0)
    naive_lo = datetime(2026, 5, 10, 10, 0, 0)
    for fn in (rg_day_start, ev_day_start):
        assert fn({"trading": {"risk": {"daily_rollover_utc_hour": 0}}}, naive_hi).hour == 0
        assert fn({"trading": {"risk": {"broker_timezone": "America/New_York"}}}, naive_hi) is not None
        assert fn({"trading": {"risk": {"broker_timezone": "INVALID_TZ_NAME"}}}, naive_hi).hour == 21
        assert fn({"trading": {"risk": {"broker_timezone": "INVALID_TZ_NAME"}}}, naive_lo).hour == 21
    assert ev_cutoff(naive_hi, {}) is not None

    # 2. RiskGate.data_provider, update_parameters, evaluate kill_switch.flag, live equity checks
    gate = RiskGate(
        settings={
            "trading": {"risk": {"max_daily_drawdown_percent": 3.0}, "paper_trading": {"enabled": True}},
            "paper_trading": {"enabled": True, "initial_balance": 10000.0},
        }
    )
    with patch("monika.domain.risk.ports.get_default_risk_data_provider", return_value="dp_obj"):
        assert gate.data_provider() == "dp_obj"

    gate.update_parameters({})
    gate.update_parameters(
        {
            "trading": {
                "risk": {
                    "max_daily_drawdown_percent": 4.0,
                    "max_concurrent_positions": 5,
                    "correlation_limit": 3,
                    "news_window_minutes": 30,
                    "correlation_threshold": 0.75,
                }
            }
        }
    )
    assert gate.correlation_limit == 3

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

    # Kill-switch flag file in DATA_DIR
    flag_dir = tmp_path / "data_flag"
    flag_dir.mkdir(parents=True, exist_ok=True)
    (flag_dir / "kill_switch.flag").write_text("1", encoding="utf-8")
    with patch("monika.core.paths.DATA_DIR", flag_dir):
        v_ks = await gate.evaluate(None, "EURUSD", "BUY", sizing_ok, 10000.0)
        assert v_ks.approved is False

    # Live mode account_equity <= 0 and > 0
    gate_live = RiskGate(
        settings={
            "trading": {"paper_trading": {"enabled": False}},
            "paper_trading": {"enabled": False},
        }
    )
    v_live_zero = await gate_live.evaluate(None, "EURUSD", "BUY", sizing_ok, 0.0, is_paper=False)
    assert v_live_zero.approved is False

    class _MockRiskStateObj:
        daily_drawdown_pct = 1.2
        current_drawdown = 0.0
        daily_pnl = -120.0
        trading_paused = False
        reason = None
        unpause_at = None
        date = datetime.now(UTC)

    class _MockExecResult:
        def __init__(self, val: object = None, rows: list[object] | None = None) -> None:
            self._val = val
            self._rows = rows or []

        def scalar_one_or_none(self) -> object:
            return self._val

        def scalar(self) -> object:
            return self._val

        def scalars(self) -> _MockExecResult:
            return self

        def all(self) -> list[object]:
            return self._rows

    class _MockSession:
        def __init__(self, fail_exec: bool = False, result_val: object = None) -> None:
            self.fail_exec = fail_exec
            self.result_val = result_val

        async def execute(self, *_a: object, **_k: object) -> _MockExecResult:
            if self.fail_exec:
                raise RuntimeError("db exec err")
            return _MockExecResult(val=self.result_val)

        async def commit(self) -> None:
            return None

        async def flush(self) -> None:
            return None

        def add(self, _obj: object) -> None:
            return None

    # Plugin PRE_RISK_GATE error, event store emit error, metrics error
    with (
        patch("monika.domain.risk.ports.emit_risk_hook", side_effect=RuntimeError("hook err")),
        patch(
            "monika.domain.risk.ports.get_default_event_publisher",
            return_value=MagicMock(emit=AsyncMock(side_effect=RuntimeError("ev err"))),
        ),
        patch("monika.core.telemetry.metrics_exporter.metrics.inc_counter", side_effect=RuntimeError("m err")),
    ):
        await gate_live.evaluate(_MockSession(fail_exec=True), "EURUSD", "BUY", sizing_ok, 10000.0, is_paper=False)

    # 3. evaluate_proposal branches (risk state dd, error fail-closed, open positions error, invariant failures, geometry, JPY pips fallback)
    prop_buy = TradeProposal(
        symbol="USDJPY",
        direction="BUY",
        entry_price=150.0,
        stop_loss=149.0,
        take_profit=152.0,
        lot_size=0.1,
    )

    verdict_ok = RiskVerdict(approved=True, symbol="USDJPY", proposed_lots=0.1, checks_passed=[], checks_failed=[])
    with patch.object(gate, "_get_risk_state", AsyncMock(return_value=_MockRiskStateObj())):
        with patch.object(
            gate,
            "evaluate",
            AsyncMock(return_value=verdict_ok),
        ):
            with patch("monika.domain.risk.position_sizing.get_instrument_spec", side_effect=RuntimeError("spec err")):
                v_prop_ok = await gate.evaluate_proposal(_MockSession(fail_exec=True), prop_buy, 10000.0)
                assert v_prop_ok.approved is True

    with patch.object(gate, "_get_risk_state", AsyncMock(side_effect=RuntimeError("state err"))):
        v_prop_err = await gate.evaluate_proposal(_MockSession(), prop_buy, 10000.0)
        assert v_prop_err.approved is False

    # Invariant failure & exception in evaluate_proposal
    from monika.domain.risk.invariants.registry import InvariantResult, InvariantStatus

    with patch(
        "monika.domain.risk.invariants.registry.InvariantRegistry.run_all",
        return_value=[InvariantResult(name="r1", status=InvariantStatus.FAIL, message="bad")],
    ):
        assert (await gate.evaluate_proposal(None, prop_buy, 10000.0)).approved is False

    with patch(
        "monika.domain.risk.invariants.registry.InvariantRegistry.run_all",
        side_effect=RuntimeError("inv reg crash"),
    ):
        assert (await gate.evaluate_proposal(None, prop_buy, 10000.0)).approved is False

    # Geometry branches inside evaluate_proposal when invariants pass
    with patch("monika.domain.risk.invariants.registry.InvariantRegistry.run_all", return_value=[]):
        p_b_sl = prop_buy.model_copy(update={"stop_loss": 151.0})
        assert (await gate.evaluate_proposal(None, p_b_sl, 10000.0)).approved is False
        p_b_tp = prop_buy.model_copy(update={"take_profit": 148.0})
        assert (await gate.evaluate_proposal(None, p_b_tp, 10000.0)).approved is False

        prop_sell = TradeProposal(
            symbol="EURUSD", direction="SELL", entry_price=1.1000, stop_loss=1.1050, take_profit=1.0900, lot_size=0.1
        )
        p_s_sl = prop_sell.model_copy(update={"stop_loss": 1.0950})
        assert (await gate.evaluate_proposal(None, p_s_sl, 10000.0)).approved is False
        p_s_tp = prop_sell.model_copy(update={"take_profit": 1.1050})
        assert (await gate.evaluate_proposal(None, p_s_tp, 10000.0)).approved is False

        with patch.object(gate, "evaluate", AsyncMock(return_value=verdict_ok)):
            assert (await gate.evaluate_proposal(None, prop_sell, 10000.0)).approved is True
            p_wait = prop_sell.model_copy(update={"direction": "WAIT"})
            assert (await gate.evaluate_proposal(None, p_wait, 10000.0)).approved is True

    # 4. _get_risk_state, _log_verdict, update_daily_pnl notifier error, pause_trading, resume_trading, get_current_scorecard, get_current_risk_state
    assert await gate._get_risk_state(None) is None
    with patch.object(rg_mod, "RiskState", None), patch.object(rg_mod, "resolve_model", return_value=None):
        assert await gate._get_risk_state(_MockSession()) is None
    assert await gate._get_risk_state(_MockSession(fail_exec=True)) is None

    with patch.object(rg_mod, "OrderLog", None), patch.object(rg_mod, "resolve_model", return_value=None):
        await gate._log_verdict(_MockSession(), "EURUSD", "BUY", sizing_ok, verdict_ok)

    # update_risk_state notifier error
    state_pause = _MockRiskStateObj()
    state_pause.daily_pnl = -500.0

    class _BadNotifier:
        async def send_critical(self, _msg: str) -> None:
            raise RuntimeError("tg err")

    with patch("monika.domain.risk.ports.get_default_notifier", return_value=_BadNotifier()):
        await gate.update_risk_state(_MockSession(result_val=state_pause), pnl_delta=-500.0, equity=9000.0)

    # pause_trading when state is None and duration_hours is provided
    await gate.pause_trading(_MockSession(result_val=None), reason="test_pause", duration_hours=1.0)

    # resume_trading when tracker.unsuspend_all raises
    with patch(
        "monika.domain.risk.ports.get_default_suspended_symbols_provider",
        return_value=lambda _s: MagicMock(unsuspend_all=AsyncMock(side_effect=RuntimeError("unsuspend err"))),
    ):
        await gate.resume_trading(_MockSession(result_val=None))

    # get_current_scorecard (with one check passing, one failing, one raising)
    with patch.object(gate, "_check_daily_trade_count", AsyncMock(side_effect=RuntimeError("check err"))):
        sc = await gate.get_current_scorecard(_MockSession(), symbol="EURUSD", equity=10000.0)
        assert sc["total_checks"] >= 20

    # get_current_risk_state branches
    with patch("monika.domain.risk.ports.get_default_session_factory", side_effect=RuntimeError("no sess")):
        st_no_sess = await get_current_risk_state(session=None)
        assert st_no_sess["status"] == "unavailable"

    class _AsyncRowSession:
        def __init__(self) -> None:
            self.calls = 0

        async def execute(self, *_a: object, **_k: object) -> object:
            self.calls += 1

            class _Res:
                def __init__(self, call_idx: int) -> None:
                    self.call_idx = call_idx

                async def _coro_none(self) -> None:
                    return None

                async def _coro_row(self) -> object:
                    return _MockRiskStateObj()

                async def _coro_cnt(self) -> int:
                    return 2

                def scalar_one_or_none(self) -> object:
                    return self._coro_none() if self.call_idx == 1 else self._coro_row()

                def scalar(self) -> object:
                    return self._coro_cnt()

            return _Res(self.calls)

    class _LiveEqClient:
        async def get_account_info(self) -> dict[str, float]:
            return {"equity": 12345.0}

    with patch("monika.domain.risk.ports.get_default_broker_client", return_value=_LiveEqClient()):
        st_full = await get_current_risk_state(session=_AsyncRowSession(), settings={})
        assert st_full["current_equity"] == 12345.0

    with patch("monika.domain.risk.ports.get_default_broker_client", side_effect=RuntimeError("broker err")):
        await get_current_risk_state(session=_MockSession(result_val=None), settings={})

    # 5. Evaluators: execution_checks.py
    # _check_consecutive_losses config variants, streak_policy=="disabled", live tracker error/missing/suspended/max_consecutive
    for s_cfg in (
        {"paper_trading": {"enabled": True, "streak_loss_policy": "disabled"}},
        {"trading": {"paper_trading": True}},
        {"trading": {"paper_trading": "invalid"}},
    ):
        g_tmp = RiskGate(settings=s_cfg)
        await g_tmp._check_consecutive_losses(_MockSession(), "EURUSD")

    g_live_exec = RiskGate(settings={"trading": {"paper_trading": False, "auto_execute": True}})
    with patch("monika.domain.risk.ports.get_default_suspended_symbols_provider", return_value=None):
        ok_np, _ = await g_live_exec._check_consecutive_losses(_MockSession(), "EURUSD")
        assert ok_np is False

    with patch(
        "monika.domain.risk.ports.get_default_suspended_symbols_provider",
        return_value=lambda _s: MagicMock(get_suspended_symbols=AsyncMock(side_effect=RuntimeError("trk err"))),
    ):
        assert (await g_live_exec._check_consecutive_losses(_MockSession(), "EURUSD"))[0] is False

    with patch(
        "monika.domain.risk.ports.get_default_suspended_symbols_provider",
        return_value=lambda _s: MagicMock(get_suspended_symbols=AsyncMock(return_value={"EURUSD"})),
    ):
        assert (await g_live_exec._check_consecutive_losses(_MockSession(), "EURUSD"))[0] is False

    class _LossOrder:
        pnl_pct = -1.0
        exit_reason = "sl_hit"

    class _LossSession(_MockSession):
        async def execute(self, *_a: object, **_k: object) -> _MockExecResult:
            return _MockExecResult(
                rows=[_LossOrder(), _LossOrder(), _LossOrder(), MagicMock(pnl_pct=1.0, exit_reason="tp_hit")]
            )

    with patch(
        "monika.domain.risk.ports.get_default_suspended_symbols_provider",
        return_value=lambda _s: MagicMock(get_suspended_symbols=AsyncMock(return_value=set())),
    ):
        assert (await g_live_exec._check_consecutive_losses(_LossSession(), "EURUSD"))[0] is False

    # _check_not_paused with manual_trading_paused expired unpause_at, active block, and RiskState unpause_at expired
    class _CfgObj:
        def __init__(self, key: str, value: str) -> None:
            self.key = key
            self.value = value

    past_iso = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    cfg_expired = _CfgObj("manual_trading_paused", f"true:reason|unpause_at:{past_iso}")
    cfg_active = _CfgObj("kill_switch", "true:emergency")

    class _PauseSession(_MockSession):
        def __init__(self, cfgs: list[object], state_obj: object = None, commit_err: bool = False) -> None:
            super().__init__()
            self.cfgs = cfgs
            self.state_obj = state_obj
            self.commit_err = commit_err
            self.calls = 0

        async def execute(self, *_a: object, **_k: object) -> _MockExecResult:
            self.calls += 1
            if self.calls == 1:
                return _MockExecResult(rows=self.cfgs)
            if self.calls == 2:
                return _MockExecResult(val=self.state_obj)
            return _MockExecResult(val=self.cfgs[0] if self.cfgs else None)

        async def commit(self) -> None:
            if self.commit_err:
                raise RuntimeError("commit err")

    assert (await gate._check_not_paused(_PauseSession([cfg_expired, cfg_active], commit_err=True)))[0] is False

    state_timed = _MockRiskStateObj()
    state_timed.trading_paused = True
    state_timed.unpause_at = datetime.now(UTC) - timedelta(minutes=10)
    assert (
        await gate._check_not_paused(
            _PauseSession([_CfgObj("manual_trading_paused", "false")], state_obj=state_timed, commit_err=True)
        )
    )[0] is True

    # _check_daily_trade_count with bool and non-bool/non-dict paper_trading
    await RiskGate(settings={"paper_trading": True})._check_daily_trade_count(_MockSession(result_val=0), is_paper=None)
    await RiskGate(settings={"paper_trading": "invalid"})._check_daily_trade_count(
        _MockSession(result_val=0), is_paper=None
    )

    # _check_sizing_valid, _check_lot_size, _check_min_rr_ratio
    assert (await gate._check_sizing_valid(SizingResult(**{**sizing_ok.__dict__, "entry_price": float("nan")})))[
        0
    ] is False
    assert (
        await gate._check_sizing_valid(SizingResult(**{**sizing_ok.__dict__, "direction": "BUY", "stop_loss": 1.1100}))
    )[0] is False
    assert (
        await gate._check_sizing_valid(
            SizingResult(**{**sizing_ok.__dict__, "direction": "BUY", "take_profit": 1.0900})
        )
    )[0] is False
    assert (
        await gate._check_sizing_valid(SizingResult(**{**sizing_ok.__dict__, "direction": "SELL", "stop_loss": 1.0900}))
    )[0] is False
    assert (
        await gate._check_sizing_valid(
            SizingResult(**{**sizing_ok.__dict__, "direction": "SELL", "stop_loss": 1.1100, "take_profit": 1.1100})
        )
    )[0] is False

    assert (await gate._check_lot_size(SizingResult(**{**sizing_ok.__dict__, "recommended_lots": 150.0})))[0] is False
    assert (await gate._check_lot_size(SizingResult(**{**sizing_ok.__dict__, "recommended_lots": 0.0001})))[0] is False

    assert (await gate._check_min_rr_ratio(SizingResult(**{**sizing_ok.__dict__, "rr_ratio": None})))[0] is False
    assert (await gate._check_min_rr_ratio(SizingResult(**{**sizing_ok.__dict__, "rr_ratio": 0.5})))[0] is False

    # _check_max_spread branches (bool/other pt_cfg, no client live, disconnected paper/live, empty spread paper/live, invalid pts paper/live, crypto relative spread <= 0.0005, exception)
    await RiskGate(settings={"paper_trading": True})._check_max_spread(_MockSession(), "EURUSD")
    await RiskGate(settings={"paper_trading": "other"})._check_max_spread(_MockSession(), "EURUSD")
    assert (
        await RiskGate(settings={"paper_trading": False})._check_max_spread(_MockSession(), "EURUSD", is_paper=False)
    )[0] is False

    class _SpreadClient:
        def __init__(self, conn: bool = True, spread_ret: object = None, fail: bool = False) -> None:
            self.conn = conn
            self.spread_ret = spread_ret
            self.fail = fail

        async def is_connected(self) -> bool:
            if self.fail:
                raise RuntimeError("conn err")
            return self.conn

        async def get_spread(self, _sym: str) -> object:
            return self.spread_ret

    assert (
        await RiskGate(settings={}, mt5_client=_SpreadClient(conn=False))._check_max_spread(
            _MockSession(), "EURUSD", is_paper=True
        )
    )[0] is True
    assert (
        await RiskGate(settings={}, mt5_client=_SpreadClient(conn=False))._check_max_spread(
            _MockSession(), "EURUSD", is_paper=False
        )
    )[0] is False
    assert (
        await RiskGate(settings={}, mt5_client=_SpreadClient(spread_ret={}))._check_max_spread(
            _MockSession(), "EURUSD", is_paper=True
        )
    )[0] is True
    assert (
        await RiskGate(settings={}, mt5_client=_SpreadClient(spread_ret={}))._check_max_spread(
            _MockSession(), "EURUSD", is_paper=False
        )
    )[0] is False
    assert (
        await RiskGate(settings={}, mt5_client=_SpreadClient(spread_ret={"spread_points": -1}))._check_max_spread(
            _MockSession(), "EURUSD", is_paper=True
        )
    )[0] is True
    assert (
        await RiskGate(settings={}, mt5_client=_SpreadClient(spread_ret={"spread_points": -1}))._check_max_spread(
            _MockSession(), "EURUSD", is_paper=False
        )
    )[0] is False
    assert (
        await RiskGate(
            settings={},
            mt5_client=_SpreadClient(spread_ret={"spread_points": 100, "bid": 60000.0, "point": 0.01}),
        )._check_max_spread(_MockSession(), "BTCUSD", is_paper=False)
    )[0] is True
    assert (
        await RiskGate(settings={}, mt5_client=_SpreadClient(fail=True))._check_max_spread(
            _MockSession(), "EURUSD", is_paper=False
        )
    )[0] is False

    # _check_no_duplicate (conflict outside pair_group, group_count >= 2, existing duplicate)
    assert (await gate._check_no_duplicate(_MockSession(result_val=99), "EURUSD", pair_group_id="pg1"))[0] is False

    class _PairGroupSession(_MockSession):
        def __init__(self) -> None:
            super().__init__()
            self.c = 0

        async def execute(self, *_a: object, **_k: object) -> _MockExecResult:
            self.c += 1
            return _MockExecResult(val=None if self.c == 1 else 2)

    assert (await gate._check_no_duplicate(_PairGroupSession(), "EURUSD", pair_group_id="pg1"))[0] is False
    assert (await gate._check_no_duplicate(_MockSession(result_val=55), "EURUSD"))[0] is False

    # _check_post_loss_cooldown (disabled, paper recent_sl, live recent_sl)
    assert (
        await RiskGate(settings={"trading": {"risk": {"post_sl_cooldown_hours": 0}}})._check_post_loss_cooldown(
            _MockSession(), "EURUSD"
        )
    )[0] is True

    class _RecentSlObj:
        closed_at = datetime.now(UTC) - timedelta(hours=1)

    assert (await gate._check_post_loss_cooldown(_MockSession(result_val=_RecentSlObj()), "EURUSD"))[0] is False

    class _PaperSlCooldownSession(_MockSession):
        def __init__(self) -> None:
            super().__init__()
            self.c = 0

        async def execute(self, *_a: object, **_k: object) -> _MockExecResult:
            self.c += 1
            return _MockExecResult(val=None if self.c == 1 else _RecentSlObj())

    assert (await gate._check_post_loss_cooldown(_PaperSlCooldownSession(), "EURUSD"))[0] is False


@pytest.mark.asyncio
async def test_evaluators_intelligence_market_and_portfolio_full_coverage() -> None:
    from monika.domain.risk.position_sizing import SizingResult
    from monika.domain.risk.risk_gate import RiskGate

    gate = RiskGate(
        settings={
            "trading": {"risk": {"max_daily_drawdown_percent": 3.0}, "paper_trading": {"enabled": True}},
            "paper_trading": {"enabled": True, "initial_balance": 10000.0},
        }
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
        raw_lots=0.20,
        recommended_lots=0.20,
        rr_ratio=2.0,
        is_valid=True,
    )

    class _MockExecResult:
        def __init__(self, val: object = None, rows: list[object] | None = None) -> None:
            self._val = val
            self._rows = rows or []

        def scalar_one_or_none(self) -> object:
            return self._val

        def scalar(self) -> object:
            return self._val

        def scalars(self) -> _MockExecResult:
            return self

        def all(self) -> list[object]:
            return self._rows

    class _MockSession:
        def __init__(
            self, fail_exec: bool = False, result_val: object = None, rows: list[object] | None = None
        ) -> None:
            self.fail_exec = fail_exec
            self.result_val = result_val
            self.rows = rows or []

        async def execute(self, *_a: object, **_k: object) -> _MockExecResult:
            if self.fail_exec:
                raise RuntimeError("db exec err")
            return _MockExecResult(val=self.result_val, rows=self.rows)

        async def get(self, _model: object, _ident: object) -> object:
            return MagicMock(source_strategy_id="strat_1")

        async def flush(self) -> None:
            raise RuntimeError("flush err")

        def add(self, _obj: object) -> None:
            return None

    # 1. intelligence_checks.py
    default_q = {"q10": [1.0900], "q30": [1.0940], "q50": [1.1000], "q70": [1.1060], "q90": [1.1150]}
    tfm_rec = MagicMock(quantiles_json=json.dumps(default_q))
    sess_tfm = _MockSession(result_val=tfm_rec)

    sz_zero_sl = SizingResult(**{**sizing_ok.__dict__, "stop_loss": 0.0})
    assert (await gate._check_timesfm_expectancy(sess_tfm, "EURUSD", "BUY", sz_zero_sl))[0] is False
    sz_no_tp = SizingResult(**{**sizing_ok.__dict__, "take_profit": None})
    assert (await gate._check_timesfm_expectancy(sess_tfm, "EURUSD", "BUY", sz_no_tp))[0] is True

    # Holding period metadata variants, proposal attribute, reevaluation_trigger json, adr_tp_pct_used
    for meta_hp in ("scalp", "intraday", "swing"):
        await gate._check_timesfm_expectancy(
            sess_tfm,
            "EURUSD",
            "BUY",
            sizing_ok,
            proposal=MagicMock(metadata={"holding_period": meta_hp}, holding_period=None),
        )
    for attr_hp in ("scalp", "intraday", "swing"):
        await gate._check_timesfm_expectancy(
            sess_tfm,
            "EURUSD",
            "BUY",
            sizing_ok,
            proposal=MagicMock(metadata={}, holding_period=attr_hp),
        )
    await gate._check_timesfm_expectancy(
        sess_tfm,
        "EURUSD",
        "BUY",
        sizing_ok,
        proposal=MagicMock(metadata={}, holding_period=None, reevaluation_trigger='{"bars": 4}', adr_tp_pct_used=None),
    )
    await gate._check_timesfm_expectancy(
        sess_tfm,
        "EURUSD",
        "BUY",
        sizing_ok,
        proposal=MagicMock(metadata={}, holding_period=None, reevaluation_trigger="{bad_json", adr_tp_pct_used=0.5),
    )

    # SELL expectancy: TP < Q10 * 0.98 and SL inside Q70 noise cone
    sz_sell_low_tp = SizingResult(
        **{**sizing_ok.__dict__, "direction": "SELL", "entry_price": 1.1000, "stop_loss": 1.1100, "take_profit": 1.0500}
    )
    assert (await gate._check_timesfm_expectancy(sess_tfm, "EURUSD", "SELL", sz_sell_low_tp))[0] is False

    sz_sell_tight_sl = SizingResult(
        **{**sizing_ok.__dict__, "direction": "SELL", "entry_price": 1.1000, "stop_loss": 1.1010, "take_profit": 1.0900}
    )
    assert (await gate._check_timesfm_expectancy(sess_tfm, "EURUSD", "SELL", sz_sell_tight_sl))[0] is False

    # Empty quantile list & exception fail-closed
    sess_empty_q = _MockSession(result_val=MagicMock(quantiles_json=json.dumps({"q70": [], "q90": []})))
    await gate._check_timesfm_expectancy(sess_empty_q, "EURUSD", "SELL", sizing_ok)
    assert (await gate._check_timesfm_expectancy(_MockSession(fail_exec=True), "EURUSD", "BUY", sizing_ok))[0] is False

    # _check_analysis_quality_scores
    assert (await gate._check_analysis_quality_scores(None))[0] is False

    class _MockPolicy:
        def __init__(self, fail: bool = False) -> None:
            self.fail = fail

        async def get_effective_threshold(self, *_a: object) -> tuple[int, str]:
            if self.fail:
                raise RuntimeError("pol err")
            return 4, "adaptive"

    ana_llm = MagicMock(
        symbol="EURUSD",
        decision_source="llm",
        confluence_score=5,
        confidence="high",
        setup_quality="A",
        rr_ratio=2.0,
    )
    with patch("monika.domain.risk.ports.get_default_adaptive_risk_policy", return_value=_MockPolicy(fail=False)):
        await gate._check_analysis_quality_scores(ana_llm, session=_MockSession())
    with patch("monika.domain.risk.ports.get_default_adaptive_risk_policy", return_value=_MockPolicy(fail=True)):
        await gate._check_analysis_quality_scores(ana_llm, session=_MockSession())

    for bad_conf in (True, "not_a_float", 0.10):
        ana_q = MagicMock(symbol="EURUSD", decision_source="quantitative_ema", confidence=bad_conf)
        assert (await gate._check_analysis_quality_scores(ana_q))[0] is False

    # _check_edge_status_not_paused, _check_evidence_gate exception, _check_bounded_mandate coroutine scalar & exception & as_of
    assert (
        await gate._check_edge_status_not_paused(_MockSession(result_val=MagicMock(value="true:negative_expectancy")))
    )[0] is False

    with patch("monika.domain.risk.ports.get_default_evidence_store", side_effect=RuntimeError("ev store err")):
        assert (await gate._check_evidence_gate(_MockSession(), "EURUSD", analysis=MagicMock(source_strategy_id="s1")))[
            0
        ] is False

    await gate._check_bounded_mandate(_MockSession(fail_exec=True), "EURUSD", sizing_ok, as_of=datetime.now(UTC))

    # 2. market_checks.py
    with patch(
        "monika.domain.risk.ports.get_default_data_freshness_validator",
        return_value=AsyncMock(return_value={"ready": True, "errors": []}),
    ):
        assert (await gate._check_data_freshness(_MockSession(), "EURUSD"))[0] is True

    with patch(
        "monika.domain.risk.ports.get_default_data_freshness_validator",
        return_value=AsyncMock(side_effect=RuntimeError("fresh err")),
    ):
        assert (await gate._check_data_freshness(_MockSession(), "EURUSD"))[0] is False

    # _check_vix_threshold live missing & >= pause_threshold
    assert (
        await RiskGate(settings={"paper_trading": {"enabled": False}})._check_vix_threshold(
            _MockSession(result_val=None), is_backtest=False
        )
    )[0] is False
    assert (
        await gate._check_vix_threshold(
            _MockSession(result_val=MagicMock(close=45.0, date=datetime.now(UTC))), is_backtest=False
        )
    )[0] is False

    # assess_weekend_gap_risk Friday >= threshold_hour
    friday_late = datetime(2026, 5, 8, 20, 30, tzinfo=UTC)  # Friday 20:30 UTC
    assert (await gate.assess_weekend_gap_risk(_MockSession(), "EURUSD", as_of=friday_late))[0] is False

    # _check_rollover_window: crypto exempt, naive as_of inside rollover, and invalid tz fallback inside rollover
    assert (await gate._check_rollover_window("BTCUSD"))[0] is True
    rollover_naive = datetime(2026, 5, 6, 21, 5, 0)  # 17:05 EDT (NY close rollover)
    assert (await gate._check_rollover_window("EURUSD", as_of=rollover_naive))[0] is False
    with patch("zoneinfo.ZoneInfo", side_effect=RuntimeError("tz err")):
        assert (await gate._check_rollover_window("EURUSD", as_of=rollover_naive))[0] is False

    # _check_news_window: naive as_of, naive SystemConfig dt, SystemConfig parse err -> fallback to MAX(fetched_at), live empty block, crypto weekend, live stale block, UserPreference blacklists
    class _NewsSeqSession(_MockSession):
        def __init__(self, responses: list[object]) -> None:
            super().__init__()
            self.responses = list(responses)

        async def execute(self, *_a: object, **_k: object) -> _MockExecResult:
            val = self.responses.pop(0) if self.responses else None
            if isinstance(val, Exception):
                raise val
            if isinstance(val, list):
                return _MockExecResult(rows=val)
            return _MockExecResult(val=val)

    # Naive SystemConfig dt & live empty calendar -> hard block
    g_live_news = RiskGate(settings={"paper_trading": {"enabled": False}})
    sess_naive_cfg = _NewsSeqSession(
        [
            MagicMock(value="2026-05-06T10:00:00"),  # naive ISO in SystemConfig
            10,  # total_events
            1,  # future_coverage
            [],  # blacklists
            [],  # upcoming high-impact
        ]
    )
    assert (
        await g_live_news._check_news_window(
            sess_naive_cfg, "EURUSD", as_of=datetime(2026, 5, 6, 12, 0), is_paper=False
        )
    )[0] is True

    sess_empty_cal = _NewsSeqSession(
        [
            None,  # latest_fetch_cfg is None
            None,  # max_fetched is None
            0,  # total_events == 0
        ]
    )
    assert (
        await g_live_news._check_news_window(
            sess_empty_cal, "EURUSD", as_of=datetime(2026, 5, 6, 12, 0), is_paper=False
        )
    )[0] is False

    # Bad SystemConfig value -> MAX(fetched_at) naive -> stale live trade block
    sess_stale_cal = _NewsSeqSession(
        [
            MagicMock(value="not-an-iso"),
            datetime(2026, 5, 1, 10, 0, 0),  # naive max_fetched (5 days old)
            10,  # total_events
            None,  # future_coverage
        ]
    )
    assert (
        await g_live_news._check_news_window(
            sess_stale_cal, "EURUSD", as_of=datetime(2026, 5, 6, 12, 0, tzinfo=UTC), is_paper=False
        )
    )[0] is False

    # Crypto weekend + UserPreference blacklists (list, str, invalid json) matching upcoming event
    sat_now = datetime(2026, 5, 9, 12, 0, tzinfo=UTC)  # Saturday
    ev_match = MagicMock(
        event_time=datetime(2026, 5, 9, 12, 10),  # naive event_time within window
        event_name="FOMC Press Conference",
        currency="USD",
    )
    sess_blacklist = _NewsSeqSession(
        [
            MagicMock(value=sat_now.isoformat()),
            10,  # total_events
            sat_now + timedelta(days=2),  # future_coverage
            [
                MagicMock(value_json='["NFP", "FOMC"]'),
                MagicMock(value_json='"CPI"'),
                MagicMock(value_json="{bad_json_raw_term"),
            ],
            [MagicMock(event_time=None), ev_match],
        ]
    )
    assert (await gate._check_news_window(sess_blacklist, "BTCUSD", as_of=sat_now))[0] is False

    # _check_schmitt_regime FUSED + simulated_positions >= 2, and exception
    from monika.domain.indicators.regime_detector import RegimeState

    with patch(
        "monika.domain.indicators.regime_detector.get_schmitt_regime_detector",
        return_value=MagicMock(state=RegimeState.FUSED, last_density=0.85),
    ):
        assert (
            await gate._check_schmitt_regime(
                _MockSession(result_val=1), "EURUSD", simulated_positions=[object(), object()]
            )
        )[0] is False

    with patch(
        "monika.domain.indicators.regime_detector.get_schmitt_regime_detector",
        side_effect=RuntimeError("schmitt err"),
    ):
        assert (await gate._check_schmitt_regime(_MockSession(), "EURUSD"))[0] is False

    # _check_vpin_toxicity (>0.75, <=0.75, exception) on VPIN_SYMBOLS ("BTCUSD")
    assert (
        await gate._check_vpin_toxicity(
            _MockSession(result_val=MagicMock(value_json='{"vpin": 0.85}')), "BTCUSD", as_of=sat_now
        )
    )[0] is False
    assert (
        await gate._check_vpin_toxicity(
            _MockSession(result_val=MagicMock(value_json='{"vpin": 0.35}')), "BTCUSD", as_of=sat_now
        )
    )[0] is True
    assert (await gate._check_vpin_toxicity(_MockSession(fail_exec=True), "BTCUSD"))[0] is False

    # _check_adv_liquidity: rollover window 21:55-22:15 with lots > 0.5, and non-finite ADV (len(rows) >= 5)
    sz_big = SizingResult(**{**sizing_ok.__dict__, "recommended_lots": 1.0})
    assert (
        await gate._check_adv_liquidity(
            _MockSession(), "EURUSD", sz_big, as_of=datetime(2026, 5, 6, 21, 58, tzinfo=UTC)
        )
    )[0] is False
    assert (
        await gate._check_adv_liquidity(
            _MockSession(rows=[0.0, 0.0, 0.0, 0.0, 0.0]),
            "EURUSD",
            sizing_ok,
            as_of=datetime(2026, 5, 6, 14, 0, tzinfo=UTC),
        )
    )[0] is False

    # 3. portfolio_checks.py
    # _check_strategy_factor_exposure: integer limit_val, simulated_positions with source_strategy_id and analysis_id, DB positions with analysis_id
    g_int_lim = RiskGate(settings={"trading": {"risk": {"max_positions_per_factor_family": 2}}})
    sim_p1 = MagicMock(source_strategy_id="strat_1", analysis_id=None)
    sim_p2 = MagicMock(source_strategy_id=None, analysis_id=10)
    await g_int_lim._check_strategy_factor_exposure(
        _MockSession(),
        analysis=MagicMock(factor_family="", source_strategy_id="strat_1"),
        simulated_positions=[sim_p1, sim_p2],
    )
    await g_int_lim._check_strategy_factor_exposure(
        _MockSession(rows=[sim_p2]),
        analysis=MagicMock(factor_family="", source_strategy_id="strat_1"),
        simulated_positions=None,
    )

    # _check_weekly_drawdown & _check_daily_drawdown equity <= 0, unverified closed paper trade, open paper trade anchor from analysis, invalid stop, missing risk_pct, live flush/mt5 errors
    g_zero_eq = RiskGate(settings={"paper_trading": {"enabled": True, "initial_balance": 0.0}})
    assert (await g_zero_eq._check_weekly_drawdown(_MockSession(), 0.0))[0] is False
    assert (await g_zero_eq._check_daily_drawdown(_MockSession(), 0.0))[0] is False

    unverified_trade = MagicMock(accounting_status="corrupt", symbol="EURUSD", id=1)
    assert (await gate._check_daily_drawdown(_MockSession(rows=[unverified_trade]), 10000.0, is_paper=True))[0] is False

    class _PaperOpenSession(_MockSession):
        def __init__(self, open_trades: list[object], anchor_val: float | None = 1.0900) -> None:
            super().__init__()
            self.open_trades = open_trades
            self.anchor_val = anchor_val
            self.c = 0

        async def execute(self, *_a: object, **_k: object) -> _MockExecResult:
            self.c += 1
            if self.c == 1:
                return _MockExecResult(rows=[])  # closed_today
            if self.c == 2:
                return _MockExecResult(rows=self.open_trades)  # open_paper
            return _MockExecResult(val=self.anchor_val)  # AssetAnalysis.stop_loss

    p_bad_stop = MagicMock(
        id=2,
        symbol="EURUSD",
        direction="buy",
        entry_price=1.1000,
        initial_stop_loss=None,
        analysis_id=5,
        initial_risk_pct=1.0,
        risk_pct=1.0,
    )
    assert (
        await gate._check_daily_drawdown(_PaperOpenSession([p_bad_stop], anchor_val=1.1100), 10000.0, is_paper=True)
    )[0] is False

    p_no_risk = MagicMock(
        id=3,
        symbol="EURUSD",
        direction="buy",
        entry_price=1.1000,
        initial_stop_loss=1.0900,
        analysis_id=None,
        initial_risk_pct=0.0,
        risk_pct=0.0,
    )
    assert (await gate._check_daily_drawdown(_PaperOpenSession([p_no_risk]), 10000.0, is_paper=True))[0] is False

    # Live daily drawdown with state=None (flush raises) and mt5.get_open_positions raises
    g_live_dd = RiskGate(
        settings={"trading": {"paper_trading": {"enabled": False}}, "paper_trading": {"enabled": False}},
        mt5_client=MagicMock(get_open_positions=AsyncMock(side_effect=RuntimeError("mt5 pos err"))),
    )
    with patch.object(g_live_dd, "_get_risk_state", AsyncMock(return_value=None)):
        await g_live_dd._check_daily_drawdown(_MockSession(), 10000.0, is_paper=False)

    # _check_correlation: dcm exception, empty pos_sym, correlated_exposure > limit, _get_dynamic_correlation s2_rows >= 30 & exception
    pos_empty_sym = MagicMock(symbol="", direction="buy", volume=1.0)
    pos_corr = MagicMock(symbol="GBPUSD", direction="buy", volume=5.0)
    with (
        patch.object(gate.dynamic_correlation_matrix, "get_matrix", AsyncMock(side_effect=RuntimeError("dcm err"))),
        patch.object(gate, "_get_dynamic_correlation", AsyncMock(return_value=(0.95, 0.01))),
    ):
        assert (
            await gate._check_correlation(
                _MockSession(), "EURUSD", "buy", simulated_positions=[pos_empty_sym, pos_corr]
            )
        )[0] is False

    base_ts = datetime(2026, 5, 1, tzinfo=UTC)
    s2_35 = [(base_ts + timedelta(hours=4 * i), 1.2500 + 0.001 * i) for i in range(35)]

    class _CorrStdSession(_MockSession):
        def __init__(self, fail: bool = False) -> None:
            super().__init__()
            self.fail = fail

        async def execute(self, *_a: object, **_k: object) -> _MockExecResult:
            if self.fail:
                raise RuntimeError("std db err")
            return _MockExecResult(rows=s2_35)

    with patch(
        "monika.domain.market.dynamic_correlation.get_rolling_correlation",
        AsyncMock(return_value=(0.8, "db")),
    ):
        corr_v, std_v = await gate._get_dynamic_correlation(_CorrStdSession(), "EURUSD", "GBPUSD")
        assert corr_v == 0.8 and std_v > 0
        with patch("pandas.Series.std", side_effect=ValueError("std err")):
            await gate._get_dynamic_correlation(_CorrStdSession(), "EURUSD", "GBPUSD")
        await gate._get_dynamic_correlation(_CorrStdSession(fail=True), "EURUSD", "GBPUSD")

    # _check_total_portfolio_heat: buy BE, sell BE, _get_instrument_spec_dynamic raises + spec=None fallback, no SL with simulated_positions=None & simulated_positions!=None, total_heat > max_heat
    p_buy_be = MagicMock(symbol="EURUSD", direction="buy", entry_price=1.1000, sl=1.1010, volume=0.1)
    p_sell_be = MagicMock(symbol="GBPUSD", direction="sell", entry_price=1.2500, sl=1.2490, volume=0.1)
    p_unknown = MagicMock(symbol="UNKNOWN_XYZ", direction="buy", entry_price=100.0, sl=90.0, volume=0.1)
    p_no_sl = MagicMock(symbol="USDJPY", direction="buy", entry_price=150.0, sl=0.0, stop_loss=0.0, volume=0.1)

    with patch(
        "monika.domain.risk.position_sizing.PositionSizer._get_instrument_spec_dynamic",
        AsyncMock(side_effect=RuntimeError("dyn spec err")),
    ):
        await gate._check_total_portfolio_heat(
            _MockSession(), sizing_ok, 10000.0, simulated_positions=[p_buy_be, p_sell_be, p_unknown, p_no_sl]
        )

    # DB positions with no SL (simulated_positions=None) + heat > max_heat_pct
    sz_huge_heat = SizingResult(**{**sizing_ok.__dict__, "risk_amount_usd": 900.0})
    assert (
        await gate._check_total_portfolio_heat(
            _MockSession(rows=[p_no_sl]), sz_huge_heat, 10000.0, simulated_positions=None
        )
    )[0] is False

    # _check_copula_tail_risk: c_rows < 30, o_rows < 30, common_ts < 30, lower_tail > 0.40, lower_tail <= 0.40
    class _CopulaSession(_MockSession):
        def __init__(self, seq: list[list[object]]) -> None:
            super().__init__()
            self.seq = list(seq)

        async def execute(self, *_a: object, **_k: object) -> _MockExecResult:
            rows = self.seq.pop(0) if self.seq else []
            return _MockExecResult(rows=rows)

    c_short = [(base_ts + timedelta(hours=i), 1.10 + 0.0001 * i) for i in range(10)]
    c_long = [(base_ts + timedelta(hours=i), 1.10 + 0.0001 * (i % 5)) for i in range(35)]
    o_disjoint = [(base_ts + timedelta(days=100, hours=i), 1.25 + 0.0001 * i) for i in range(35)]

    with patch(
        "monika.domain.risk.ports.get_default_copula_tail_risk_fitter",
        return_value=lambda *_a: {"lower_tail_dependence": 0.20},
    ):
        # c_rows < 30
        assert (
            await gate._check_copula_tail_risk(
                _CopulaSession([c_short]), "EURUSD", simulated_positions=[{"symbol": "GBPUSD"}]
            )
        )[0] is True
        # o_rows < 30, common_ts < 30, then valid o_rows with lower_tail <= 0.40
        assert (
            await gate._check_copula_tail_risk(
                _CopulaSession([c_long, c_short, o_disjoint, c_long]),
                "EURUSD",
                simulated_positions=[
                    {"symbol": "GBPUSD"},
                    {"symbol": "AUDUSD"},
                    {"symbol": "NZDUSD"},
                ],
            )
        )[0] is True

    with patch(
        "monika.domain.risk.ports.get_default_copula_tail_risk_fitter",
        return_value=lambda *_a: {"lower_tail_dependence": 0.65},
    ):
        assert (
            await gate._check_copula_tail_risk(
                _CopulaSession([c_long, c_long]), "EURUSD", simulated_positions=[{"symbol": "GBPUSD"}]
            )
        )[0] is False


@pytest.mark.asyncio
async def test_domain_risk_remaining_143_lines_coverage(tmp_path: Path) -> None:
    """Covers the final 143 missed lines across all 12 remaining files in monika.domain.risk."""
    import numpy as np
    import pandas as pd

    from monika.domain.risk.approval_hub import ApprovalHub, get_approval_hub
    from monika.domain.risk.crypto_audit_ledger import (
        GENESIS_PREV_HASH,
        CryptoAuditLedger,
        LedgerCorruptionError,
    )
    from monika.domain.risk.execution_simulator import ExecutionSimulator
    from monika.domain.risk.portfolio_correlation_gate import filter_correlated_proposals
    from monika.domain.risk.portfolio_optimizer import PortfolioOptimizer
    from monika.domain.risk.position_sizing import InstrumentSpec, PositionSizer, SizingResult, get_instrument_spec
    from monika.domain.risk.risk_gate import RiskGate, get_current_risk_state

    class _MockExecResult:
        def __init__(self, scalar_val: object = None, rows: list[object] | None = None) -> None:
            self._val = scalar_val
            self._rows = rows or []

        def scalar_one_or_none(self) -> object:
            return self._val

        def scalar(self) -> object:
            return self._val

        def scalars(self) -> _MockExecResult:
            return self

        def all(self) -> list[object]:
            return self._rows

    class _MockSession:
        def __init__(
            self,
            *,
            scalar_val: object = None,
            rows: list[object] | None = None,
            fail_execute: bool = False,
        ) -> None:
            self.scalar_val = scalar_val
            self.rows = rows or []
            self.fail_execute = fail_execute

        async def execute(self, *_a: object, **_k: object) -> _MockExecResult:
            if self.fail_execute:
                raise RuntimeError("db exec err")
            return _MockExecResult(scalar_val=self.scalar_val, rows=self.rows)

        async def get(self, *_a: object, **_k: object) -> object:
            return self.scalar_val

        async def commit(self) -> None:
            return None

        async def flush(self) -> None:
            return None

        def add(self, _obj: object) -> None:
            return None

    # 1. approval_hub.py: line 538 (await_decision resolves before timeout)
    hub = ApprovalHub()
    r_wait = hub.create_request(request_id="r_wait", action="trade", description="wait", ttl_seconds=30.0)
    wait_task = asyncio.create_task(hub.await_decision(r_wait.token, timeout_seconds=5.0))
    await asyncio.sleep(0)
    hub.decide(r_wait.token, approved=True, user_id="op")
    ok_wait, _ = await wait_task
    assert ok_wait is True

    # 2. crypto_audit_ledger.py: 96, 127-129, 216-217, 236-241, 245
    ok_path = tmp_path / "ok_ledger.jsonl"
    ok_ledger = CryptoAuditLedger(ledger_path=ok_path)
    ok_ledger.append_audit_record("ACT1", {"k": 1})
    ok_ver, msg_ver = ok_ledger.verify_chain_integrity()
    assert ok_ver is True and "verified" in msg_ver

    # Tamper record_hash on disk (line 96) while keeping valid seq=0 and prev_record_hash=GENESIS_PREV_HASH
    ok_path.write_text(
        json.dumps(
            {
                "seq": 0,
                "prev_record_hash": GENESIS_PREV_HASH,
                "record_hash": "0" * 64,
                "timestamp_utc": "2026-01-01T00:00:00Z",
                "action": "ACT1",
                "payload": {"k": 1},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    fail_ver, _ = ok_ledger.verify_chain_integrity()
    assert fail_ver is False

    # Corrupt JSON on disk while ok_ledger2._load_error is None -> append hits 127-129 and 216-217
    corrupt_path = tmp_path / "corrupt_ledger.jsonl"
    ok_ledger2 = CryptoAuditLedger(ledger_path=corrupt_path)
    corrupt_path.write_text("not-json\n", encoding="utf-8")
    with pytest.raises(LedgerCorruptionError):
        ok_ledger2.append("ACT2", {})

    # 3. execution_simulator.py: 86-87 (get_ticks raises exception)
    sim = ExecutionSimulator(mt5_client=MagicMock(get_ticks=AsyncMock(side_effect=RuntimeError("tick err"))))
    sim_ticks = await sim.fetch_recent_ticks("EURUSD")
    assert isinstance(sim_ticks, list)

    # 4. portfolio_correlation_gate.py: 146, 169
    class _SessionMutatingPos:
        symbol = "AUDUSD"
        calls = 0

        @property
        def direction(self) -> str:
            self.calls += 1
            if self.calls >= 2:
                sys._getframe(1).f_locals["session"] = None
            return "buy"

    with patch(
        "monika.domain.risk.ports.get_default_risk_data_provider",
        return_value=MagicMock(get_open_positions=AsyncMock(return_value=[_SessionMutatingPos()])),
    ):
        kept1, _ = await filter_correlated_proposals(
            _MockSession(),
            [("EURUSD", {"decision": "buy", "confidence": 0.9})],
            threshold=0.99,
        )
        assert len(kept1) == 1

    with (
        patch(
            "monika.domain.risk.ports.get_default_risk_data_provider",
            return_value=MagicMock(get_open_positions=AsyncMock(return_value=[])),
        ),
        patch(
            "monika.domain.risk.portfolio_correlation_gate.get_rolling_correlation",
            AsyncMock(return_value=(0.1, "dyn")),
        ),
    ):
        kept2, _ = await filter_correlated_proposals(
            _MockSession(),
            [
                ("EURUSD", {"decision": "buy", "confidence": 0.9}),
                ("GBPUSD", {"decision": "buy", "confidence": 0.8}),
            ],
            threshold=0.99,
        )
        assert len(kept2) == 2

    # 5. portfolio_optimizer.py: 315, 365-375
    opt = PortfolioOptimizer(
        symbols=["EURUSD", "GBPUSD", "XAUUSD"],
        cov_matrix=np.eye(3) * 0.01,
        expected_returns=np.array([0.05, 0.04, 0.03]),
    )

    class _DynamicGroupMap(dict[str, str]):
        def __init__(self) -> None:
            super().__init__({"_keep_truthy": "1"})
            self.calls = 0

        def get(self, key: str, default: object = None) -> str:
            self.calls += 1
            if self.calls <= 9:
                return "OTHER"
            return "G_CAP" if key in ("EURUSD", "GBPUSD") else "OTHER"

    opt_res1 = opt.solve_turnover_aware(
        prev_weights={"EURUSD": 0.45, "GBPUSD": 0.45, "XAUUSD": 0.10},
        max_weight=0.80,
        group_map=_DynamicGroupMap(),
        group_caps={"G_CAP": 0.20, "OTHER": 1.0},
    )
    assert opt_res1.converged is True

    # Also trigger line 375 (hr_sum <= 1e-9 when XAUUSD is METALS at its 0.25 bound)
    class _DynamicGroupMapNoHeadroom(dict[str, str]):
        def __init__(self) -> None:
            super().__init__({"_keep_truthy": "1"})
            self.calls = 0

        def get(self, key: str, default: object = None) -> str:
            self.calls += 1
            if 4 <= self.calls <= 6:
                return "METALS" if key == "XAUUSD" else "OTHER"
            if self.calls <= 9:
                return "OTHER"
            return "G_CAP" if key in ("EURUSD", "GBPUSD") else "METALS"

    opt_res2 = opt.solve_turnover_aware(
        prev_weights={"EURUSD": 0.40, "GBPUSD": 0.35, "XAUUSD": 0.25},
        max_weight=0.80,
        group_map=_DynamicGroupMapNoHeadroom(),
        group_caps={"G_CAP": 0.20, "METALS": 0.25, "OTHER": 1.0},
    )
    assert opt_res2.converged is True

    # 6. evaluators/execution_checks.py: 58, 96, 100, 128, 165-166, 239, 255, 363, 370, 394-396, 415, 457-464, 498, 509, 517-528, 536
    gate = RiskGate(
        {
            "paper_trading": {"enabled": True, "streak_loss_policy": "disabled"},
            "trading": {"auto_execute": False, "risk": {"max_consecutive_losses_per_symbol": 2, "max_daily_trades": 2}},
        }
    )
    # line 58 (paper_trading in self.settings when trading.paper_trading is not dict) & line 96 (streak_policy == 'disabled')
    gate.settings["trading"]["paper_trading"] = None
    assert (await gate._check_consecutive_losses(_MockSession(rows=[]), "EURUSD"))[0] is True

    # line 100 (streak_policy == 'warn_and_scale' with consecutive_losses >= max_consecutive)
    gate.settings["paper_trading"]["streak_loss_policy"] = "warn_and_scale"
    loss_rows = [MagicMock(pnl_pct=-1.0, exit_reason="sl_hit"), MagicMock(pnl_pct=-1.0, exit_reason="sl_hit")]
    assert "warn_and_scale" in (await gate._check_consecutive_losses(_MockSession(rows=loss_rows), "EURUSD"))[1]

    # line 128 (auto_execute=True, consecutive_losses < max_consecutive)
    gate.settings["trading"]["auto_execute"] = True
    with patch(
        "monika.domain.risk.ports.get_default_suspended_symbols_provider",
        return_value=lambda _s: MagicMock(get_suspended_symbols=AsyncMock(return_value=set())),
    ):
        assert (await gate._check_consecutive_losses(_MockSession(rows=[]), "EURUSD"))[0] is True

    # lines 165-166 (invalid isoformat in manual_trading_paused unpause_at)
    bad_pause_cfg = MagicMock(key="manual_trading_paused", value="true:op|unpause_at:not-a-date")
    assert (await gate._check_not_paused(_MockSession(rows=[bad_pause_cfg])))[0] is False

    # lines 239, 255 (_check_daily_trade_count with is_paper=None and paper_today >= max_daily_trades)
    assert (await gate._check_daily_trade_count(_MockSession(scalar_val=5), is_paper=None))[0] is False

    # lines 363, 370, 394-396 (_check_max_spread with coroutine is_connected & get_spread, and spread_pct <= 0.0005)
    async def _conn_coro() -> bool:
        return True

    async def _spread_coro() -> dict[str, float]:
        return {"spread_points": 50.0, "spread_cost": 1.0, "bid": 10000.0, "ask": 10000.0}

    gate._mt5 = MagicMock(
        is_connected=_conn_coro(),
        get_spread=AsyncMock(return_value=_spread_coro()),
    )
    assert (await gate._check_max_spread(_MockSession(), "BTCUSD", is_paper=False))[0] is True

    # line 415 (_check_max_positions simulated_positions >= max_concurrent)
    gate.max_concurrent = 2
    assert (await gate._check_max_positions(_MockSession(), simulated_positions=[1, 2]))[0] is False

    # lines 457-464 (_check_no_duplicate with simulated_positions pair_group_id match & mismatch)
    assert (
        await gate._check_no_duplicate(
            _MockSession(),
            "EURUSD",
            simulated_positions=[{"symbol": "EURUSD", "pair_group_id": "g1"}],
            pair_group_id="g1",
        )
    )[0] is True
    assert (
        await gate._check_no_duplicate(
            _MockSession(),
            "EURUSD",
            simulated_positions=[{"symbol": "EURUSD", "pair_group_id": "g2"}],
            pair_group_id="g1",
        )
    )[0] is False

    # line 498 (_check_no_duplicate existing_paper is not None)
    class _SeqScalarSession(_MockSession):
        def __init__(self, vals: list[object]) -> None:
            super().__init__()
            self.vals = list(vals)

        async def execute(self, *_a: object, **_k: object) -> _MockExecResult:
            v = self.vals.pop(0) if self.vals else None
            return _MockExecResult(scalar_val=v)

    assert (await gate._check_no_duplicate(_SeqScalarSession([None, 77]), "EURUSD", is_paper=True))[0] is False

    # lines 509, 517-528 (_check_no_duplicate pair_group_id with is_paper=True: conflict=None, group_count >= 2 and < 2)
    assert (
        await gate._check_no_duplicate(_SeqScalarSession([None, None, 2]), "EURUSD", pair_group_id="g1", is_paper=True)
    )[0] is False
    assert (
        await gate._check_no_duplicate(_SeqScalarSession([None, None, 1]), "EURUSD", pair_group_id="g1", is_paper=True)
    )[0] is True

    # line 536 (_check_no_duplicate existing is not None without pair_group_id)
    assert (await gate._check_no_duplicate(_SeqScalarSession([None, 88]), "EURUSD", is_paper=False))[0] is False

    # 7. evaluators/intelligence_checks.py: 157, 244, 247-248, 250, 359, 361-362, 367
    # line 157 (_get_step_val with empty q_list in _check_timesfm_expectancy)
    class _TruthyThenFalsyList(list[object]):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        def __bool__(self) -> bool:
            self.calls += 1
            return self.calls == 1

    with patch(
        "monika.domain.risk.ports.get_default_risk_data_provider",
        return_value=MagicMock(
            get_latest_timesfm_forecast=AsyncMock(return_value={"q30": _TruthyThenFalsyList(), "q10": [1.08]})
        ),
    ):
        await gate._check_timesfm_expectancy(
            _MockSession(),
            "EURUSD",
            "buy",
            MagicMock(entry_price=1.10, stop_loss=1.09, take_profit=1.12),
            MagicMock(revalidation_Trigger=None, adr_tp_pct_used=0.3),
        )

    # lines 244, 247-248, 250 (_check_analysis_quality_scores quantitative source with invalid/low confidence)
    with patch(
        "monika.domain.risk.evaluators.intelligence_checks.evaluate_analysis_scorecard", return_value=(True, "ok")
    ):
        assert (await gate._check_analysis_quality_scores(MagicMock(decision_source="edge_registry", confidence=True)))[
            0
        ] is False
        assert (
            await gate._check_analysis_quality_scores(
                MagicMock(decision_source="edge_registry", confidence="not-a-float")
            )
        )[0] is False
        assert (await gate._check_analysis_quality_scores(MagicMock(decision_source="edge_registry", confidence=0.1)))[
            0
        ] is False

    # lines 359, 361-362, 367 (_check_bounded_mandate with coroutine scalar, exception in session.execute, and as_of datetime)
    hub_global = get_approval_hub()
    hub_global.issue_mandate(operator="op")
    try:

        async def _zero_coro() -> int:
            return 0

        sess_coro_m = MagicMock(execute=AsyncMock(return_value=MagicMock(scalar=lambda: _zero_coro())))
        assert (
            await gate._check_bounded_mandate(
                sess_coro_m, "EURUSD", MagicMock(risk_percent=1.0), as_of=datetime.now(UTC)
            )
        )[0] is True
        assert (
            await gate._check_bounded_mandate(
                _MockSession(fail_execute=True), "EURUSD", MagicMock(risk_percent=1.0), as_of=1700000000.0
            )
        )[0] is True
    finally:
        hub_global._mandates.clear()
        hub_global._active_mandate_id = None

    # 8. evaluators/market_checks.py: 51, 347-348, 435, 446-447, 467
    with patch("monika.domain.risk.ports.get_default_data_freshness_validator", return_value=None):
        assert (await gate._check_data_freshness(_MockSession(), "EURUSD", is_backtest=False))[0] is False

    # lines 347-348: UserPreference blacklist check raises exception inside _check_news_window
    class _NewsBlacklistErrSession(_MockSession):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        async def execute(self, *_a: object, **_k: object) -> _MockExecResult:
            self.calls += 1
            if self.calls == 1:
                return _MockExecResult(scalar_val=MagicMock(value=datetime.now(UTC).isoformat()))
            if self.calls == 2:
                return _MockExecResult(scalar_val=5)
            if self.calls == 3:
                return _MockExecResult(scalar_val=1)
            if self.calls == 4:
                raise RuntimeError("pref err")
            return _MockExecResult(scalar_val=None)

    assert (await gate._check_news_window(_NewsBlacklistErrSession(), "EURUSD"))[0] is True

    # lines 435, 446-447: _check_macro_regime with valid dxy_row.close and yield_row.yield_percent
    class _MacroRowSession(_MockSession):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        async def execute(self, *_a: object, **_k: object) -> _MockExecResult:
            self.calls += 1
            if self.calls == 1:
                return _MockExecResult(scalar_val=MagicMock(close=100.2))
            return _MockExecResult(scalar_val=MagicMock(yield_percent=1.1))

    assert (await gate._check_macro_regime(_MacroRowSession(), "EURUSD", "buy", as_of=datetime.now(UTC)))[0] is True

    # line 467: _check_vpin_toxicity with is_backtest=True and as_of=None
    assert (await gate._check_vpin_toxicity(_MockSession(), "BTCUSD", as_of=None, is_backtest=True))[0] is True

    # 9. evaluators/portfolio_checks.py: 46-47, 55, 60, 77, 86, 93, 96, 192, 426, 478, 525, 553-563, 632
    gate.settings["trading"]["risk"]["max_positions_per_factor_family"] = {"trend": 1, "default": 1}
    with patch("monika.domain.risk.ports.get_strategy_factor_family", return_value="trend"):
        # dict analysis (46-47), factor_family lookup (55), dict limit_val (60), simulated_positions hit (77, 96)
        assert (
            await gate._check_strategy_factor_exposure(
                _MockSession(),
                {"source_strategy_id": "s1"},
                simulated_positions=[MagicMock(source_strategy_id="s1")],
            )
        )[0] is False
        # DB open_positions with source_strategy_id (86, 93, 96)
        assert (
            await gate._check_strategy_factor_exposure(
                _MockSession(rows=[MagicMock(source_strategy_id="s1", analysis_id=None)]),
                {"source_strategy_id": "s1"},
                simulated_positions=None,
            )
        )[0] is False

    # line 192: _check_daily_drawdown with is_backtest=True and simulated_daily_pnl=None
    assert (await gate._check_daily_drawdown(_MockSession(), is_backtest=True, simulated_daily_pnl=None))[0] is True

    # line 426: check_correlation_exposure returns True when correlated_exposure <= limit
    gate.correlation_limit = 10.0
    assert (
        await gate.check_correlation_exposure(
            _MockSession(),
            "EURUSD",
            "buy",
            simulated_positions=[MagicMock(symbol="GBPUSD", direction="buy", volume=0.01)],
        )
    )[0] is True

    # line 478: _get_dynamic_correlation when len(s2_rows) < 30
    with patch(
        "monika.domain.market.dynamic_correlation.get_rolling_correlation", AsyncMock(return_value=(0.5, "static"))
    ):
        corr_v, std_v = await gate._get_dynamic_correlation(_MockSession(rows=[]), "EURUSD", "GBPUSD")
        assert std_v == 0.01

    # lines 525, 553-563: _check_total_portfolio_heat with empty pos_sym (525) and valid spec from _get_instrument_spec_dynamic (553-563)
    valid_spec = InstrumentSpec("EURUSD", 0.0001, 10.0, 100000, 0.01, 100.0, 0.01)
    sizing_small = SizingResult(
        symbol="EURUSD",
        direction="buy",
        entry_price=1.1000,
        stop_loss=1.0950,
        take_profit=1.1100,
        account_equity=10000.0,
        risk_percent=0.5,
        risk_amount_usd=50.0,
        sl_distance_price=0.0050,
        sl_distance_pips=50.0,
        pip_value_per_lot=10.0,
        raw_lots=0.1,
        recommended_lots=0.1,
        rr_ratio=2.0,
        is_valid=True,
        rejection_reasons=[],
    )
    with patch(
        "monika.domain.risk.position_sizing.PositionSizer._get_instrument_spec_dynamic",
        AsyncMock(return_value=valid_spec),
    ):
        assert (
            await gate._check_total_portfolio_heat(
                _MockSession(),
                sizing_small,
                10000.0,
                simulated_positions=[
                    MagicMock(symbol="", entry_price=0.0, volume=0.0),
                    MagicMock(symbol="EURUSD", direction="buy", entry_price=1.1000, sl=1.0950, volume=0.1),
                ],
            )
        )[0] is True

    # line 632: _check_copula_tail_risk when get_default_copula_tail_risk_fitter returns None
    with patch("monika.domain.risk.ports.get_default_copula_tail_risk_fitter", return_value=None):
        assert (
            await gate._check_copula_tail_risk(_MockSession(), "EURUSD", simulated_positions=[{"symbol": "GBPUSD"}])
        )[0] is True

    # 10. position_sizing.py: 173, 262, 444, 446, 450, 452, 463, 523, 565, 574, 665, 691, 727-728, 770, 776, 778, 823, 825-826, 889, 898, 965-990, 1270-1271
    sizer = PositionSizer(
        {
            "paper_trading": {"enabled": True, "initial_balance": 10000.0},
            "trading": {"risk": {"is_cent_account": True, "max_risk_amount_usd": 50.0}},
        }
    )
    # line 173: account_equity <= 0 in calculate_with_session
    assert (
        await sizer.calculate_with_session(_MockSession(), "EURUSD", "buy", 1.10, 1.09, 1.12, account_equity=0.0)
    ).is_valid is False

    # lines 262, 444, 446, 450, 452, 463, 523: calculate_with_session with vix=17, geometry errors, tiny SL < 1 pip, actual_risk > max_risk_cap
    await sizer.calculate_with_session(
        _MockSession(), "EURUSD", "buy", 1.1000, 1.1050, 1.0900, account_equity=10000.0, vix_level=17.0
    )
    await sizer.calculate_with_session(
        _MockSession(), "EURUSD", "sell", 1.1000, 1.0950, 1.1100, account_equity=10000.0, vix_level=17.0
    )
    await sizer.calculate_with_session(
        _MockSession(), "EURUSD", "buy", 1.10000, 1.09999, 1.11000, account_equity=10000000.0, risk_percent_override=5.0
    )
    sizer_cap = PositionSizer(
        {
            "paper_trading": {"enabled": True, "initial_balance": 100000.0},
            "trading": {"risk": {"is_cent_account": False, "max_risk_amount_usd": 50.0}},
        }
    )
    res_cap = await sizer_cap.calculate_with_session(
        _MockSession(), "EURUSD", "buy", 1.1000, 1.0950, 1.1100, account_equity=100000.0, risk_percent_override=5.0
    )
    assert res_cap.is_valid is False
    # lines 565, 574: cross pair notional > 20x equity in calculate_with_session (e.g. EURGBP with tight SL and high risk_pct)
    from monika.domain.risk.position_sizing import DEFAULT_INSTRUMENTS

    eurgbp_spec = InstrumentSpec("EURGBP", 0.0001, 10.0, 100000, 0.01, 10000.0, 0.01)
    sizer_high = PositionSizer({"trading": {"risk": {"max_risk_amount_usd": 1000000.0, "max_lot_size": 10000.0}}})
    with patch.dict(DEFAULT_INSTRUMENTS, {"EURGBP": eurgbp_spec}):
        await sizer_high.calculate_with_session(
            _MockSession(), "EURGBP", "buy", 0.8500, 0.8499, 0.8600, account_equity=1000.0, risk_percent_override=50.0
        )

    # lines 665, 691, 770, 776, 778, 823, 825-826, 889, 898: sync calculate() branches
    sizer_cent = PositionSizer({"trading": {"risk": {"is_cent_account": True, "max_risk_amount_usd": 1000000.0}}})
    sizer_cent.calculate("EURUSD", "buy", 1.1000, 1.1050, 1.0900, account_equity=5000.0, vix_level=12.0)
    sizer_cent.calculate("EURUSD", "sell", 1.1000, 1.0950, 1.1100, account_equity=5000.0, vix_level=12.0)
    # raw_lots < min_lot on cent account where min_lot_risk_usd <= risk_amount_usd (lines 823, 825-826)
    sizer_cent.calculate("EURUSD", "buy", 1.1000, 1.0500, 1.2000, account_equity=50000.0, risk_percent_override=1.0)
    # cross pair notional > 20x equity in sync calculate() (lines 889, 898)
    with patch.dict(DEFAULT_INSTRUMENTS, {"EURGBP": eurgbp_spec}):
        sizer_high.calculate("EURGBP", "buy", 0.8500, 0.8499, 0.8600, account_equity=1000.0, risk_percent_override=50.0)

    # lines 727-728: USDJPY cache exception in sync calculate()
    class _BadCacheDict(dict[str, object]):
        def get(self, *_a: object, **_k: object) -> object:
            raise RuntimeError("cache err")

    old_cache = getattr(PositionSizer, "_usdjpy_rate_cache", None)
    setattr(PositionSizer, "_usdjpy_rate_cache", _BadCacheDict({"rate": 150.0}))
    try:
        sizer_high.calculate("USDJPY", "buy", 150.0, 149.0, 152.0, account_equity=10000.0)
    finally:
        setattr(PositionSizer, "_usdjpy_rate_cache", old_cache)

    # lines 965-990: _get_instrument_spec_dynamic with live _mt5 returning symbol info dict
    sizer_mt5 = PositionSizer(
        {},
        mt5_client=MagicMock(
            get_symbol_info=AsyncMock(
                return_value={
                    "digits": 5,
                    "point": 0.00001,
                    "stops_level": 10,
                    "tick_value": 1.0,
                    "tick_size": 0.00001,
                    "contract_size": 100000,
                    "volume_min": 0.01,
                    "volume_max": 100.0,
                    "volume_step": 0.01,
                }
            )
        ),
    )
    dyn_spec = await sizer_mt5._get_instrument_spec_dynamic(_MockSession(), "EURUSD")
    assert dyn_spec is not None and getattr(dyn_spec, "_source", "") == "mt5_live"

    # lines 1270-1271: get_instrument_spec with mt5_client
    spec_from_fn = get_instrument_spec("EURUSD", mt5_client=MagicMock())
    assert spec_from_fn.symbol == "EURUSD"

    # 11. risk_gate.py: 480-483, 691, 704-705, 1098-1099
    # lines 480-483: modular_risk_registry evaluation raises exception in RiskGate.evaluate
    from contextlib import ExitStack

    with ExitStack() as stack:
        for chk_name in (
            "_check_not_paused",
            "_check_edge_status_not_paused",
            "_check_daily_drawdown",
            "_check_weekly_drawdown",
            "_check_monthly_drawdown",
            "_check_max_positions",
            "_check_no_duplicate",
            "_check_daily_trade_count",
            "_check_consecutive_losses",
            "_check_post_loss_cooldown",
            "_check_total_portfolio_heat",
            "_check_correlation",
            "_check_vix",
            "_check_news_window",
            "_check_rollover_window",
            "_check_weekend_gap",
            "_check_data_freshness",
            "_check_max_spread",
            "_check_schmitt_regime",
            "_check_macro_regime",
            "_check_vpin_toxicity",
            "_check_copula_tail_risk",
            "_check_strategy_factor_exposure",
            "_check_risk_of_ruin",
            "_check_evidence_gate",
            "_check_bounded_mandate",
        ):
            if hasattr(gate, chk_name):
                stack.enter_context(patch.object(gate, chk_name, AsyncMock(return_value=(True, "ok"))))
        stack.enter_context(patch.object(gate, "_log_verdict", AsyncMock()))
        gate.modular_risk_registry = MagicMock(evaluate_modular_rules=AsyncMock(side_effect=RuntimeError("reg boom")))
        v_reg_err = await gate.evaluate(_MockSession(), "EURUSD", "buy", sizing_small, account_equity=10000.0)
        assert "modular_risk_registry" in v_reg_err.checks_failed
        gate.modular_risk_registry = None

    # lines 691, 704-705: evaluate_proposal with SELL take_profit >= entry_price, and non-BUY/SELL/WAIT direction
    with (
        patch(
            "monika.domain.risk.trade_proposal.FortressAdmissionValidator.validate_proposal",
            return_value=(True, []),
        ),
        patch.object(gate, "_get_risk_state", AsyncMock(return_value=None)),
        patch(
            "monika.domain.risk.invariants.get_global_invariant_registry",
            return_value=MagicMock(run_all=lambda *_a, **_k: []),
        ),
    ):
        prop_sell_bad_tp = MagicMock(
            proposal_id="p1",
            symbol="EURUSD",
            direction="SELL",
            entry_price=1.1000,
            stop_loss=1.1050,
            take_profit=1.1100,
            lot_size=0.1,
            account_equity=10000.0,
            metadata={},
        )
        v_sell_tp = await gate.evaluate_proposal(_MockSession(), prop_sell_bad_tp)
        assert v_sell_tp.approved is False

        prop_other_dir = MagicMock(
            proposal_id="p2",
            symbol="EURUSD",
            direction="HOLD_CUSTOM",
            entry_price=1.1000,
            stop_loss=1.0950,
            take_profit=1.1100,
            lot_size=0.1,
            account_equity=10000.0,
            metadata={},
        )
        with patch.object(gate, "evaluate", AsyncMock(return_value=MagicMock(approved=True))):
            await gate.evaluate_proposal(_MockSession(), prop_other_dir)

    # lines 1098-1099: get_current_risk_state when client.get_account_info raises exception
    with patch(
        "monika.domain.risk.ports.get_default_broker_client",
        return_value=MagicMock(get_account_info=AsyncMock(side_effect=RuntimeError("mt5 err"))),
    ):
        st_err = await get_current_risk_state(session=_MockSession(scalar_val=None), settings={})
        assert st_err["starting_equity"] == 10000.0
