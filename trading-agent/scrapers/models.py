# ==============================================================================
# File: scrapers/models.py
# ==============================================================================

from dataclasses import dataclass
from typing import Optional, List

@dataclass
class CalendarEvent:
    time: str
    currency: str
    impact: str # contoh: High, Medium, Low
    event_name: str
    actual: Optional[str] = None
    forecast: Optional[str] = None
    previous: Optional[str] = None
    country: Optional[str] = None
    surprise_score: Optional[float] = None

@dataclass
class ScrapedNews:
    title: str
    url: str
    source: str
    timestamp: str
    summary: Optional[str] = None
    impact: Optional[str] = None
    sentiment: Optional[str] = None
    key_data_point: Optional[str] = None

@dataclass
class ScrapedTweet:
    id: str
    username: str
    content: str
    url: str
    timestamp: str
    is_retweet: bool = False
    retweet_context: Optional[str] = None
    media_urls: Optional[List[str]] = None

@dataclass
class FedProbability:
    target_range: str
    probability: float
    action: str

@dataclass
class FedMeeting:
    meeting_date: str
    current_rate_ref: float
    probabilities: List[FedProbability]
    most_likely: str
