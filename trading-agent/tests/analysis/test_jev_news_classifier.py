"""
Unit tests for Jev-powered news classification, news watcher shock eval, and trigger validator.
"""

import pytest
import unittest.mock as mock
from datetime import datetime, timezone, timedelta
from utils.typesafe.jev_primitives import classify_news_batch_with_jev
from typesafe_sdk import SystemOneResponse, ChoiceAnswer, NoulAnswer, ScoreAnswer
from typesafe_sdk._core.response_types import Usage


class MockNewsItem:
    def __init__(self, id, title, summary, minutes_ago=10):
        self.id = id
        self.title = title
        self.summary = summary
        self.fetched_at = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
        self.published_at = self.fetched_at


@pytest.mark.asyncio
async def test_classify_news_batch_breaking_success():
    mock_client = mock.AsyncMock()
    
    def fake_system_one(state, questions, **kwargs):
        title = state.get("title", "")
        if "Cut" in title or "Emergency" in title:
            impact_ans = ChoiceAnswer(choice="BREAKING", confidence=0.95, probabilities={"BREAKING": 0.95, "HIGH": 0.05})
            surprise_ans = ChoiceAnswer(choice="large", confidence=0.90, probabilities={"large": 0.90})
            fresh_ans = NoulAnswer(noul=0.92)
        else:
            impact_ans = ChoiceAnswer(choice="LOW", confidence=0.75, probabilities={"LOW": 0.75, "MEDIUM": 0.25})
            surprise_ans = ChoiceAnswer(choice="none", confidence=0.85, probabilities={"none": 0.85})
            fresh_ans = NoulAnswer(noul=0.10)
        
        return SystemOneResponse(
            model="jev-1.13.0",
            usage=Usage(input_tokens=200, output_tokens=0),
            answers={
                "impact": impact_ans,
                "surprise_magnitude": surprise_ans,
                "is_fresh_catalyst": fresh_ans,
                "is_deescalation": NoulAnswer(noul=0.05),
                "is_risk_off": NoulAnswer(noul=0.80),
                "is_risk_on": NoulAnswer(noul=0.10),
            }
        )

    mock_client.system_one.side_effect = fake_system_one

    batch = [
        MockNewsItem(1, "Fed Emergency Rate Cut 50bps Announced", "Unexpected emergency easing", minutes_ago=15),
        MockNewsItem(2, "Routine Market Update for Asian Session", "Quiet trading session", minutes_ago=20),
    ]

    results = await classify_news_batch_with_jev(
        client=mock_client,
        batch=batch,
        now_utc=datetime.now(timezone.utc),
        min_confidence=0.30
    )

    assert results is not None
    assert len(results) == 2
    assert results[0]["impact"] == "BREAKING"
    assert results[0]["confidence"] == 0.95
    assert "USD" in results[0]["currencies"]
    assert "FRESH_CATALYST" in results[0]["sentiments"]
    assert "RISK_OFF" in results[0]["sentiments"]

    assert results[1]["impact"] == "LOW"


@pytest.mark.asyncio
async def test_time_in_system_downgrades_stale_breaking():
    mock_client = mock.AsyncMock()
    mock_client.system_one.return_value = SystemOneResponse(
        model="jev-1.13.0",
        usage=Usage(input_tokens=200, output_tokens=0),
        answers={
            "impact": ChoiceAnswer(choice="BREAKING", confidence=0.90, probabilities={"BREAKING": 0.90}),
            "surprise_magnitude": ChoiceAnswer(choice="large", confidence=0.85, probabilities={"large": 0.85}),
            "is_fresh_catalyst": NoulAnswer(noul=0.80),
            "is_deescalation": NoulAnswer(noul=0.10),
            "is_risk_off": NoulAnswer(noul=0.20),
            "is_risk_on": NoulAnswer(noul=0.80),
        }
    )

    # Item fetched 120 minutes ago (> 90 min threshold)
    stale_batch = [
        MockNewsItem(1, "Major Central Bank Surprise Decision", "Old breaking news", minutes_ago=120)
    ]

    results = await classify_news_batch_with_jev(
        client=mock_client,
        batch=stale_batch,
        now_utc=datetime.now(timezone.utc),
        min_confidence=0.30
    )

    assert results is not None
    # Must be capped at HIGH because time in system exceeds 90 minutes
    assert results[0]["impact"] == "HIGH"


@pytest.mark.asyncio
async def test_calendar_prior_lifts_impact():
    mock_client = mock.AsyncMock()
    mock_client.system_one.return_value = SystemOneResponse(
        model="jev-1.13.0",
        usage=Usage(input_tokens=200, output_tokens=0),
        answers={
            "impact": ChoiceAnswer(choice="LOW", confidence=0.70, probabilities={"LOW": 0.70}),
            "surprise_magnitude": ChoiceAnswer(choice="none", confidence=0.80, probabilities={"none": 0.80}),
            "is_fresh_catalyst": NoulAnswer(noul=0.10),
            "is_deescalation": NoulAnswer(noul=0.10),
            "is_risk_off": NoulAnswer(noul=0.10),
            "is_risk_on": NoulAnswer(noul=0.10),
        }
    )

    batch = [
        MockNewsItem(1, "US CPI Inflation Data Release", "CPI inflation prints 2.5%", minutes_ago=5)
    ]

    # Calendar prior says HIGH impact scheduled release
    results = await classify_news_batch_with_jev(
        client=mock_client,
        batch=batch,
        now_utc=datetime.now(timezone.utc),
        calendar_priors={1: "HIGH"},
        min_confidence=0.30
    )

    assert results is not None
    # Calendar prior HIGH must lift LOW -> HIGH
    assert results[0]["impact"] == "HIGH"


@pytest.mark.asyncio
async def test_news_watcher_realtime_shock():
    from scheduler.news_watcher import NewsWatcher
    nw = NewsWatcher(settings={})
    
    with mock.patch("analysis.providers.llm_factory.get_client_for_task") as mock_get_client:
        mock_client = mock.AsyncMock()
        mock_client.classify_json.return_value = {
            "market_sentiment": 1.2,
            "threatens_positions": "YES",
            "requires_circuit_breaker": "NO",
            "_confidence": 0.88
        }
        mock_get_client.return_value = mock_client

        item = MockNewsItem(1, "Flash Crash in Gold", "Gold dropped $50 in 3 minutes")
        res = await nw.evaluate_realtime_news_shock(item, open_positions=["XAUUSD"])
        assert res["threatens_positions"] == "YES"
        assert res["_confidence"] == 0.88


@pytest.mark.asyncio
async def test_trigger_checker_validate_trigger():
    from scheduler.trigger_checker import TriggerChecker
    from database.models import TradeTrigger
    
    tc = TriggerChecker(settings={})
    
    with mock.patch("analysis.providers.llm_factory.get_client_for_task") as mock_get_client:
        mock_client = mock.AsyncMock()
        mock_client.classify_json.return_value = {
            "is_still_valid": "YES",
            "invalidation_risk": 1.1,
            "_confidence": 0.85
        }
        mock_get_client.return_value = mock_client

        trig = TradeTrigger(
            asset_analysis_id=1,
            trigger_type="price",
            condition_json='{"level": 2650.0, "direction": "above"}',
            created_at=datetime.now(timezone.utc) - timedelta(hours=1)
        )
        res = await tc.validate_trigger_with_jev(trig, current_price=2648.5, symbol="XAUUSD")
        assert res["is_still_valid"] == "YES"
        assert res["_confidence"] == 0.85
