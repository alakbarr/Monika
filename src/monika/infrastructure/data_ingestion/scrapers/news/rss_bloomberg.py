# ==============================================================================
# File: scrapers/news/rss_bloomberg.py
# ==============================================================================

from scrapers.news.rss_base import RssBaseScraper

class BloombergRssScraper(RssBaseScraper):
    def __init__(self):
        super().__init__(
            source_name="bloomberg_markets", 
            feed_url="https://feeds.bloomberg.com/markets/news.rss"
        )
