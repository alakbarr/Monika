import pytest
from utils.llm.cache_breakpoint_manager import CacheBreakpointManager
from utils.llm.prompt_compressor import truncate_to_budget
from analysis.debate.bull_analyst import generate_bull_advocacy
from analysis.debate.bear_analyst import generate_bear_dissent
from unittest.mock import AsyncMock, MagicMock


def test_cache_breakpoint_manager_dynamic_padding():
    short_prompt = 'Short prompt for single turn classification.' * 5
    padded_short = CacheBreakpointManager.pad_system_prompt_to_threshold(
        short_prompt, model_name='claude-3-7-sonnet', provider_name='anthropic'
    )
    assert padded_short == short_prompt

    # For claude-3-7-sonnet, min_chars is 4200. 70% is 2940.
    medium_prompt = ('You are an elite quantitative analyst with SMC skills. ' * 55)[:3100]
    padded_medium = CacheBreakpointManager.pad_system_prompt_to_threshold(
        medium_prompt, model_name='claude-3-7-sonnet', provider_name='anthropic'
    )
    assert len(padded_medium) >= 4200
    assert '=== CANONICAL SYSTEM GOVERNANCE' in padded_medium


def test_prompt_compressor_protects_stress_test_and_invalidation():
    long_rationale = (
        'Market is expanding following H4 BOS. Confluence score is 11/14. '
        'Entry zone at 1.0850. Order block confirmed. ' * 30
    )
    tail_blocks = (
        '\n[STRESS TEST: Bearish reversal if DXY surges above 104.50]\n'
        '[INVALIDATION: Price closes below 1.0810 on H4 body close]'
    )
    full_text = long_rationale + tail_blocks

    truncated = truncate_to_budget(full_text, max_tokens=150)
    assert '[TRUNCATED' in truncated
    assert '[STRESS TEST: Bearish reversal if DXY surges above 104.50]' in truncated
    assert '[INVALIDATION: Price closes below 1.0810 on H4 body close]' in truncated


@pytest.mark.asyncio
async def test_bull_and_bear_analyst_fallback_schema():
    mock_client = MagicMock()
    mock_client.generate_content = AsyncMock(side_effect=RuntimeError('API error'))
    mock_client.default_temperature = 0.2
    mock_client.max_tokens = 4096

    orig_ctx = {'decision': 'buy', 'symbol': 'EURUSD'}
    fact_sheet = {'dxy': 'weakening'}
    bull_claim = {'bull_thesis': 'Upside continuation'}

    bull_res = await generate_bull_advocacy(mock_client, 'EURUSD', orig_ctx, fact_sheet)
    assert bull_res['parse_error'] is True
    assert 'evidence_cited' in bull_res
    assert isinstance(bull_res['evidence_cited'], list)
    assert len(bull_res['evidence_cited']) >= 1

    bear_res = await generate_bear_dissent(mock_client, 'EURUSD', orig_ctx, bull_claim, fact_sheet)
    assert bear_res['parse_error'] is True
    assert 'evidence_cited' in bear_res
    assert isinstance(bear_res['evidence_cited'], list)
    assert len(bear_res['evidence_cited']) >= 1
