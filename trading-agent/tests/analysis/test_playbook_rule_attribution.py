import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock
from database.models import PlaybookRuleAttribution, DecisionReflection
from analysis.memory.lesson_consolidator import record_playbook_rule_outcome
from analysis.memory.session_search import SessionSearchEngine


@pytest.mark.asyncio
async def test_playbook_rule_attribution_model_and_recording():
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None
    mock_session.execute.return_value = mock_result
    
    rule = "Wait for London session liquidity sweep before buying EURUSD demand"
    symbol = "EURUSD"
    
    # 1. Record first win
    attr = await record_playbook_rule_outcome(
        session=mock_session,
        rule_text=rule,
        symbol=symbol,
        was_profitable=True,
        pnl=150.0
    )
    
    assert attr.symbol == "EURUSD"
    assert attr.times_triggered == 1
    assert attr.wins_count == 1
    assert attr.losses_count == 0
    assert attr.win_rate == 1.0
    assert attr.total_pnl == 150.0
    assert attr.status == "active"


@pytest.mark.asyncio
async def test_playbook_rule_auto_deprecation_on_low_win_rate():
    mock_session = AsyncMock()
    
    existing_attr = PlaybookRuleAttribution(
        rule_hash="eurusd_test_hash",
        symbol="EURUSD",
        rule_text="Test risky rule",
        status="active",
        times_triggered=4,
        wins_count=1,
        losses_count=3,
        total_pnl=-80.0,
        win_rate=0.25,
        promoted_at=datetime.now(timezone.utc)
    )
    
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = existing_attr
    mock_session.execute.return_value = mock_result
    
    # 5th trade is a loss -> total 1 win, 4 losses -> win rate 0.20 < 0.40 -> auto-deprecated
    updated = await record_playbook_rule_outcome(
        session=mock_session,
        rule_text="Test risky rule",
        symbol="EURUSD",
        was_profitable=False,
        pnl=-40.0,
        min_eval_deprecate=5,
        deprecation_win_rate=0.40
    )
    
    assert updated.times_triggered == 5
    assert updated.wins_count == 1
    assert updated.losses_count == 4
    assert updated.win_rate == 0.20
    assert updated.status == "deprecated"
    assert updated.deprecated_at is not None
    assert "low_win_rate" in updated.deprecation_reason


@pytest.mark.asyncio
async def test_playbook_rule_auto_elevation_to_golden():
    mock_session = AsyncMock()
    
    existing_attr = PlaybookRuleAttribution(
        rule_hash="gold_rule_hash",
        symbol="XAUUSD",
        rule_text="High confluence golden rule",
        status="active",
        times_triggered=4,
        wins_count=3,
        losses_count=1,
        total_pnl=300.0,
        win_rate=0.75,
        promoted_at=datetime.now(timezone.utc)
    )
    
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = existing_attr
    mock_session.execute.return_value = mock_result
    
    # 5th trade is a win -> 4 wins, 1 loss -> win rate 0.80 >= 0.65 -> elevated to golden
    updated = await record_playbook_rule_outcome(
        session=mock_session,
        rule_text="High confluence golden rule",
        symbol="XAUUSD",
        was_profitable=True,
        pnl=120.0,
        min_eval_deprecate=5,
        golden_win_rate=0.65
    )
    
    assert updated.times_triggered == 5
    assert updated.wins_count == 4
    assert updated.losses_count == 1
    assert updated.win_rate == 0.80
    assert updated.status == "golden"


def test_hybrid_multi_factor_precedent_scoring():
    engine = SessionSearchEngine()
    now = datetime.now(timezone.utc)
    
    # Case 1: High match (matching regime, matching tokens, profitable, recent)
    ref_high = DecisionReflection(
        id=1,
        symbol="EURUSD",
        decision="buy",
        reflection_text="Market in trending_bull regime. Clean demand zone entry.",
        rationale_summary="EURUSD buy in trending_bull with strong macro support.",
        was_profitable=True,
        outcome_pnl_usd=250.0,
        created_at=now - timedelta(days=2)
    )
    
    setup_tokens = {"eurusd", "demand", "macro", "trending_bull"}
    score_high = engine.compute_precedent_hybrid_score(
        reflection=ref_high,
        current_regime="trending_bull",
        setup_tokens=setup_tokens,
        now=now
    )
    
    # Case 2: Low match (different regime, loss, old)
    ref_low = DecisionReflection(
        id=2,
        symbol="EURUSD",
        decision="buy",
        reflection_text="Market in high_volatility_chop regime. Failed breakout.",
        rationale_summary="EURUSD stopped out due to sudden news catalyst.",
        was_profitable=False,
        outcome_pnl_usd=-180.0,
        created_at=now - timedelta(days=60)
    )
    
    score_low = engine.compute_precedent_hybrid_score(
        reflection=ref_low,
        current_regime="trending_bull",
        setup_tokens=setup_tokens,
        now=now
    )
    
    assert score_high["composite"] > score_low["composite"]
    assert score_high["regime_score"] == 1.0
    assert score_high["outcome_score"] == 1.0
    assert score_low["outcome_score"] == 0.1
    assert score_high["recency_score"] > score_low["recency_score"]
