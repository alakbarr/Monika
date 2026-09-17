# ==============================================================================
# File: scrapers/news/rss_marketwatch.py
# ==============================================================================

from scrapers.news.rss_base import RssBaseScraper

class MarketwatchRssScraper(RssBaseScraper):
    def __init__(self):
        super().__init__(
            source_name="marketwatch_pulse", 
            feed_url="http://feeds.marketwatch.com/marketwatch/marketpulse/"
        )
