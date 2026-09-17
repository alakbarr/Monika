import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from database.adapters import (
    extract_currency_tags, parse_timestamp, scraped_news_to_model, 
    calendar_event_to_model, scraped_tweet_to_model, fed_meeting_to_models,
    batch_save_news, batch_save_calendar, batch_save_tweets, batch_save_fedwatch
)
from scrapers.models import ScrapedNews, CalendarEvent, ScrapedTweet, FedMeeting, FedProbability
from database.models import NewsItem, EconomicCalendar, FedWatchProbability

def test_extract_currency_tags():
    assert extract_currency_tags("The fed hiked rates") == "USD"
    assert extract_currency_tags("ECB and BOE to hike") == "EUR,GBP"
    assert extract_currency_tags("Gold prices fell") == "XAU"
    assert extract_currency_tags("Bitcoin breaks all time high") == "BTC"
    assert extract_currency_tags("OPEC agrees on crude oil cuts") == "XTI"
    assert extract_currency_tags("Nothing relevant") is None

def test_parse_timestamp():
    dt = parse_timestamp("2024-01-01T12:00:00Z")
    assert dt.year == 2024
    assert dt.tzname() == "UTC"
    
    # Test timezone offset conversion to UTC
    dt_wib = parse_timestamp("2026-08-27T19:30:00+07:00")
    assert dt_wib.year == 2026
    assert dt_wib.month == 8
    assert dt_wib.day == 27
    assert dt_wib.hour == 12
    assert dt_wib.minute == 30
    assert dt_wib.tzname() == "UTC"

    dt_edt = parse_timestamp("2026-08-27T08:30:00-04:00")
    assert dt_edt.hour == 12
    assert dt_edt.minute == 30
    assert dt_edt.tzname() == "UTC"

    assert parse_timestamp(None) is None
    assert parse_timestamp("invalid date") is None
    
    dt2 = datetime(2024, 1, 1)
    dt_parsed = parse_timestamp(dt2)
    assert dt_parsed.tzinfo == timezone.utc

def test_scraped_news_to_model():
    news = ScrapedNews(source="Bloomberg", title="Fed hike", summary="Details", url="http://b.com", timestamp="2024-01-01T00:00:00Z")
    model = scraped_news_to_model(news)
    assert isinstance(model, NewsItem)
    assert model.source == "Bloomberg"
    assert model.currency_tags == "USD"

def test_calendar_event_to_model():
    event = CalendarEvent(event_name="NFP", time="2024-01-01T00:00:00Z", currency="USD", impact="High", actual="100K", forecast="150K", previous="200K")
    model = calendar_event_to_model(event)
    assert isinstance(model, EconomicCalendar)
    assert model.event_name == "NFP"
    assert model.impact == "high"

def test_scraped_tweet_to_model():
    tweet = ScrapedTweet(id="1", username="trader", content="Long Gold!", url="http://t.co", timestamp="2024-01-01T00:00:00Z")
    model = scraped_tweet_to_model(tweet)
    assert isinstance(model, NewsItem)
    assert model.source == "twitter"
    assert "XAU" in model.currency_tags

def test_fed_meeting_to_models():
    meeting = FedMeeting(meeting_date="2024-02-01", current_rate_ref="5.25-5.50%", most_likely="Hold", probabilities=[
        FedProbability(target_range="5.25-5.50%", probability=80.0, action="Hold")
    ])
    models = fed_meeting_to_models(meeting)
    assert len(models) == 1
    assert isinstance(models[0], FedWatchProbability)

@pytest.mark.asyncio
async def test_batch_save_news():
    """Bulk dedup: 1 query VIX + 1 bulk URL check; kedua news baru -> keduanya disimpan."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_vix_result = MagicMock()
    mock_vix_result.scalar_one_or_none.return_value = None  # no VIX row -> no warning prefix
    mock_url_result = MagicMock()
    mock_url_result.scalars.return_value.all.return_value = []  # no existing URLs
    mock_session.execute = AsyncMock(side_effect=[mock_vix_result, mock_url_result])

    news1 = ScrapedNews(source="A", title="T1", summary="", url="http://u1", timestamp=None)
    news2 = ScrapedNews(source="A", title="T2", summary="", url="http://u2", timestamp=None)

    res = await batch_save_news(mock_session, [news1, news2])

    assert res == 2
    assert mock_session.add.call_count == 2
    mock_session.commit.assert_awaited_once()

@pytest.mark.asyncio
async def test_batch_save_news_skips_duplicates():
    """URL yang sudah ada di DB di-skip tanpa query per-item (anti N+1)."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_vix_result = MagicMock()
    mock_vix_result.scalar_one_or_none.return_value = None
    mock_url_result = MagicMock()
    mock_url_result.scalars.return_value.all.return_value = ["http://u1"]  # news1 exists
    mock_session.execute = AsyncMock(side_effect=[mock_vix_result, mock_url_result])

    news1 = ScrapedNews(source="A", title="T1", summary="", url="http://u1", timestamp=None)
    news2 = ScrapedNews(source="A", title="T2", summary="", url="http://u2", timestamp=None)

    res = await batch_save_news(mock_session, [news1, news2])

    assert res == 1
    assert mock_session.add.call_count == 1
    added = mock_session.add.call_args[0][0]
    assert added.url == "http://u2"
    mock_session.commit.assert_awaited_once()

@pytest.mark.asyncio
async def test_batch_save_calendar():
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None 
    mock_session.execute = AsyncMock(return_value=mock_result)
    
    event1 = CalendarEvent(event_name="E1", time="2024-01-01T00:00:00Z", currency="USD", impact="High", actual=None, forecast=None, previous=None)
    
    res = await batch_save_calendar(mock_session, [event1])
    assert res == 1
    assert mock_session.add.call_count >= 1
    mock_session.commit.assert_awaited()

@pytest.mark.asyncio
async def test_batch_save_calendar_updates_existing_event():
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    
    existing_event = MagicMock()
    existing_event.actual = None
    existing_event.forecast = "1.0"
    existing_event.previous = "0.8"
    existing_event.fetched_at = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    
    # 1st execute: finding existing event
    mock_res_event = MagicMock()
    mock_res_event.scalar_one_or_none.return_value = existing_event
    
    # 2nd execute: finding SystemConfig for last_calendar_fetch_at
    existing_cfg = MagicMock()
    mock_res_cfg = MagicMock()
    mock_res_cfg.scalar_one_or_none.return_value = existing_cfg
    
    mock_session.execute.side_effect = [mock_res_event, mock_res_cfg]
    
    event_released = CalendarEvent(
        event_name="E1", time="2024-01-01T00:00:00Z", currency="USD",
        impact="High", actual="1.2", forecast="1.0", previous="0.8"
    )
    
    res = await batch_save_calendar(mock_session, [event_released])
    assert res == 0  # 0 new, 1 updated
    assert existing_event.actual == "1.2"
    assert existing_event.fetched_at is not None
    assert existing_cfg.value is not None
    mock_session.commit.assert_awaited()

@pytest.mark.asyncio
async def test_batch_save_calendar_self_heals_corrupt_timestamp():
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    
    # Existing event has corrupted time (19:30 UTC instead of 12:30 UTC)
    corrupted_existing_event = MagicMock()
    corrupted_existing_event.event_time = datetime(2026, 8, 27, 19, 30, tzinfo=timezone.utc)
    corrupted_existing_event.actual = None
    corrupted_existing_event.forecast = "230K"
    corrupted_existing_event.previous = "235K"
    
    # 1st execute: 30-min window query returns None
    mock_res_30m = MagicMock()
    mock_res_30m.scalar_one_or_none.return_value = None
    
    # 2nd execute: same-day fallback query finds the corrupted event
    mock_res_day = MagicMock()
    mock_res_day.scalar_one_or_none.return_value = corrupted_existing_event
    
    # 3rd execute: SystemConfig fetch
    mock_res_cfg = MagicMock()
    mock_res_cfg.scalar_one_or_none.return_value = MagicMock()
    
    mock_session.execute.side_effect = [mock_res_30m, mock_res_day, mock_res_cfg]
    
    # Incoming event with corrected time (12:30 UTC)
    corrected_event = CalendarEvent(
        event_name="Initial Jobless Claims",
        time="2026-08-27T12:30:00Z",
        currency="USD",
        impact="High",
        actual="228K",
        forecast="230K",
        previous="235K"
    )
    
    res = await batch_save_calendar(mock_session, [corrected_event])
    assert res == 0
    # Verifikasi bahwa timestamp yang korup berhasil diperbaiki ke 12:30 UTC
    assert corrupted_existing_event.event_time == datetime(2026, 8, 27, 12, 30, tzinfo=timezone.utc)
    assert corrupted_existing_event.actual == "228K"
    mock_session.commit.assert_awaited()

@pytest.mark.asyncio
async def test_batch_save_tweets():
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None 
    mock_session.execute = AsyncMock(return_value=mock_result)
    
    tweet1 = ScrapedTweet(id="1", username="U1", content="C1", url="http://t1", timestamp=None)
    
    res = await batch_save_tweets(mock_session, [tweet1])
    assert res == 1
    mock_session.add.assert_called_once()
    mock_session.commit.assert_awaited_once()

@pytest.mark.asyncio
async def test_batch_save_fedwatch():
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    
    meeting = FedMeeting(meeting_date="2024-02-01", current_rate_ref="", most_likely="", probabilities=[])
    
    res = await batch_save_fedwatch(mock_session, [meeting])
    assert res == 1
    mock_session.add.assert_called_once()
    mock_session.commit.assert_awaited_once()
