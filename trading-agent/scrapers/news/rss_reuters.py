# ==============================================================================
# File: scrapers/news/rss_reuters.py
# ==============================================================================

from scrapers.news.rss_base import RssBaseScraper

class ReutersRssScraper(RssBaseScraper):
    def __init__(self):
        super().__init__(
            source_name="reuters_markets",
            feed_url="https://news.google.com/rss/search?q=site:reuters.com+when:1d&hl=en-US&gl=US&ceid=US:en"
        )
