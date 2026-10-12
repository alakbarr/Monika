import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from analysis.validators.adjudication_verifier import verify_adjudication

@pytest.mark.asyncio
async def test_adjudication_trust_weights():
    settings = {
        'llm': {
            'task_roles': {
                'stage2_adjudicator': {'primary': 'dummy_model'}
            }
        }
    }
    
    symbol = "EURUSD"
    specialist_biases = {"technical": "bullish", "macro": "bearish", "sentiment": "neutral"}
    specialist_confidence = {"technical": 0.8, "macro": 0.6, "sentiment": 0.5}
    specialist_trust_weights = {"technical": 0.3, "macro": 0.9, "sentiment": 0.5}
    
    final_decision = "buy"
    rationale = "Buying despite macro bearish because technical says buy."
    
    mock_client = AsyncMock()
    mock_client.classify_json.return_value = {
        'verdict': 'FLAG_FOR_REVIEW',
        'adjudication_rule_correctly_applied': False,
        'expected_outcome_per_rules': 'wait',
        'mismatch_explanation': 'Technical trust weight is low (0.3).'
    }
    
    with patch('analysis.validators.adjudication_verifier.get_client_for_task', return_value=mock_client):
        result = await verify_adjudication(
            settings, symbol, specialist_biases, specialist_confidence,
            final_decision, rationale, specialist_trust_weights=specialist_trust_weights
        )
        
        assert isinstance(result, dict)
        assert result['verdict'] == 'FLAG_FOR_REVIEW'
        assert result['adjudication_rule_correctly_applied'] is False


@pytest.mark.asyncio
async def test_adjudication_full_bullish_alignment_buy():
    settings = {'llm': {'task_roles': {'stage2_adjudicator': {'primary': 'dummy_model'}}}}
    
    symbol = "XAUUSD"
    specialist_biases = {"technical": "bullish", "macro": "bullish", "sentiment": "bullish"}
    specialist_confidence = {"technical": "high", "macro": "high", "sentiment": "high"}
    specialist_trust_weights = {"technical": 1.0, "macro": 1.0, "sentiment": 0.8}
    
    final_decision = "buy"
    rationale = "Full bullish alignment across all 3 specialists. Confluence 8/14 >= threshold 6/14."
    
    mock_client = AsyncMock()
    mock_client.classify_json.return_value = {
        'verdict': 'CONFIRM',
        'adjudication_rule_correctly_applied': True,
        'is_conditional_wait': False,
        'expected_outcome_per_rules': 'buy',
        'mismatch_explanation': ''
    }
    
    with patch('analysis.validators.adjudication_verifier.get_client_for_task', return_value=mock_client):
        result = await verify_adjudication(
            settings, symbol, specialist_biases, specialist_confidence,
            final_decision, rationale, specialist_trust_weights=specialist_trust_weights,
            confluence_score=8, effective_threshold=6
        )
        
        assert result['verdict'] == 'CONFIRM'
        assert result['adjudication_rule_correctly_applied'] is True
        assert result['is_conditional_wait'] is False


@pytest.mark.asyncio
async def test_adjudication_full_bullish_alignment_conditional_wait():
    """Memverifikasi bahwa keputusan WAIT yang rasional (menunggu pullback/threshold) dikonfirmasi (CONFIRM)."""
    settings = {'llm': {'task_roles': {'stage2_adjudicator': {'primary': 'dummy_model'}}}}
    
    symbol = "XAUUSD"
    specialist_biases = {"technical": "bullish", "macro": "bullish", "sentiment": "bullish"}
    specialist_confidence = {"technical": "high", "macro": "high", "sentiment": "high"}
    specialist_trust_weights = {"technical": 1.0, "macro": 1.0, "sentiment": 0.8}
    
    final_decision = "wait"
    rationale = "All specialists bullish, but price is extended above H4 OB. Confluence 5/14 is below threshold 6/14. Waiting for pullback to 2650 support."
    trigger = {"type": "price_level", "symbol": "XAUUSD", "price": 2650.0, "direction": "below"}
    
    mock_client = AsyncMock()
    mock_client.classify_json.return_value = {
        'verdict': 'CONFIRM',
        'adjudication_rule_correctly_applied': True,
        'is_conditional_wait': True,
        'expected_outcome_per_rules': 'wait',
        'mismatch_explanation': 'Valid conditional wait for pullback to key support.'
    }
    
    with patch('analysis.validators.adjudication_verifier.get_client_for_task', return_value=mock_client):
        result = await verify_adjudication(
            settings, symbol, specialist_biases, specialist_confidence,
            final_decision, rationale, specialist_trust_weights=specialist_trust_weights,
            confluence_score=5, effective_threshold=6, reeval_trigger=trigger
        )
        
        assert result['verdict'] == 'CONFIRM'
        assert result['adjudication_rule_correctly_applied'] is True
        assert result['is_conditional_wait'] is True


@pytest.mark.asyncio
async def test_adjudication_full_bullish_alignment_contradiction_sell():
    """Memverifikasi bahwa keputusan SELL saat semua spesialis BULLISH ditandai sebagai CONTRADICTS_OWN_FRAMEWORK."""
    settings = {'llm': {'task_roles': {'stage2_adjudicator': {'primary': 'dummy_model'}}}}
    
    symbol = "XAUUSD"
    specialist_biases = {"technical": "bullish", "macro": "bullish", "sentiment": "bullish"}
    specialist_confidence = {"technical": "high", "macro": "high", "sentiment": "high"}
    specialist_trust_weights = {"technical": 1.0, "macro": 1.0, "sentiment": 0.8}
    
    final_decision = "sell"
    rationale = "Deciding to sell because price feels too high."
    
    mock_client = AsyncMock()
    mock_client.classify_json.return_value = {
        'verdict': 'CONTRADICTS_OWN_FRAMEWORK',
        'adjudication_rule_correctly_applied': False,
        'is_conditional_wait': False,
        'expected_outcome_per_rules': 'buy',
        'mismatch_explanation': 'Direct contradiction: All specialists are bullish, but decision is SELL.'
    }
    
    with patch('analysis.validators.adjudication_verifier.get_client_for_task', return_value=mock_client):
        result = await verify_adjudication(
            settings, symbol, specialist_biases, specialist_confidence,
            final_decision, rationale, specialist_trust_weights=specialist_trust_weights
        )
        
        assert result['verdict'] == 'CONTRADICTS_OWN_FRAMEWORK'
        assert result['adjudication_rule_correctly_applied'] is False


@pytest.mark.asyncio
async def test_adjudication_prompt_extras_passed():
    """Memverifikasi bahwa parameter tambahan (confluence, threshold, trigger) diteruskan ke prompt."""
    settings = {'llm': {'task_roles': {'stage2_adjudicator': {'primary': 'dummy_model'}}}}
    
    symbol = "EURUSD"
    specialist_biases = {"technical": "bearish", "macro": "bearish", "sentiment": "bearish"}
    specialist_confidence = {"technical": "high", "macro": "medium", "sentiment": "high"}
    
    trigger = {"type": "price_level", "price": 1.0850}
    
    mock_client = AsyncMock()
    mock_client.classify_json.return_value = {
        'verdict': 'CONFIRM',
        'adjudication_rule_correctly_applied': True,
        'expected_outcome_per_rules': 'wait',
        'mismatch_explanation': ''
    }
    
    with patch('analysis.validators.adjudication_verifier.get_client_for_task', return_value=mock_client):
        await verify_adjudication(
            settings, symbol, specialist_biases, specialist_confidence,
            "wait", "Waiting for retest of 1.0850 resistance",
            confluence_score=4, effective_threshold=7, reeval_trigger=trigger
        )
        
        call_kwargs = mock_client.classify_json.call_args.kwargs
        prompt_text = call_kwargs['prompt']
        assert "Confluence Score: 4" in prompt_text
        assert "Effective Confluence Threshold: 7" in prompt_text
        assert "Re-evaluation Trigger" in prompt_text
        assert "1.085" in prompt_text


@pytest.mark.asyncio
async def test_adjudication_unverified_on_exception():
    """Memverifikasi fallback UNVERIFIED jika model verifier melempar exception."""
    settings = {'llm': {'task_roles': {'stage2_adjudicator': {'primary': 'dummy_model'}}}}
    
    mock_client = AsyncMock()
    mock_client.classify_json.side_effect = RuntimeError("API connection timeout")
    
    with patch('analysis.validators.adjudication_verifier.get_client_for_task', return_value=mock_client):
        result = await verify_adjudication(
            settings, "XAUUSD", {"technical": "bullish"}, {"technical": "high"},
            "buy", "Rationale"
        )
        
        assert result['verdict'] == 'UNVERIFIED'
        assert result['adjudication_rule_correctly_applied'] is None
        assert "API connection timeout" in result['mismatch_explanation']

