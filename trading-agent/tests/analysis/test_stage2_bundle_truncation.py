import pytest
from unittest.mock import AsyncMock
from analysis.prefetch.stage2_prefetcher import Stage2DataBundler


@pytest.mark.asyncio
async def test_stage2_bundle_truncation_preserves_smc_zones():
    """Memastikan bahwa bundler Stage 2 tidak memotong paksa SMC zones meskipun bundle sangat besar (>40k chars)."""
    session = AsyncMock()
    settings = {
        "trading": {
            "cost_mode": "lite"
        },
        "analysis": {
            "stage2_max_bundle_chars": 2000  # Set limit kecil untuk memaksa kompresi
        }
    }
    bundler = Stage2DataBundler(session, settings)
    
    long_history = {
        "bars": [
            {"time": f"2026-03-0{i%9+1}T12:00:00Z", "open": 1.1000 + i*0.001, "high": 1.1050 + i*0.001, "low": 1.0950 + i*0.001, "close": 1.1020 + i*0.001}
            for i in range(50)
        ]
    }
    
    smc_data = {
        "order_blocks": [
            {"timeframe": "H4", "type": "bullish", "high": 1.1050, "low": 1.1020, "mitigated": False},
            {"timeframe": "H4", "type": "bearish", "high": 1.1200, "low": 1.1180, "mitigated": False},
            {"timeframe": "D1", "type": "bullish", "high": 1.0900, "low": 1.0850, "mitigated": False}
        ],
        "fair_value_gaps": [
            {"timeframe": "H4", "type": "bullish_fvg", "top": 1.1080, "bottom": 1.1060},
            {"timeframe": "H4", "type": "bearish_fvg", "top": 1.1150, "bottom": 1.1130}
        ]
    }
    
    async def mock_execute(tool_name, inp):
        if "price_history" in tool_name:
            return long_history
        if "smc_zones" in tool_name:
            return smc_data
        if "confluence" in tool_name:
            return {"buy_potential_score": 8, "sell_potential_score": 4, "reference_price": 1.1000}
        return {"dummy": "value" * 30}

    bundler.executor.execute = AsyncMock(side_effect=mock_execute)
    
    bundle, raw_data = await bundler.fetch_bundle("EURUSD")
    
    # Verifikasi bahwa output TIDAK memuat teks truncation rusak
    assert "…(truncated)" not in bundle, "Bundle memuat pemotongan string rusak pada SMC zones!"
    assert "[TRUNCATED" not in bundle, "Bundle terpotong secara destruktif!"
    
    # Verifikasi data SMC tetap ada di dalam bundle teks
    assert "bullish" in bundle.lower()
    assert "fair_value_gaps" in bundle.lower() or "order_blocks" in bundle.lower()
