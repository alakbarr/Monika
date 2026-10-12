import pytest
from scrapers.models import CalendarEvent, ScrapedNews, ScrapedTweet, FedProbability, FedMeeting

def test_calendar_event():
    event = CalendarEvent(
        time="10:00", currency="USD", impact="High", event_name="NFP",
        actual="100K", forecast="90K", previous="80K"
    )
    assert event.time == "10:00"
    assert event.impact == "High"
    assert event.actual == "100K"

def test_scraped_news():
    news = ScrapedNews(
        title="Test News", url="http://test.com", source="Test",
        timestamp="2023-01-01", summary="A summary"
    )
    assert news.title == "Test News"
    assert news.summary == "A summary"

def test_scraped_tweet():
    tweet = ScrapedTweet(
        id="123", username="testuser", content="hello",
        url="http://x.com/123", timestamp="2023-01-01"
    )
    assert tweet.id == "123"
    assert not tweet.is_retweet
    assert tweet.media_urls is None

def test_fed_models():
    prob = FedProbability(target_range="5.25-5.50", probability=90.5, action="Hold")
    assert prob.probability == 90.5
    
    meeting = FedMeeting(
        meeting_date="2023-09-20", current_rate_ref=5.50,
        probabilities=[prob], most_likely="Hold"
    )
    assert meeting.most_likely == "Hold"
    assert len(meeting.probabilities) == 1
