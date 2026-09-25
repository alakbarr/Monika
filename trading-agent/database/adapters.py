# ==============================================================================
# File: database/adapters.py
# ==============================================================================

"""
Adapter: Mengonversi dataclass scraper menjadi model SQLAlchemy ORM.

Menjembatani layer scraper (dataclass sederhana) dengan layer database (model SQLAlchemy).
"""

import datetime
import json
import logging
import re
from typing import List, Optional

from dateutil import parser as dateutil_parser

from scrapers.models import CalendarEvent, ScrapedNews, ScrapedTweet, FedMeeting
from database.models import NewsItem, EconomicCalendar, FedWatchProbability, SystemConfig
from database.safe_ops import safe_commit

logger = logging.getLogger("TradingAgent.Adapters")


# =============================================================================
# Ekstraksi tag mata uang (berbasis keyword)
# =============================================================================

CURRENCY_KEYWORDS = {
    'USD': ['us dollar', 'usd', 'fed', 'the fed', 'fed rate', 'fed chair', 'fomc', 'treasury', 'us economy', 'us gdp',
            'nonfarm', 'nfp', 'federal reserve', 'powell', 'warsh', 'us cpi', 'us ppi', 'dxy', 'greenback'],
    'EUR': ['euro', 'eur', 'ecb', 'eurozone', 'lagarde', 'european central bank'],
    'GBP': ['pound', 'gbp', 'boe', 'bank of england', 'sterling', 'bailey'],
    'JPY': ['yen', 'jpy', 'boj', 'bank of japan', 'ueda', 'kuroda'],
    'AUD': ['aussie', 'aud', 'rba', 'australia', 'reserve bank of australia'],
    'XAU': ['gold', 'xau', 'precious metal', 'bullion', 'xauusd'],
    'XTI': ['crude oil', 'oil price', 'oil inventories', 'wti', 'brent', 'opec', 'xtiusd', 'xbrusd', 'petroleum', 'energy reserves'],
    'BTC': ['bitcoin', 'btc', 'crypto market', 'cryptocurrency', 'btcusd', 'halving', 'etf btc', 'satoshi', 'digital asset'],
}


import re

CURRENCY_PATTERNS = {
    cur: [re.compile(r'\b' + re.escape(kw) + r'\b', re.IGNORECASE) for kw in kws]
    for cur, kws in CURRENCY_KEYWORDS.items()
}

def extract_currency_tags(text: str) -> Optional[str]:
    """
    Ekstrak tag mata uang dari teks dengan mencocokkan keyword (word boundary regex).
    
    Mengembalikan string kode mata uang yang dipisahkan koma, misal 'USD,EUR,XAU'.
    """
    if not text:
        return None
    tags = []
    for currency, patterns in CURRENCY_PATTERNS.items():
        if any(p.search(text) for p in patterns):
            tags.append(currency)
    return ','.join(tags) if tags else None


# =============================================================================
# Parsing timestamp
# =============================================================================

def parse_timestamp(ts) -> Optional[datetime.datetime]:
    """
    Parsing berbagai format timestamp menjadi UTC datetime (timezone-aware).
    
    Mendukung string ISO, offset timezone (+07:00, Z), dan objek datetime. Mengembalikan None jika gagal.
    """
    if ts is None:
        return None
    if isinstance(ts, datetime.datetime):
        if ts.tzinfo is None:
            return ts.replace(tzinfo=datetime.timezone.utc)
        return ts.astimezone(datetime.timezone.utc)
    if not isinstance(ts, str) or not ts.strip():
        return None
    try:
        clean = ts.strip()
        # Handle Unix epoch numeric string (e.g. "1724812345.678" or "1724812345678")
        if re.match(r"^\d+(\.\d+)?$", clean):
            epoch_val = float(clean)
            if epoch_val > 1e11:  # milliseconds
                epoch_val /= 1000.0
            return datetime.datetime.fromtimestamp(epoch_val, tz=datetime.timezone.utc)

        # Tangani akhiran 'Z'
        if clean.endswith('Z'):
            clean = clean[:-1] + '+00:00'
        dt = dateutil_parser.parse(clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        else:
            dt = dt.astimezone(datetime.timezone.utc)
        return dt
    except (ValueError, TypeError) as e:
        logger.debug(f"Failed to parse timestamp '{ts}': {e}")
        return None


def _now_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


# =============================================================================
# Fungsi adapter individual
# =============================================================================

def scraped_news_to_model(news: ScrapedNews) -> NewsItem:
    """Konversi dataclass ScrapedNews menjadi model ORM NewsItem."""
    text_for_tags = f"{news.title} {news.summary or ''}"
    return NewsItem(
        source=news.source[:50] if news.source else "unknown",
        title=news.title[:500] if news.title else "No Title",
        summary=news.summary,
        url=news.url[:1000] if news.url else "",
        published_at=parse_timestamp(news.timestamp),
        currency_tags=extract_currency_tags(text_for_tags),
        fetched_at=_now_utc(),
        impact=getattr(news, 'impact', None),
        sentiment=getattr(news, 'sentiment', None),
        key_data_point=getattr(news, 'key_data_point', None),
    )


def calendar_event_to_model(event: CalendarEvent) -> EconomicCalendar:
    """Konversi dataclass CalendarEvent menjadi model ORM EconomicCalendar."""
    return EconomicCalendar(
        event_name=event.event_name[:200] if event.event_name else "Unknown Event",
        country=getattr(event, 'country', None) or "",
        currency=event.currency[:10] if event.currency else "",
        impact=event.impact.lower() if event.impact else "low",
        actual=event.actual[:50] if event.actual else None,
        forecast=event.forecast[:50] if event.forecast else None,
        previous=event.previous[:50] if event.previous else None,
        event_time=parse_timestamp(event.time),
        fetched_at=_now_utc(),
        surprise_score=getattr(event, 'surprise_score', None),
    )


def scraped_tweet_to_model(tweet: ScrapedTweet) -> NewsItem:
    """Konversi dataclass ScrapedTweet menjadi model ORM NewsItem (sumber='twitter')."""
    title = tweet.content[:250] + "..." if len(tweet.content) > 250 else tweet.content
    text_for_tags = tweet.content or ""
    return NewsItem(
        source="twitter",
        title=f"@{tweet.username}: {title}",
        summary=tweet.content,
        url=tweet.url[:1000] if tweet.url else "",
        published_at=parse_timestamp(tweet.timestamp),
        currency_tags=extract_currency_tags(text_for_tags),
        fetched_at=_now_utc(),
    )


def fed_meeting_to_models(meeting: FedMeeting) -> List[FedWatchProbability]:
    """
    Konversi dataclass FedMeeting menjadi model ORM FedWatchProbability.
    
    Menyimpan semua probabilitas untuk 1 meeting ke dalam satu baris (format JSON).
    """
    probs_dict = {}
    for prob in meeting.probabilities:
        probs_dict[prob.target_range] = {
            'probability': prob.probability,
            'action': prob.action,
        }
    
    model = FedWatchProbability(
        meeting_date=meeting.meeting_date,
        probabilities_json=json.dumps({
            'current_rate_ref': meeting.current_rate_ref,
            'most_likely': meeting.most_likely,
            'probabilities': probs_dict,
        }),
        fetched_at=_now_utc(),
    )
    return [model]


# =============================================================================
# Utilitas penyimpanan batch asinkron
# =============================================================================

async def batch_save_news(session, news_list: List[ScrapedNews]) -> int:
    """Konversi dan simpan berita secara batch, lewati duplikat berdasarkan URL."""
    from sqlalchemy import select
    from database.models import VIXData

    # Ambil VIX terbaru
    vix_row = (await session.execute(
        select(VIXData).order_by(VIXData.date.desc()).limit(1)
    )).scalar_one_or_none()
    
    is_high_vix = False
    if vix_row and vix_row.close > 30.0:
        is_high_vix = True

    # Bulk deduplikasi URL untuk menghindari N+1 query
    candidate_urls = [n.url[:1000] for n in news_list if getattr(n, "url", None)]
    existing_urls = set()
    if candidate_urls:
        existing_rows = (await session.execute(
            select(NewsItem.url).where(NewsItem.url.in_(candidate_urls))
        )).scalars().all()
        existing_urls = set(existing_rows)

    saved = 0
    for news in news_list:
        # Tambahkan suffix/prefix VIX warning
        if is_high_vix:
            if news.title and "[HIGH_VIX_WARNING]" not in news.title:
                news.title = f"[HIGH_VIX_WARNING] {news.title}"
            elif not news.title:
                news.title = "[HIGH_VIX_WARNING] No Title"

        # Cek duplikat URL dari in-memory set
        if news.url and news.url[:1000] in existing_urls:
            continue
        if news.url:
            existing_urls.add(news.url[:1000])

        model = scraped_news_to_model(news)
        session.add(model)
        saved += 1

    if saved > 0:
        await safe_commit(session, label="batch_save_news")
        logger.info(f"Saved {saved} news items (skipped {len(news_list) - saved} duplicates)")

    return saved


async def batch_save_calendar(session, events: List[CalendarEvent]) -> int:
    """Konversi dan simpan event kalender secara batch dengan deduplikasi (mata uang, event, waktu)."""
    from sqlalchemy import select
    from datetime import timedelta
    
    saved = 0
    updated = 0
    now_utc = _now_utc()
    
    for event in events:
        model = calendar_event_to_model(event)
        if not model.event_time or not model.currency or not model.event_name:
            continue
        
        # Cek event serupa di rentang 30 menit (mengatasi selisih waktu antar scraper)
        time_min = model.event_time - timedelta(minutes=30)
        time_max = model.event_time + timedelta(minutes=30)
        
        existing = (await session.execute(
            select(EconomicCalendar)
            .where(EconomicCalendar.currency == model.currency)
            .where(EconomicCalendar.event_name == model.event_name)
            .where(EconomicCalendar.event_time >= time_min)
            .where(EconomicCalendar.event_time <= time_max)
            .limit(1)
        )).scalar_one_or_none()
        
        # Self-healing: jika tidak ditemukan dalam rentang 30m, cari apakah ada event sama
        # pada hari kalender yang sama (misal tergeser beberapa jam akibat bug timezone lama)
        if existing is None and model.event_time is not None:
            day_min = model.event_time.replace(hour=0, minute=0, second=0, microsecond=0)
            day_max = day_min + timedelta(days=1)
            same_day_corrupt = (await session.execute(
                select(EconomicCalendar)
                .where(EconomicCalendar.currency == model.currency)
                .where(EconomicCalendar.event_name == model.event_name)
                .where(EconomicCalendar.event_time >= day_min)
                .where(EconomicCalendar.event_time < day_max)
                .limit(1)
            )).scalar_one_or_none()
            if same_day_corrupt is not None:
                # Preserve existing valid event_time; only set if existing is None to prevent cross-scraper timestamp shifting
                if same_day_corrupt.event_time is None:
                    same_day_corrupt.event_time = model.event_time
                existing = same_day_corrupt

        if existing is None:
            session.add(model)
            saved += 1
        else:
            # Perbarui fetched_at agar mencerminkan data terverifikasi baru
            existing.fetched_at = now_utc
            
            # Update actual/forecast/previous jika data sudah rilis
            changed = False
            if model.actual and model.actual != existing.actual:
                existing.actual = model.actual
                changed = True
            if model.forecast and model.forecast != existing.forecast:
                existing.forecast = model.forecast
                changed = True
            if model.previous and model.previous != existing.previous:
                existing.previous = model.previous
                changed = True
            if changed:
                updated += 1
    
    # Catat metadata timestamp scraping kalender terakhir ke SystemConfig
    if len(events) > 0:
        cfg = (await session.execute(
            select(SystemConfig).where(SystemConfig.key == "last_calendar_fetch_at")
        )).scalar_one_or_none()
        if cfg:
            cfg.value = now_utc.isoformat()
        else:
            session.add(SystemConfig(key="last_calendar_fetch_at", value=now_utc.isoformat()))

    if saved > 0 or updated > 0 or len(events) > 0:
        await safe_commit(session, label="batch_save_calendar")
        if saved > 0 or updated > 0:
            logger.info(f"Saved {saved} new calendar events (skipped/refreshed {len(events) - saved - updated} duplicates, updated {updated})")
    
    return saved


async def batch_save_tweets(session, tweets: List[ScrapedTweet]) -> int:
    """Konversi dan simpan tweet secara batch sebagai berita, lewati duplikat."""
    from sqlalchemy import select

    saved = 0
    for tweet in tweets:
        if tweet.url:
            stmt = select(NewsItem.id).where(NewsItem.url == tweet.url[:1000]).limit(1)
            result = await session.execute(stmt)
            if result.scalar_one_or_none() is not None:
                continue

        model = scraped_tweet_to_model(tweet)
        session.add(model)
        saved += 1

    if saved > 0:
        await safe_commit(session, label="batch_save_tweets")
        logger.info(f"Saved {saved} tweets (skipped {len(tweets) - saved} duplicates)")

    return saved


async def batch_save_fedwatch(session, meetings: List[FedMeeting]) -> int:
    """Konversi dan simpan data probabilitas FedWatch secara batch."""
    saved = 0
    for meeting in meetings:
        models = fed_meeting_to_models(meeting)
        for model in models:
            session.add(model)
            saved += 1

    if saved > 0:
        await safe_commit(session, label="batch_save_fedwatch")
        logger.info(f"Saved {saved} FedWatch records")

    return saved
