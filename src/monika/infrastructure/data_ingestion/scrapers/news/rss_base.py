# ==============================================================================
# File: scrapers/news/rss_base.py
# ==============================================================================

import logging
import time
import re
import urllib.request
from typing import List
from scrapers.models import ScrapedNews

logger = logging.getLogger("TradingAgent.RssNewsScraper")


class _TimeoutHandler(urllib.request.BaseHandler):
    """Enforces connection and read timeout on feedparser urllib opener."""
    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    def http_request(self, req):
        req.timeout = self.timeout
        return req

    def https_request(self, req):
        req.timeout = self.timeout
        return req


class RssBaseScraper:
    """RSS scraper menggunakan feedparser — TIDAK memerlukan browser."""
    
    def __init__(self, source_name: str, feed_url: str, headless: bool = True, timeout: float = 15.0):
        # headless parameter dipertahankan untuk kompatibilitas interface, tapi tidak dipakai
        self.source_name = source_name
        self.feed_url = feed_url
        self.timeout = timeout

    def fetch_news(self, limit: int = 30, fetch_full_text: bool = False) -> List[ScrapedNews]:
        """Fetch news dari RSS feed menggunakan feedparser (tidak perlu browser)."""
        news_list = []
        try:
            import feedparser
        except ImportError:
            logger.error("feedparser is not installed. Run: pip install feedparser")
            return news_list

        DEFAULT_UA = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) "
            "Gecko/20100101 Firefox/128.0"
        )
        try:
            logger.info(f"Fetching RSS feed from {self.source_name}...")
            feed = feedparser.parse(
                self.feed_url,
                agent=DEFAULT_UA,
                request_headers={"User-Agent": DEFAULT_UA, "Accept": "*/*"},
                handlers=[_TimeoutHandler(self.timeout)],
            )
            status = getattr(feed, "status", None)
            if isinstance(status, int) and status == 403:
                fallback_ua = "curl/7.88.1"
                logger.info(f"RSS {self.source_name} got 403, retrying with fallback UA...")
                feed = feedparser.parse(
                    self.feed_url,
                    agent=fallback_ua,
                    request_headers={"User-Agent": fallback_ua, "Accept": "*/*"},
                    handlers=[_TimeoutHandler(self.timeout)],
                )
                status = getattr(feed, "status", None)

            if isinstance(status, int) and status >= 400:
                logger.warning(f"RSS {self.source_name} returned HTTP {status}")
                return news_list

            count = 0
            seen_urls = set()

            for entry in feed.entries:
                if count >= limit:
                    break

                url = entry.get("link", "")
                title = entry.get("title", "")
                raw_published = entry.get("published", entry.get("pubDate", entry.get("updated", entry.get("date", ""))))
                normalized_ts = raw_published
                if raw_published:
                    try:
                        from dateutil import parser as dateutil_parser
                        from datetime import timezone
                        parsed_dt = dateutil_parser.parse(str(raw_published))
                        if parsed_dt.tzinfo is None:
                            parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)
                        if ":" in str(raw_published):
                            normalized_ts = parsed_dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                        else:
                            normalized_ts = str(raw_published)
                    except Exception:
                        normalized_ts = str(raw_published)

                if not url or not title:
                    continue
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                summary = ""
                for field in ["summary", "description", "content"]:
                    val = entry.get(field, "")
                    if isinstance(val, list):
                        val = val[0].get("value", "") if val else ""
                    if val:
                        summary = re.sub(r'<[^>]+>', '', str(val)).strip()[:1000]
                        break

                news_list.append(ScrapedNews(
                    title=title.strip(),
                    url=url,
                    source=f"RSS ({self.source_name})",
                    timestamp=normalized_ts,
                    summary=summary,
                ))
                count += 1

        except Exception as e:
            logger.error(f"Error parsing RSS feed {self.source_name}: {e}")
            return news_list

        return news_list

    def close(self):
        """No-op: RSS scraper tidak membuka resource yang perlu di-close."""
        pass
