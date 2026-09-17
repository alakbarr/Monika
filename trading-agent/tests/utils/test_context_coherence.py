import pytest
from utils.protocol.context_coherence import compute_bundle_coherence_issues, compute_cross_pair_contradictions

def test_compute_bundle_coherence_issues():
    # Test VIX vs risk_sentiment
    data = {
        'get_fundamental_brief': {'risk_sentiment': 'risk-on'},
        'get_vix': {'latest': {'close': 35.0}}
    }
    issues = compute_bundle_coherence_issues(data)
    assert len(issues) == 1
    assert "VIX=35.0" in issues[0]

    # Test DXY vs USD bias
    data2 = {
        'get_fundamental_brief': {'currency_bias': {'USD': 'bearish'}},
        'get_dxy': {'trend_5d': 'strengthening'}
    }
    issues2 = compute_bundle_coherence_issues(data2)
    assert len(issues2) == 1
    assert "DXY 5-day trend='strengthening'" in issues2[0]

def test_compute_cross_pair_contradictions():
    analyses = {
        'EURUSD': {'decision': 'buy', 'confidence': 0.8}, # USD WEAK
        'USDJPY': {'decision': 'buy', 'confidence': 0.9}, # USD STRONG
    }
    contradictions = compute_cross_pair_contradictions(analyses)
    assert len(contradictions) == 1
    assert 'EURUSD' in contradictions[0]['weak_usd_symbols']
    assert 'USDJPY' in contradictions[0]['strong_usd_symbols']
    assert contradictions[0]['recommended_filter'] == 'USD_STRONG'

def test_no_contradictions():
    analyses = {
        'EURUSD': {'decision': 'buy', 'confidence': 0.8}, # USD WEAK
        'GBPUSD': {'decision': 'buy', 'confidence': 0.7}, # USD WEAK
    }
    contradictions = compute_cross_pair_contradictions(analyses)
    assert len(contradictions) == 0
