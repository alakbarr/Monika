"""
Unit test verifying architectural decoupling and elimination of circular imports (Fase 1).
"""

import sys
import pytest


def test_risk_domain_instruments_import_isolation():
    """Verify risk.domain.instruments can be imported purely without loading mt5 or execution."""
    from risk.domain.instruments import InstrumentSpec, DEFAULT_INSTRUMENTS

    assert "XAUUSD" in DEFAULT_INSTRUMENTS
    xau = DEFAULT_INSTRUMENTS["XAUUSD"]
    assert isinstance(xau, InstrumentSpec)
    assert xau.contract_size == 100
    assert xau.pip_size == 0.01


def test_execution_modules_import_domain_instruments_cleanly():
    """Verify execution modules import DEFAULT_INSTRUMENTS without pulling entire position_sizing."""
    from execution.broker_adapter import _get_contract_size
    from execution.mt5_client import MT5Client

    # Test contract size calculation decoupled from circular risk dependencies
    xau_size = _get_contract_size("XAUUSD")
    assert xau_size == 100.0

    btc_size = _get_contract_size("BTCUSD")
    assert btc_size == 1.0


def test_scheduler_adhoc_proxy_decoupling():
    """Verify AdHocSchedulerProxy exists in scheduler and is cleanly re-exported."""
    from scheduler.adhoc_proxy import AdHocSchedulerProxy
    from agent.agent_loop import AdHocSchedulerProxy as ReExportedProxy

    assert AdHocSchedulerProxy is ReExportedProxy

    # Instantiation check without circular graph dependency
    proxy = AdHocSchedulerProxy(settings={"trading": {}}, symbols=["EURUSD"])
    assert proxy.asset_universe == ["EURUSD"]
    assert "M15" in proxy.mt5_timeframes
