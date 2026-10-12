# ==============================================================================
# File: scrapers/news/rss_rba.py
# ==============================================================================
 
"""Reserve Bank of Australia official RSS feeds (Speeches & Monetary Policy Media Releases). Critical for AUDUSD."""
from typing import List
from scrapers.news.rss_base import RssBaseScraper
from scrapers.models import ScrapedNews

class RbaRssScraper(RssBaseScraper):
    def __init__(self):
        super().__init__(
            source_name="rba_official",
            feed_url="https://www.rba.gov.au/rss/rss-cb-media-releases.xml",
        )
        self.feed_urls = [
            "https://www.rba.gov.au/rss/rss-cb-media-releases.xml",
            "https://www.rba.gov.au/rss/rss-cb-speeches.xml",
        ]

    def fetch_news(self, limit: int = 30, fetch_full_text: bool = False) -> List[ScrapedNews]:
        all_news = []
        seen_urls = set()
        per_feed_limit = max(10, limit // len(self.feed_urls))
        for url in self.feed_urls:
            self.feed_url = url
            items = super().fetch_news(limit=per_feed_limit, fetch_full_text=fetch_full_text)
            for item in items:
                if item.url not in seen_urls:
                    seen_urls.add(item.url)
                    all_news.append(item)
        return all_news[:limit]
