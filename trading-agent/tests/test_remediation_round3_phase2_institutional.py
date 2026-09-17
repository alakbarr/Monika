import pytest
import os
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Test 1: F2-1 Redundant MT5 Multi-Terminal Gateway & Failover
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_f2_1_mt5_redundant_failover_and_fallback():
    """Verify automated failover to secondary MT5 gateway and fallback to primary."""
    from execution.mt5_client import MT5Client

    with patch.dict(os.environ, {
        "MT5_ACCOUNT": "111111",
        "MT5_SERVER": "Broker-Primary",
        "MT5_PATH": "C:/MT5_Primary/terminal64.exe",
        "MT5_SECONDARY_ACCOUNT": "222222",
        "MT5_SECONDARY_PASSWORD": "SecPassword",
        "MT5_SECONDARY_SERVER": "Broker-Secondary",
        "MT5_SECONDARY_PATH": "C:/MT5_Secondary/terminal64.exe",
    }):
        client = MT5Client()
        client._run = AsyncMock(return_value=True)
        try:
            assert client.active_gateway == "primary"
            assert client.account == 111111
            assert client.secondary_account == 222222

            # 1. Simulate failover to secondary
            failover_ok = await client.failover_to_secondary()
            assert failover_ok is True
            assert client.active_gateway == "secondary"
            path, acc, pwd, serv = client.get_current_gateway_params()
            assert acc == 222222
            assert serv == "Broker-Secondary"

            # 2. Simulate fallback to primary
            fallback_ok = await client.fallback_to_primary()
            assert fallback_ok is True
            assert client.active_gateway == "primary"
            path, acc, pwd, serv = client.get_current_gateway_params()
            assert acc == 111111
            assert serv == "Broker-Primary"
        finally:
            client._executor.shutdown(wait=False)


# ---------------------------------------------------------------------------
# Test 2: F2-2 Prometheus / OpenMetrics Exporter
# ---------------------------------------------------------------------------

def test_f2_2_prometheus_metrics_export():
    """Verify Prometheus metric collection and string formatting."""
    from logging_observability.metrics_exporter import MetricsCollector

    collector = MetricsCollector()
    collector.set_gauge("test_equity", 15420.50)
    collector.inc_counter("test_trades_total", 3.0, labels={"symbol": "EURUSD", "status": "win"})
    collector.record_histogram("test_analysis_latency", 1.25)
    collector.record_histogram("test_analysis_latency", 2.15)

    prom_text = collector.generate_prometheus_metrics()
    assert "# HELP trading_agent_test_equity Gauge metric for test_equity" in prom_text
    assert "# TYPE trading_agent_test_equity gauge" in prom_text
    assert "trading_agent_test_equity 15420.5" in prom_text
    assert 'trading_agent_test_trades_total{status="win",symbol="EURUSD"} 3.0' in prom_text
    assert "trading_agent_test_analysis_latency_count 2" in prom_text
    assert "trading_agent_test_analysis_latency_sum 3.4000" in prom_text


def test_f2_2_dashboard_api_metrics_endpoint():
    """Verify FastAPI /api/metrics endpoint returns Prometheus formatted text."""
    from fastapi.testclient import TestClient
    from logging_observability.dashboard.api import app

    client = TestClient(app)
    resp = client.get("/api/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    assert "trading_agent_agent_uptime_seconds" in resp.text


# ---------------------------------------------------------------------------
# Test 3: F2-3 Monte Carlo Stress Tester & Scenario Shock Engine
# ---------------------------------------------------------------------------

def test_f2_3_monte_carlo_stress_tester_comprehensive():
    """Verify Monte Carlo 10,000 permutations, ruin probability, and slippage shock."""
    from backtest.monte_carlo_engine import MonteCarloStressTester

    tester = MonteCarloStressTester(seed=123)

    # 30 trades: 18 wins (+2.5%), 12 losses (-1.5%)
    returns = [0.025 if i < 18 else -0.015 for i in range(30)]

    # 1. Permutation Drawdown Test
    res = tester.run_permutation_drawdown_test(returns, num_simulations=1000, initial_equity=10000.0)
    assert res["num_simulations"] == 1000
    assert res["var_95_drawdown_pct"] > 0.0
    assert res["var_99_drawdown_pct"] >= res["var_95_drawdown_pct"]
    assert res["ruin_probability_pct"] >= 0.0
    assert res["final_equity_distribution"]["median_p50"] > 10000.0

    # 2. Slippage Shock Test
    shock_res = tester.run_slippage_spread_shock_test(
        trade_returns=returns,
        slippage_multipliers=[1.0, 3.0],
        num_simulations=500,
        initial_equity=10000.0
    )
    assert "shock_1x_slippage" in shock_res
    assert "shock_3x_slippage" in shock_res
    # 3x slippage shock should lead to higher or equal drawdown and lower median equity
    assert shock_res["shock_3x_slippage"]["var_95_drawdown_pct"] >= shock_res["shock_1x_slippage"]["var_95_drawdown_pct"]


# ---------------------------------------------------------------------------
# Test 4: F2-4 Systemic Correlation Matrix & Directional USD Exposure
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_f2_4_systemic_correlation_matrix_and_usd_exposure():
    """Verify NxN correlation matrix computation and USD concentration capping."""
    from risk.portfolio_correlation_gate import compute_portfolio_correlation_matrix, filter_correlated_proposals

    mock_session = AsyncMock()

    symbols = ["EURUSD", "GBPUSD", "USDJPY"]
    with patch("risk.portfolio_correlation_gate.get_rolling_correlation", AsyncMock(return_value=(0.75, "db"))):
        matrix = await compute_portfolio_correlation_matrix(mock_session, symbols)
        assert len(matrix) == 3
        assert matrix["EURUSD"]["EURUSD"] == 1.0
        assert matrix["EURUSD"]["GBPUSD"] == 0.75

    # Test Systemic USD Exposure Cap
    # 4 Buy proposals on USD quote pairs -> all Short USD
    proposals = [
        ("EURUSD", {"decision": "buy", "confidence": 0.85}),
        ("GBPUSD", {"decision": "buy", "confidence": 0.80}),
        ("XAUUSD", {"decision": "buy", "confidence": 0.78}),
        ("AUDUSD", {"decision": "buy", "confidence": 0.70}),
    ]

    with patch("risk.portfolio_correlation_gate.get_rolling_correlation", AsyncMock(return_value=(0.20, "db"))):
        # max_usd_exposure = 3 -> 4th trade should be rejected by systemic concentration cap
        kept, rejected = await filter_correlated_proposals(
            mock_session, proposals, threshold=0.65, max_usd_exposure=3
        )
        assert len(kept) == 3
        assert len(rejected) == 1
        assert "Systemic concentration cap" in rejected[0][2]
        assert rejected[0][0] == "AUDUSD"
