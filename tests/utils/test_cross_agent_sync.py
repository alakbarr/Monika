import pytest
from utils.protocol.cross_agent_sync import CrossAgentSynchronizer

@pytest.mark.asyncio
async def test_detect_contradictions():
    sync = CrossAgentSynchronizer()
    pa_results = {
        "EURUSD": {"decision": "buy", "confidence": 0.8},
        "USDJPY": {"decision": "buy", "confidence": 0.6} # Implies weak USD, but EURUSD buy also implies weak USD. Wait, EURUSD buy = USD weak. USDJPY buy = USD strong. CONTRADICTION!
    }
    
    contradictions = sync.detect_contradictions(pa_results)
    assert len(contradictions) == 1
    assert contradictions[0]["expected_corr"] == -0.80 # correlation between EURUSD and USDJPY

@pytest.mark.asyncio
async def test_apply_suppression():
    sync = CrossAgentSynchronizer()
    pa_results = {
        "EURUSD": {"decision": "buy", "confidence": 0.8},
        "USDJPY": {"decision": "buy", "confidence": 0.6}
    }
    
    contradictions = sync.detect_contradictions(pa_results)
    updated, suppressed = sync.apply_selective_suppression(pa_results, contradictions)
    assert len(suppressed) == 1
    assert "USDJPY" in suppressed
    assert updated["USDJPY"]["decision"] == "wait"
