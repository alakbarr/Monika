import pytest
from datetime import datetime, timezone, timedelta
from database.models import UserMarketIntel, _utcnow


def test_user_market_intel_instantiation():
    now = _utcnow()
    intel = UserMarketIntel(
        telegram_user_id="12345678",
        intel_type="pre_event_research",
        title="FOMC Whisper Expectations",
        summary="Market whispers indicate 25bps cut fully priced, 50bps cut at 15% probability.",
        full_content="Detailed institutional consensus research report...",
        affected_symbols=["EURUSD", "USDJPY", "XAUUSD"],
        directive="favor_buy",
        target_cycle="next_cycle_only",
        is_active=True,
        created_at=now,
        expires_at=now + timedelta(hours=8),
        metadata_json={"source": "tavily", "consensus_sentiment": "dovish"},
    )

    assert intel.telegram_user_id == "12345678"
    assert intel.intel_type == "pre_event_research"
    assert intel.title == "FOMC Whisper Expectations"
    assert "EURUSD" in intel.affected_symbols_list
    assert intel.directive == "favor_buy"
    assert intel.target_cycle == "next_cycle_only"
    assert intel.is_active is True
    assert intel.consumed_at is None
    assert intel.consumed_by_cycle_id is None
    assert intel.metadata_dict["source"] == "tavily"


def test_user_market_intel_defaults():
    intel = UserMarketIntel(
        title="Quick Note",
        summary="Short note on DXY",
        intel_type="tactical_directive",
    )

    assert intel.title == "Quick Note"
    assert intel.directive == "neutral"
    assert intel.target_cycle == "next_cycle_only"
    assert intel.is_active is True
    assert intel.affected_symbols == "ALL"
    assert intel.affected_symbols_list == ["ALL"]
    assert intel.metadata_dict == {}


def test_user_market_intel_consumption_lifecycle():
    now = _utcnow()
    intel = UserMarketIntel(
        title="Next Cycle Directive",
        summary="Avoid trading GBPUSD during BoE speech",
        intel_type="flash_news",
        target_cycle="next_cycle_only",
        is_active=True,
    )

    assert intel.is_active is True
    assert intel.consumed_at is None

    # Simulate post-cycle consumption
    intel.is_active = False
    intel.consumed_at = now
    intel.consumed_by_cycle_id = "cycle_20260904_080000"

    assert intel.is_active is False
    assert intel.consumed_at == now
    assert intel.consumed_by_cycle_id == "cycle_20260904_080000"
