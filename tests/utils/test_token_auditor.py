"""
Unit test untuk TokenAuditor service.
"""
import pytest
from utils.analytics.token_auditor import TokenAuditor


from contextlib import asynccontextmanager
from unittest.mock import patch
from datetime import datetime, timezone
from database.models import TokenUsageLog


@pytest.mark.asyncio
async def test_token_auditor_summary_and_breakdowns(db_session):
    # Insert sample token usage log to test populated breakdown branches
    sample_log = TokenUsageLog(
        task_role="stage2_per_asset_primary",
        provider="anthropic",
        task_name="stage2",
        subsystem="analysis",
        symbol="XAUUSD",
        model_name="claude-3-7-sonnet",
        input_tokens=1000,
        output_tokens=500,
        thinking_tokens=200,
        total_tokens=1500,
        cached_tokens=100,
        cache_creation_tokens=50,
        cost_estimate=0.015,
        execution_time_ms=1200,
        status="success",
        slot_name="primary",
        timestamp=datetime.now(timezone.utc),
    )
    db_session.add(sample_log)
    await db_session.commit()

    @asynccontextmanager
    async def mock_get_session():
        yield db_session

    with patch("utils.analytics.token_auditor.get_session", side_effect=mock_get_session):
        summary = await TokenAuditor.get_summary(hours=24)
        assert isinstance(summary, dict)
        assert summary["total_calls"] == 1
        assert summary["total_tokens"] == 1500
        assert summary["thinking_tokens"] == 200
        assert summary["pure_content_tokens"] == 300
        assert "thinking_pct_of_output" in summary
        assert summary["cached_tokens"] == 100
        assert summary["total_cost_usd"] == 0.015

        roles = await TokenAuditor.get_role_breakdown(hours=24)
        assert isinstance(roles, list)
        assert len(roles) == 1
        assert roles[0]["task_role"] == "stage2_per_asset_primary"
        assert "avg_thinking" in roles[0]
        assert "sum_thinking" in roles[0]
        assert "thinking_pct" in roles[0]

        subsystems = await TokenAuditor.get_subsystem_breakdown(hours=24)
        assert isinstance(subsystems, list)
        assert len(subsystems) == 1
        assert subsystems[0]["subsystem"] == "analysis"
        assert "sum_thinking" in subsystems[0]

        symbols = await TokenAuditor.get_symbol_breakdown(hours=24)
        assert isinstance(symbols, list)
        assert len(symbols) == 1
        assert symbols[0]["symbol"] == "XAUUSD"
        assert "sum_thinking" in symbols[0]

        providers = await TokenAuditor.get_provider_breakdown(hours=24)
        assert isinstance(providers, list)
        assert len(providers) == 1
        assert providers[0]["model_name"] == "claude-3-7-sonnet"
        assert "sum_thinking" in providers[0]

        recent = await TokenAuditor.get_recent_logs(limit=5)
        assert isinstance(recent, list)
        assert len(recent) == 1
        assert recent[0]["thinking_tokens"] == 200

        # Test stage and slot breakdown
        stage_slots = await TokenAuditor.get_stage_and_slot_breakdown(hours=24)
        assert isinstance(stage_slots, list)
        assert len(stage_slots) == 1
        assert stage_slots[0]["subsystem"] == "analysis"
        assert stage_slots[0]["slot_name"] == "primary"
        assert stage_slots[0]["cache_hit_rate_pct"] == 10.0  # 100 / 1000 * 100

        # Test cache performance audit
        cache_audit = await TokenAuditor.get_cache_performance_audit(hours=24)
        assert isinstance(cache_audit, dict)
        assert cache_audit["total_input_tokens"] == 1000
        assert cache_audit["cache_read_tokens"] == 100
        assert cache_audit["global_cache_hit_rate_pct"] == 10.0
        assert len(cache_audit["model_cache_breakdown"]) == 1
        assert cache_audit["model_cache_breakdown"][0]["model_name"] == "claude-3-7-sonnet"


@pytest.mark.asyncio
async def test_activity_logger_fallback_event(db_session):
    from logging_observability.activity_logger import ActivityLogger
    from database.models import ActivityLog
    from sqlalchemy import select

    logger_instance = ActivityLogger()
    log_id = await logger_instance.log_fallback_event(
        task_role="stage1_macro",
        from_slot="primary",
        from_model="gemini-2.5-pro",
        to_slot="fallback_1",
        to_model="claude-3-7-sonnet",
        reason="rate_limited",
        cycle_id="cycle-404",
        session=db_session,
    )
    assert log_id is not None

    stmt = select(ActivityLog).where(ActivityLog.id == log_id)
    entry = (await db_session.execute(stmt)).scalar_one_or_none()
    assert entry is not None
    assert entry.actor == "failover_engine"
    assert "LLM FALLBACK" in entry.description
    assert "gemini-2.5-pro" in entry.description
    assert "claude-3-7-sonnet" in entry.description
    assert "cycle-404" in entry.description


