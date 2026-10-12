import pytest
from unittest.mock import AsyncMock, MagicMock
from analysis.subagent.adhoc_manager import AdHocSubagentManager, AdHocInvestigationVerdict
from analysis.tools.quant_sandbox.rpc_server import QuantSandboxRpcServer, QuantSandboxClient


@pytest.mark.asyncio
async def test_quant_sandbox_stats():
    client = QuantSandboxClient()
    series = [100.0, 102.0, 101.5, 103.0, 102.5, 104.0, 105.0, 106.0, 105.5, 107.0, 108.0, 107.5, 109.0, 110.0, 111.0, 112.0]
    res = await client.compute_stats(series)

    assert res["count"] == 16
    assert "mean" in res
    assert "std" in res
    assert "z_score" in res
    assert "regime_bias" in res


@pytest.mark.asyncio
async def test_quant_sandbox_correlation():
    client = QuantSandboxClient()
    series_a = [1.0, 2.0, 3.0, 4.0, 5.0]
    series_b = [2.0, 4.0, 6.0, 8.0, 10.0]
    res = await client.compute_correlation(series_a, series_b)

    assert res["samples"] == 5
    assert res["correlation"] == 1.0
    assert res["strong_correlation"] is True


@pytest.mark.asyncio
async def test_quant_sandbox_code_execution():
    client = QuantSandboxClient()
    code = "res = 40 + 2\nprint(f'The answer is {res}')"
    res = await client.execute_code(code)

    assert res["success"] is True
    assert "The answer is 42" in res["output"]


@pytest.mark.asyncio
async def test_adhoc_manager_verdict_caching():
    mgr = AdHocSubagentManager()
    # Cache a verdict directly
    verdict = AdHocInvestigationVerdict(
        investigation_id="test_inv_1",
        symbol="XAUUSD",
        topic="CPI Volatility Spike",
        anomaly_detected=True,
        confidence=0.85,
        recommendation="reduce_risk",
        findings="Massive spread expansion detected post-CPI.",
    )
    mgr._verdicts["XAUUSD"] = verdict

    cached = mgr.get_latest_verdict("XAUUSD", max_age_seconds=600)
    assert cached is not None
    assert cached.anomaly_detected is True
    assert cached.recommendation == "reduce_risk"
